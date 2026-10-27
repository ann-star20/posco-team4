from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from event_gateway.migrate import apply_migrations
from event_gateway.contracts import EventCreate, CorrectionProposal
from event_gateway.repository import EventRepository, EventConflict
from event_gateway.stream import format_unity_event


ROOT = Path(__file__).parents[4]


def test_migration_is_repeatable_and_preserves_legacy_event(test_connection):
    connection = test_connection
    connection.execute((ROOT / "database/migrations/001_create_events.sql").read_text(encoding="utf-8"))
    event_id = uuid4()
    connection.execute(
        "INSERT INTO events(event_id,schema_version,event_type,source,severity,payload,occurred_at) "
        "VALUES (%s,1,'legacy','test','info','{}',now())", (event_id,))
    apply_migrations(connection, ROOT / "database/migrations", start_at=2)
    apply_migrations(connection, ROOT / "database/migrations", start_at=2)
    row = connection.execute("SELECT run_id FROM events WHERE event_id=%s", (event_id,)).fetchone()
    assert row == (None,)
    assert connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall() == [
        ("002_create_integration_workflow.sql",),
        ("003_create_dead_letters.sql",),
        ("004_create_aoi_image_artifacts.sql",),
        ("005_create_inference_jobs.sql",),
        ("006_surrogate_and_unity_delivery.sql",),
        ("007_create_aoi_inference_metrics.sql",),
        ("008_diagnosis_and_ml_executions.sql",),
        ("009_ml_execution_attempts.sql",),
        ("010_create_tcad_candidate_queue.sql",),
    ]


def test_correction_and_job_constraints(test_connection):
    connection = test_connection
    connection.execute((ROOT / "database/migrations/001_create_events.sql").read_text(encoding="utf-8"))
    apply_migrations(connection, ROOT / "database/migrations", start_at=2)
    with pytest.raises(psycopg.errors.CheckViolation):
        connection.execute(
            "INSERT INTO integration_runs(run_id,tcad_mode,unity_mode,input_origin,baseline_version) "
            "VALUES (%s,'invalid','mock','synthetic','v1')", (uuid4(),))


def test_retry_idempotency(test_connection):
    connection = test_connection
    apply_migrations(connection, ROOT / "database/migrations")
    run_id = uuid4()
    connection.execute(
        "INSERT INTO integration_runs VALUES (%s,'mock','mock','synthetic','demo-v1',now())",
        (run_id,),
    )
    event = EventCreate.model_validate({
        "schema_version": 1, "event_id": str(uuid4()), "event_type": "anomaly.detected",
        "source": "jetson.demo", "severity": "warning",
        "occurred_at": "2026-10-14T00:00:00Z", "payload": {"lot_id": "lot-1"},
    })
    repository = EventRepository(connection)
    first = repository.ingest(event, run_id)
    second = repository.ingest(event, run_id)
    assert first.sequence == second.sequence
    assert connection.execute("SELECT count(*) FROM events").fetchone() == (1,)
    changed = event.model_copy(update={"payload": {"lot_id": "different"}})
    with pytest.raises(EventConflict):
        repository.ingest(changed, run_id)


def test_existing_run_keeps_modes_after_configuration_change(test_connection):
    connection = test_connection
    apply_migrations(connection, ROOT / "database/migrations")
    run_id = uuid4()
    repository = EventRepository(connection)
    assert repository.resolve_run(run_id, "mock", "mock")[:2] == ("mock", "mock")
    assert repository.resolve_run(run_id, "prod", "prod")[:2] == ("mock", "mock")


def test_replayed_approval_uses_stored_unity_mode(test_connection):
    connection = test_connection
    apply_migrations(connection, ROOT / "database/migrations")
    run_id = uuid4()
    repository = EventRepository(connection)
    repository.resolve_run(run_id, "mock", "prod")
    event = EventCreate.model_validate({
        "schema_version": 1, "event_id": str(uuid4()),
        "event_type": "correction.verified", "source": "gateway.verification",
        "severity": "info", "occurred_at": "2026-10-14T00:00:00Z",
        "payload": {"result_origin": "mock"},
    })
    repository.ingest(event, run_id)
    row = repository.list_after(run_id, 0)[0]
    assert row["unity_mode"] == "prod"
    assert format_unity_event(row, row["unity_mode"])["approval_allowed"] is False


def test_proposal_job_event_atomic(test_connection):
    connection = test_connection
    apply_migrations(connection, ROOT / "database/migrations")
    run_id = uuid4()
    connection.execute(
        "INSERT INTO integration_runs VALUES (%s,'mock','mock','synthetic','demo-v1',now())",
        (run_id,),
    )
    current = dict.fromkeys(("oxide_thickness", "body_dose", "diffusion_time", "epi_doping"), 1.0)
    observed = dict.fromkeys(("vth", "gm", "id_on", "bv"), 1.0)
    proposal = CorrectionProposal.model_validate({
        "proposal_id": str(uuid4()), "run_id": str(run_id),
        "representation": "normalized_ratio", "baseline_version": "demo-v1",
        "x_current": current, "delta_x": dict.fromkeys(current, 0.0),
        "x_candidate": current, "y_observed": observed,
        "targets": {key: {"min": 0.9, "max": 1.1} for key in observed},
    })
    event = EventCreate.model_validate({
        "schema_version": 1, "event_id": str(uuid4()), "event_type": "correction.proposed",
        "source": "jetson.demo", "severity": "info",
        "occurred_at": "2026-10-14T00:00:00Z",
        "payload": proposal.model_dump(mode="json"),
    })
    repository = EventRepository(connection)
    request_id = uuid4()
    repository.ingest_proposal(event, proposal, request_id, "mock", "http://127.0.0.1:8100")
    assert connection.execute("SELECT count(*) FROM events").fetchone() == (1,)
    assert connection.execute("SELECT count(*) FROM correction_proposals").fetchone() == (1,)
    assert connection.execute("SELECT count(*) FROM verification_jobs").fetchone() == (1,)
