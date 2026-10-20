from pathlib import Path
from uuid import uuid4

import pytest
from psycopg.errors import UniqueViolation

from event_gateway.migrate import apply_migrations
from event_gateway.inference_jobs import JobConflict, claim_due_aoi_requests, submit_aoi_job

ROOT = Path(__file__).parents[4]


def test_aoi_jobs_reject_concurrent_same_unit_stage(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    run_id = uuid4()
    test_connection.execute(
        "INSERT INTO integration_runs(run_id,tcad_mode,unity_mode,input_origin,baseline_version) "
        "VALUES (%s,'mock','mock','synthetic','demo-v1')", (run_id,))
    first_job = uuid4()
    test_connection.execute(
        "INSERT INTO inference_jobs(job_id,request_id,run_id,task_type,lot_id,unit_id,stage_id,"
        "stage_attempt,request_hash,request_body) VALUES (%s,%s,%s,'aoi','L1','U1','final_aoi',1,%s,'{}')",
        (first_job, uuid4(), run_id, "a" * 64))
    with pytest.raises(UniqueViolation):
        test_connection.execute(
            "INSERT INTO inference_jobs(job_id,request_id,run_id,task_type,lot_id,unit_id,stage_id,"
            "stage_attempt,request_hash,request_body) VALUES (%s,%s,%s,'aoi','L1','U1','final_aoi',1,%s,'{}')",
            (uuid4(), uuid4(), run_id, "b" * 64))
    test_connection.execute("UPDATE inference_jobs SET status='completed' WHERE job_id=%s", (first_job,))
    test_connection.execute(
        "INSERT INTO inference_jobs(job_id,request_id,run_id,task_type,lot_id,unit_id,stage_id,"
        "stage_attempt,request_hash,request_body) VALUES (%s,%s,%s,'aoi','L1','U1','final_aoi',2,%s,'{}')",
        (uuid4(), uuid4(), run_id, "c" * 64))
    assert test_connection.execute("SELECT count(*) FROM inference_jobs").fetchone() == (2,)


def test_submission_is_idempotent_and_queues_one_dispatch(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    request = {"request_id": str(uuid4()), "run_id": str(uuid4()),
               "lot_id": "L1", "unit_id": "U1", "stage_id": "final_aoi",
               "stage_attempt": 1}
    first = submit_aoi_job(test_connection, request, "mock", "mock")
    assert submit_aoi_job(test_connection, request, "mock", "mock") == first
    with pytest.raises(JobConflict):
        submit_aoi_job(test_connection, dict(request, lot_id="L2"), "mock", "mock")
    with pytest.raises(JobConflict):
        submit_aoi_job(test_connection, dict(request, request_id=str(uuid4())), "mock", "mock")
    other = submit_aoi_job(test_connection, dict(request, request_id=str(uuid4()),
                                                  unit_id="U2"), "mock", "mock")
    assert other["job_id"] != first["job_id"]
    assert test_connection.execute("SELECT count(*) FROM inference_dispatches").fetchone() == (2,)
    due = claim_due_aoi_requests(test_connection)
    assert {job["job_id"] for job in due} == {first["job_id"], other["job_id"]}
    assert claim_due_aoi_requests(test_connection) == []


def test_dispatch_carries_selected_fixture(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    request = {"request_id": str(uuid4()), "run_id": str(uuid4()),
               "lot_id": "L1", "unit_id": "U1", "stage_id": "final_aoi",
               "stage_attempt": 1, "fixture_name": "mosfet_ok.png"}
    submit_aoi_job(test_connection, request, "mock", "mock")
    assert claim_due_aoi_requests(test_connection)[0]["fixture_name"] == "mosfet_ok.png"
