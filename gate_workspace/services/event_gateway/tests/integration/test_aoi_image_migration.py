from pathlib import Path
from uuid import uuid4

import pytest
from psycopg.errors import CheckViolation, UniqueViolation

from event_gateway.migrate import apply_migrations

DIRECTORY = Path(__file__).parents[4] / "database" / "migrations"


def prepare(connection):
    apply_migrations(connection, DIRECTORY)
    assert connection.execute("SELECT to_regclass('aoi_image_artifacts')").fetchone()[0], "AOI image metadata table missing"


def insert_image(connection, **overrides):
    values = dict(artifact_id=uuid4(), job_id=uuid4(), attempt=1,
                  image_role="annotated", device_id="jetson-1",
                  local_directory="/home/jetson/project/smart_factory/result/aoi/job/1",
                  file_name="annotated.jpg", sha256="a" * 64,
                  byte_size=1024, width=1920, height=1080)
    values.update(overrides)
    columns = ",".join(values)
    return connection.execute(
        f"INSERT INTO aoi_image_artifacts ({columns}, captured_at) VALUES "
        f"({','.join(['%s'] * len(values))}, now()) RETURNING local_path, cloud_status",
        list(values.values()),
    ).fetchone()


def test_image_path_round_trip_and_repeat_migration(test_connection):
    prepare(test_connection)
    assert insert_image(test_connection) == (
        "/home/jetson/project/smart_factory/result/aoi/job/1/annotated.jpg", "disabled")
    assert apply_migrations(test_connection, DIRECTORY) == []


def test_duplicate_device_path_and_job_role_rejected(test_connection):
    prepare(test_connection)
    job = uuid4()
    insert_image(test_connection, job_id=job)
    with pytest.raises(UniqueViolation):
        insert_image(test_connection)
    with pytest.raises(UniqueViolation):
        insert_image(test_connection, job_id=job, file_name="other.jpg")


@pytest.mark.parametrize("changes", [
    {"file_name": "../result.jpg"}, {"file_name": "result.png"},
    {"local_directory": "relative/path"}, {"local_directory": "/tmp/../data"},
    {"byte_size": 0}, {"sha256": "bad"}, {"attempt": 0},
    {"cloud_status": "uploaded"}, {"local_status": "deleted"},
])
def test_invalid_artifact_rejected(test_connection, changes):
    prepare(test_connection)
    with pytest.raises(CheckViolation):
        insert_image(test_connection, **changes)


def test_cloud_location_preserves_local_provenance(test_connection):
    prepare(test_connection)
    result = insert_image(test_connection, cloud_status="uploaded", cloud_provider="gcs",
                          cloud_object_key="bucket/aoi/job/annotated.jpg",
                          cloud_uploaded_at="2026-10-16T00:00:00Z", local_status="deleted")
    assert result[0].endswith("/annotated.jpg")
    assert result[1] == "uploaded"
