from datetime import datetime, timezone
from uuid import uuid4

from event_gateway.contracts import EventCreate
from event_gateway.migrate import apply_migrations
from event_gateway.inference_jobs import submit_aoi_job
from event_gateway.repository import EventRepository

from pathlib import Path

MIGRATIONS = Path(__file__).parents[4] / "database" / "migrations"


def test_aoi_event_saves_image_locations_and_detections(test_connection):
    apply_migrations(test_connection, MIGRATIONS)
    run_id, event_id, job_id = uuid4(), uuid4(), uuid4()
    repository = EventRepository(test_connection)
    repository.ensure_run(run_id, "mock", "mock")
    image = {"artifact_id": str(uuid4()), "local_directory": "/home/jetson/project/smart_factory/result/aoi/a/1",
             "file_name": "annotated.jpg", "sha256": "f" * 64,
             "byte_size": 256, "width": 24, "height": 16}
    event = EventCreate(schema_version=1, event_id=event_id,
                        event_type="aoi.inspection.completed", source="jetson.aoi",
                        severity="warning", occurred_at=datetime.now(timezone.utc),
                        payload={"job_id": str(job_id), "attempt": 1, "device_id": "jetson-1",
                                 "verdict": "fail", "detections": [
                                     {"class_name": "bend", "confidence": .92}],
                                 "images": {"annotated": image}})
    receipt = repository.ingest(event, run_id)
    assert repository.ingest(event, run_id) == receipt
    saved = test_connection.execute(
        "SELECT file_name,local_path,sha256,source_event_id FROM aoi_image_artifacts"
    ).fetchall()
    assert saved == [("annotated.jpg", image["local_directory"] + "/annotated.jpg",
                      "f" * 64, event_id)]
    assert test_connection.execute("SELECT payload->'detections' FROM events WHERE event_id=%s",
                                   (event_id,)).fetchone()[0] == event.payload["detections"]


def test_aoi_result_completes_gateway_job_and_dispatch(test_connection):
    apply_migrations(test_connection, MIGRATIONS)
    run_id, request_id, event_id = uuid4(), uuid4(), uuid4()
    accepted = submit_aoi_job(test_connection, {
        "request_id": str(request_id), "run_id": str(run_id),
        "lot_id": "L1", "unit_id": "U1", "stage_id": "final_aoi", "stage_attempt": 1,
    }, "mock", "mock")
    event = EventCreate(schema_version=1, event_id=event_id,
                        event_type="aoi.inspection.completed", source="jetson.aoi",
                        severity="info", occurred_at=datetime.now(timezone.utc),
                        payload={"job_id": accepted["job_id"], "attempt": 1,
                                 "device_id": "wsl-jetson", "images": {}, "detections": [],
                                 "verdict": "review"})
    EventRepository(test_connection).ingest(event, run_id)
    job = test_connection.execute("SELECT status,result_event_id FROM inference_jobs WHERE job_id=%s",
                                  (accepted["job_id"],)).fetchone()
    assert job == ("completed", event_id)
    assert test_connection.execute("SELECT status FROM inference_dispatches WHERE job_id=%s",
                                   (accepted["job_id"],)).fetchone() == ("completed",)


def test_aoi_failure_closes_gateway_job_without_image_rows(test_connection):
    apply_migrations(test_connection, MIGRATIONS)
    run_id, event_id = uuid4(), uuid4()
    accepted = submit_aoi_job(test_connection, {
        "request_id": str(uuid4()), "run_id": str(run_id),
        "lot_id": "L1", "unit_id": "U1", "stage_id": "final_aoi", "stage_attempt": 1,
        "fixture_name": "missing.png",
    }, "mock", "mock")
    event = EventCreate(schema_version=1, event_id=event_id,
                        event_type="aoi.inspection.failed", source="jetson.aoi",
                        severity="error", occurred_at=datetime.now(timezone.utc),
                        payload={"job_id": accepted["job_id"], "attempt": 1,
                                 "error_code": "image_unreadable"})
    EventRepository(test_connection).ingest(event, run_id)
    assert test_connection.execute(
        "SELECT status,result_event_id FROM inference_jobs WHERE job_id=%s",
        (accepted["job_id"],)).fetchone() == ("failed", event_id)
    assert test_connection.execute(
        "SELECT status FROM inference_dispatches WHERE job_id=%s",
        (accepted["job_id"],)).fetchone() == ("completed",)
    assert test_connection.execute("SELECT count(*) FROM aoi_image_artifacts").fetchone() == (0,)


def test_aoi_event_saves_inference_timings_and_model_identity(test_connection):
    apply_migrations(test_connection, MIGRATIONS)
    run_id, event_id, job_id = uuid4(), uuid4(), uuid4()
    repository = EventRepository(test_connection)
    repository.ensure_run(run_id, "mock", "mock")
    part = {"file_name": "part.pt", "sha256": "a" * 64,
            "backend": "ultralytics-pytorch", "precision": "fp16", "device": "cuda:0"}
    defect = {"file_name": "defect.pt", "sha256": "b" * 64,
              "backend": "ultralytics-pytorch", "precision": "fp16", "device": "cuda:0"}
    event = EventCreate(schema_version=1, event_id=event_id,
                        event_type="aoi.inspection.completed", source="jetson.aoi",
                        severity="info", occurred_at=datetime.now(timezone.utc),
                        payload={"job_id": str(job_id), "attempt": 1, "device_id": "jetson-1",
                                 "verdict": "pass", "detections": [], "images": {},
                                 "timings": {"part_inference_ms": 4.25,
                                             "defect_inference_ms": 5.75,
                                             "total_processing_ms": 12.5},
                                 "models": {"part": part, "defect": defect}})

    repository.ingest(event, run_id)

    saved = test_connection.execute(
        "SELECT job_id,attempt,source_event_id,part_inference_ms,defect_inference_ms,"
        "total_processing_ms,part_model,defect_model FROM aoi_inference_metrics"
    ).fetchone()
    assert saved[:3] == (job_id, 1, event_id)
    assert tuple(float(value) for value in saved[3:6]) == (4.25, 5.75, 12.5)
    assert saved[6:] == (part, defect)
