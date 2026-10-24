from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from event_gateway.config import Settings
from event_gateway.contracts import EventCreate
from event_gateway.inference_jobs import claim_due_aoi_requests, submit_inference_job
from event_gateway.migrate import apply_migrations
from event_gateway.repository import EventRepository
from event_gateway.ros_adapter import store_ros_event
from event_gateway.tcad_contracts import make_tcad_request_id
from mock_surrogate.app import diagnose


ROOT = Path(__file__).parents[4]


def arrange_diagnosis(connection, scenario="anomaly"):
    apply_migrations(connection, ROOT / "database/migrations")
    request = {
        "request_id": str(uuid4()), "run_id": str(uuid4()), "lot_id": "LOT-1",
        "unit_id": "UNIT-1", "stage_id": "diagnosis", "stage_attempt": 1,
        "model_contract_version": "fab-ml-v1", "input_payload": {"scenario": scenario},
        "diagnosis_mode": "mock",
    }
    accepted = submit_inference_job(connection, request, "mock", "mock", "diagnosis")
    dispatch = claim_due_aoi_requests(connection)[0]
    response = diagnose(dispatch)
    event = EventCreate(
        schema_version=1, event_id=uuid4(), event_type="diagnosis.completed",
        source="jetson.diagnosis", severity="info", occurred_at=datetime.now(timezone.utc),
        payload={**dispatch, "response": response},
    )
    return request, accepted, response, event


def ingest(connection, request, event, *, enabled=True):
    settings = Settings(database_url="unused", tcad_auto_submit_enabled=enabled)
    return store_ros_event(EventRepository(connection), event, request["run_id"], settings)


def test_anomaly_admits_every_candidate_with_stable_ids(test_connection):
    request, accepted, response, event = arrange_diagnosis(test_connection)
    second = deepcopy(response["tcad_proposal"]["candidates"][0])
    second["process_parameters"]["oxide_thickness"] = 0.065
    response["tcad_proposal"]["candidates"].append(second)

    ingest(test_connection, request, event)

    group = test_connection.execute(
        "SELECT proposal_id,candidate_count,status,original_request_id FROM tcad_proposal_groups"
    ).fetchone()
    assert group[1:] == (2, "queued", UUID(request["request_id"]))
    rows = test_connection.execute(
        "SELECT candidate_index,tcad_request_id,status,process_parameters,request_body "
        "FROM tcad_verification_candidates ORDER BY candidate_index"
    ).fetchall()
    assert [row[0] for row in rows] == [0, 1]
    assert [row[1] for row in rows] == [
        make_tcad_request_id(group[0], 0), make_tcad_request_id(group[0], 1),
    ]
    assert all(row[2] == "pending" for row in rows)
    assert rows[1][3]["oxide_thickness"] == 0.065
    assert rows[0][4]["job_id"] == accepted["job_id"]
    diagnosis = test_connection.execute(
        "SELECT routing_status,tcad_proposal_group_id FROM diagnosis_results"
    ).fetchone()
    assert diagnosis == ("verification_queued", group[0])


@pytest.mark.parametrize("scenario", ["normal", "manual", "failed"])
def test_non_tcad_diagnosis_does_not_create_candidate_group(test_connection, scenario):
    request, _, _, event = arrange_diagnosis(test_connection, scenario)
    ingest(test_connection, request, event)
    assert test_connection.execute("SELECT count(*) FROM tcad_proposal_groups").fetchone() == (0,)


def test_disabled_auto_submit_preserves_review_without_queue(test_connection):
    request, _, _, event = arrange_diagnosis(test_connection)
    ingest(test_connection, request, event, enabled=False)
    assert test_connection.execute("SELECT count(*) FROM tcad_proposal_groups").fetchone() == (0,)
    assert test_connection.execute(
        "SELECT routing_status FROM diagnosis_results"
    ).fetchone() == ("review_required",)


def test_replayed_same_event_does_not_duplicate_candidates(test_connection):
    request, _, _, event = arrange_diagnosis(test_connection)
    first = ingest(test_connection, request, event)
    second = ingest(test_connection, request, event)
    assert second == first
    assert test_connection.execute("SELECT count(*) FROM tcad_proposal_groups").fetchone() == (1,)
    assert test_connection.execute(
        "SELECT count(*) FROM tcad_verification_candidates"
    ).fetchone() == (1,)


def test_invalid_second_candidate_rolls_back_entire_diagnosis(test_connection):
    request, _, response, event = arrange_diagnosis(test_connection)
    invalid = deepcopy(response["tcad_proposal"]["candidates"][0])
    invalid["process_parameters"].pop("body_dose")
    response["tcad_proposal"]["candidates"].append(invalid)
    with pytest.raises(ValidationError):
        ingest(test_connection, request, event)
    assert test_connection.execute("SELECT count(*) FROM events").fetchone() == (0,)
    assert test_connection.execute("SELECT count(*) FROM diagnosis_results").fetchone() == (0,)
    assert test_connection.execute("SELECT count(*) FROM tcad_proposal_groups").fetchone() == (0,)
