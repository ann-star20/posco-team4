import json
from pathlib import Path
from threading import Thread
import time
from uuid import uuid4

import httpx
from psycopg.conninfo import make_conninfo
import uvicorn
from websockets.sync.client import connect

from event_gateway.app import create_app as create_gateway
from event_gateway.command_dispatcher import claim_due_commands
from event_gateway.command_auth import sign_command
from event_gateway.config import Settings
from event_gateway.contracts import CorrectionProposal, EventCreate
from event_gateway.migrate import apply_migrations
from event_gateway.repository import EventRepository
from event_gateway.verification_worker import VerificationWorker
from fab_virtual_lot.command_subscriber import RecipeStore
from fab_virtual_lot.command_subscriber import make_applied_receipt
from mock_tcad.app import create_app as create_mock_tcad


ROOT = Path(__file__).parents[4]


def _server(app):
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=0,
                                            log_level="error", lifespan="off"))
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.02)
    assert server.started
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, thread, port


def test_mock_mock_software_pipeline(test_connection, tmp_path):
    connection = test_connection
    apply_migrations(connection, ROOT / "database/migrations")
    tcad_server, tcad_thread, tcad_port = _server(create_mock_tcad(tmp_path / "tcad.sqlite"))
    schema = connection.execute("SHOW search_path").fetchone()[0]
    test_dsn = Settings.load(ROOT / ".env").test_database_url
    gateway_dsn = make_conninfo(test_dsn, options=f"-c search_path={schema}")
    gateway_server, gateway_thread, gateway_port = _server(
        create_gateway(Settings(database_url=gateway_dsn, approval_token="demo-test-token",
                                approval_operator="operator")))
    try:
        repository = EventRepository(connection, "fixture-key")
        run_id = uuid4()
        repository.ensure_run(run_id, "mock", "mock")
        current = {key: 1.0 for key in (
            "oxide_thickness", "body_dose", "diffusion_time", "epi_doping")}
        delta = {key: 0.0 for key in current}
        delta["body_dose"] = 0.01
        observed = {key: 1.0 for key in ("vth", "gm", "id_on", "bv")}
        proposal = CorrectionProposal.model_validate({
            "proposal_id": str(uuid4()), "run_id": str(run_id),
            "representation": "normalized_ratio", "baseline_version": "demo-v1",
            "x_current": current, "delta_x": delta,
            "x_candidate": {key: current[key] + delta[key] for key in current},
            "y_observed": observed,
            "targets": {key: {"min": 0.9, "max": 1.1} for key in observed},
        })
        event = EventCreate.model_validate({
            "schema_version": 1, "event_id": str(uuid4()),
            "event_type": "correction.proposed", "source": "jetson.demo",
            "severity": "info", "occurred_at": "2026-10-14T00:00:00Z",
            "payload": proposal.model_dump(mode="json"),
        })
        repository.ingest_proposal(
            event, proposal, uuid4(), "mock", f"http://127.0.0.1:{tcad_port}")
        worker = VerificationWorker(connection)
        assert worker.run_once() == 1  # HTTP 202
        assert worker.run_once() == 1  # HTTP result
        status = connection.execute(
            "SELECT status FROM correction_proposals WHERE proposal_id=%s",
            (proposal.proposal_id,),
        ).fetchone()[0]
        assert status == "verified"
        with connect(f"ws://127.0.0.1:{gateway_port}/api/v1/stream?"
                     f"run_id={run_id}&after_sequence=0", open_timeout=3) as websocket:
            streamed = []
            for _ in range(3):
                streamed.append(json.loads(websocket.recv(timeout=3)))
        verified = next(item for item in streamed if item["event_type"] == "correction.verified")
        assert verified["correction"]["body_dose"]["recommended"] == 1.01
        assert verified["approval_allowed"] is True
        unauthorized = httpx.post(
            f"http://127.0.0.1:{gateway_port}/api/v1/proposals/{proposal.proposal_id}/approval",
            json={"approved_by": "operator", "effective_from_lot": "LOT-2"}, timeout=3,
        )
        assert unauthorized.status_code == 401
        response = httpx.post(
            f"http://127.0.0.1:{gateway_port}/api/v1/proposals/{proposal.proposal_id}/approval",
            json={"approved_by": "operator", "effective_from_lot": "LOT-2"}, timeout=3,
            headers={"X-Approval-Token": "demo-test-token"},
        )
        assert response.status_code == 200
        command = sign_command(claim_due_commands(connection)[0], "fixture-key")
        with RecipeStore(tmp_path / "recipe.sqlite", "fixture-key") as store:
            applied_event_id = store.apply(command)
            assert store.recipe_for("LOT-2")["body_dose"] == 1.01
        applied = EventCreate.model_validate({
            "schema_version": 1, "event_id": str(applied_event_id),
            "event_type": "correction.applied", "source": "jetson.virtual_lot",
            "severity": "info", "occurred_at": "2026-10-14T00:00:00Z",
            "payload": make_applied_receipt(command, applied_event_id, "fixture-key"),
        })
        repository.ingest(applied, run_id)
        repository.ingest(applied, run_id)
        assert connection.execute(
            "SELECT status FROM commands WHERE command_id=%s", (command["command_id"],)
        ).fetchone() == ("applied",)
    finally:
        gateway_server.should_exit = True
        tcad_server.should_exit = True
        gateway_thread.join(timeout=3)
        tcad_thread.join(timeout=3)
