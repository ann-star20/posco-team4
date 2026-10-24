from pathlib import Path
from uuid import uuid4

import httpx

from event_gateway.migrate import apply_migrations
from event_gateway.contracts import CorrectionProposal, EventCreate
from event_gateway.repository import EventRepository
from event_gateway.verification_worker import VerificationWorker


ROOT = Path(__file__).parents[4]


def test_worker_verifies_stored_job_after_restart(test_connection):
    db = test_connection
    apply_migrations(db, ROOT / "database/migrations")
    run_id = uuid4()
    repository = EventRepository(db)
    repository.ensure_run(run_id, "mock", "mock")
    x = dict.fromkeys(("oxide_thickness", "body_dose", "diffusion_time", "epi_doping"), 1.0)
    y = dict.fromkeys(("vth", "gm", "id_on", "bv"), 1.0)
    proposal = CorrectionProposal.model_validate({
        "proposal_id": str(uuid4()), "run_id": str(run_id), "representation": "normalized_ratio",
        "baseline_version": "demo-v1", "x_current": x,
        "delta_x": dict.fromkeys(x, 0.0), "x_candidate": x, "y_observed": y,
        "targets": {key: {"min": 0.9, "max": 1.1} for key in y},
    })
    event = EventCreate.model_validate({
        "schema_version": 1, "event_id": str(uuid4()), "event_type": "correction.proposed",
        "source": "jetson.demo", "severity": "info", "occurred_at": "2026-10-14T00:00:00Z",
        "payload": proposal.model_dump(mode="json"),
    })
    request_id = uuid4()
    repository.ingest_proposal(event, proposal, request_id, "mock", "http://tcad.test")
    assert db.execute("SELECT status FROM verification_jobs").fetchone() == ("queued",)
    assert db.execute("SELECT next_attempt_at<=now() FROM verification_jobs").fetchone() == (True,)

    def tcad(request):
        if request.method == "POST":
            return httpx.Response(202, json={"request_id": str(request_id), "job_id": "job-1"})
        return httpx.Response(200, json={
            "status": "succeeded", "request_id": str(request_id), "job_id": "job-1",
            "result_origin": "mock", "deck_template_version": "demo-v1",
            "y_verified": y,
        })

    worker = VerificationWorker(db, lambda url: httpx.Client(
        transport=httpx.MockTransport(tcad), base_url=url))
    assert worker.run_once() == 1
    assert worker.run_once() == 1
    assert db.execute("SELECT status FROM correction_proposals").fetchone() == ("verified",)
    assert db.execute("SELECT count(*) FROM events").fetchone() == (3,)


def test_worker_records_terminal_http_4xx(test_connection):
    db = test_connection
    apply_migrations(db, ROOT / "database/migrations")
    run_id = uuid4()
    repository = EventRepository(db)
    repository.ensure_run(run_id, "mock", "mock")
    x = dict.fromkeys(("oxide_thickness", "body_dose", "diffusion_time", "epi_doping"), 1.0)
    y = dict.fromkeys(("vth", "gm", "id_on", "bv"), 1.0)
    proposal = CorrectionProposal.model_validate({
        "proposal_id": str(uuid4()), "run_id": str(run_id),
        "representation": "normalized_ratio", "baseline_version": "demo-v1",
        "x_current": x, "delta_x": dict.fromkeys(x, 0.0),
        "x_candidate": x, "y_observed": y,
        "targets": {key: {"min": 0.9, "max": 1.1} for key in y},
    })
    event = EventCreate.model_validate({
        "schema_version": 1, "event_id": str(uuid4()), "event_type": "correction.proposed",
        "source": "jetson.demo", "severity": "info", "occurred_at": "2026-10-14T00:00:00Z",
        "payload": proposal.model_dump(mode="json"),
    })
    repository.ingest_proposal(event, proposal, uuid4(), "mock", "http://tcad.test")
    worker = VerificationWorker(db, lambda url: httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(422)), base_url=url))
    assert worker.run_once() == 1
    assert db.execute("SELECT status,last_error_code FROM verification_jobs").fetchone() == (
        "failed", "http_422")
    assert db.execute("SELECT status FROM correction_proposals").fetchone() == ("failed",)
    assert worker.run_once() == 0
