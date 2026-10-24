from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
import psycopg

from event_gateway.app import create_app
from event_gateway.config import Settings
from event_gateway.migrate import apply_migrations

ROOT = Path(__file__).parents[4]


def test_http_and_ws_aoi_acceptance_share_durable_job(test_connection, monkeypatch):
    apply_migrations(test_connection, ROOT / "database/migrations")
    schema = test_connection.execute("SELECT current_schema()").fetchone()[0]
    url = Settings.load(ROOT / ".env").test_database_url
    real_connect = psycopg.connect
    monkeypatch.setattr("event_gateway.app.psycopg.connect",
                        lambda *a, **kw: real_connect(url, autocommit=True,
                                                      options=f"-c search_path={schema}"))
    client = TestClient(create_app(Settings(database_url=url, unity_api_token="test-token")))
    request = {"request_id": str(uuid4()), "run_id": str(uuid4()),
               "lot_id": "L1", "unit_id": "U1", "stage_id": "final_aoi",
               "stage_attempt": 1}
    assert client.post("/api/v1/inspection-jobs", json=request).status_code == 401
    unsafe = {**request, "fixture_name": "../secret.png"}
    assert client.post("/api/v1/inspection-jobs", json=unsafe,
                       headers={"x-unity-token": "test-token"}).status_code == 422
    first = client.post("/api/v1/inspection-jobs", json=request,
                        headers={"x-unity-token": "test-token"})
    assert first.status_code == 202
    assert client.post("/api/v1/inspection-jobs", json=request,
                       headers={"x-unity-token": "test-token"}).json() == first.json()
    with client.websocket_connect("/api/v1/control", headers={"x-unity-token": "test-token"}) as ws:
        ws.send_json({"type": "inspection.requested", **request})
        assert ws.receive_json()["job_id"] == first.json()["job_id"]
    assert test_connection.execute("SELECT count(*) FROM inference_jobs").fetchone() == (1,)
