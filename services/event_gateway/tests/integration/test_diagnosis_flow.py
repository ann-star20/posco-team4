from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from event_gateway.config import Settings
from event_gateway.contracts import EventCreate
from event_gateway.inference_jobs import claim_due_aoi_requests, submit_inference_job
from event_gateway.migrate import apply_migrations
from event_gateway.repository import EventRepository
from event_gateway.ros_adapter import store_ros_event
from mock_surrogate.app import diagnose


def test_diagnosis_result_and_execution_metadata_are_stored(test_connection):
    apply_migrations(test_connection, Path(__file__).parents[4] / "database/migrations")
    request = {
        "request_id": str(uuid4()), "run_id": str(uuid4()), "lot_id": "L1", "unit_id": "U1",
        "stage_id": "diagnosis", "stage_attempt": 1, "model_contract_version": "fab-ml-v1",
        "input_payload": {"scenario": "normal"}, "diagnosis_mode": "mock",
    }
    accepted = submit_inference_job(test_connection, request, "mock", "mock", "diagnosis")
    dispatch = claim_due_aoi_requests(test_connection)[0]
    response = diagnose(dispatch)
    event = EventCreate(
        schema_version=1, event_id=uuid4(), event_type="diagnosis.completed",
        source="jetson.diagnosis", severity="info", occurred_at=datetime.now(timezone.utc),
        payload={**dispatch, "response": response},
    )
    store_ros_event(EventRepository(test_connection), event, request["run_id"],
                    Settings(database_url="unused"))
    result = test_connection.execute(
        "SELECT top_category,compensation_route,routing_status,response_body "
        "FROM diagnosis_results WHERE job_id=%s", (accepted["job_id"],)).fetchone()
    assert result[:3] == ("normal", "no_action", "normal")
    assert result[3] == response
    execution = test_connection.execute(
        "SELECT model_name,status,inference_duration_ms,stage_metrics "
        "FROM ml_inference_executions WHERE job_id=%s", (accepted["job_id"],)).fetchone()
    assert execution[:3] == ("mock-gp-diagnosis", "succeeded", .2)
    assert execution[3][0]["stage"] == "diagnosis"
