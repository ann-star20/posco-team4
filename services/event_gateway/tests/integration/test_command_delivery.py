from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from event_gateway.commands import approve_proposal
from event_gateway.command_auth import sign_command
from event_gateway.contracts import EventCreate
from event_gateway.migrate import apply_migrations
from event_gateway.repository import EventRepository
from fab_virtual_lot.command_subscriber import make_applied_receipt


ROOT = Path(__file__).parents[4]


def test_applied_event_updates_command_once(test_connection):
    connection = test_connection
    apply_migrations(connection, ROOT / "database/migrations")
    run_id, source_id, proposal_id = uuid4(), uuid4(), uuid4()
    connection.execute(
        "INSERT INTO integration_runs(run_id,tcad_mode,unity_mode,input_origin,baseline_version) "
        "VALUES (%s,'mock','mock','synthetic','demo-v1')", (run_id,))
    connection.execute(
        "INSERT INTO events(run_id,event_id,schema_version,event_type,source,severity,payload,occurred_at) "
        "VALUES (%s,%s,1,'correction.proposed','test','info','{}',now())",
        (run_id, source_id))
    vector = {key: 1.0 for key in ("oxide_thickness", "body_dose", "diffusion_time", "epi_doping")}
    connection.execute(
        "INSERT INTO correction_proposals(proposal_id,run_id,source_event_id,representation,"
        "x_current,delta_x,x_candidate,y_observed,targets,status,y_verified,result_origin) "
        "VALUES (%s,%s,%s,'normalized_ratio',%s,%s,%s,'{}','{}','verified','{}','mock')",
        (proposal_id, run_id, source_id, Jsonb(vector),
         Jsonb({key: 0 for key in vector}), Jsonb(vector)))
    command_id = approve_proposal(connection, proposal_id, "operator", "LOT-2")
    command = connection.execute(
        "SELECT payload FROM commands WHERE command_id=%s", (command_id,)
    ).fetchone()[0]
    command = sign_command(command, "fixture-key")
    applied_event_id = uuid4()
    event = EventCreate.model_validate({
        "schema_version": 1, "event_id": str(applied_event_id), "event_type": "correction.applied",
        "source": "jetson.virtual_lot", "severity": "info",
        "occurred_at": "2026-10-14T00:00:00Z",
        "payload": make_applied_receipt(command, applied_event_id, "fixture-key"),
    })
    repository = EventRepository(connection, "fixture-key")
    repository.ingest(event, run_id)
    repository.ingest(event, run_id)
    assert connection.execute(
        "SELECT status,applied_event_id FROM commands WHERE command_id=%s", (command_id,)
    ).fetchone() == ("applied", event.event_id)
