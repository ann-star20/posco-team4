import json
import socket
from threading import Thread
import time
from uuid import uuid4

import httpx
from psycopg.conninfo import make_conninfo
import uvicorn
from websockets.sync.client import connect

from event_gateway.app import create_app
from event_gateway.config import Settings
from event_gateway.contracts import EventCreate
from event_gateway.migrate import apply_migrations
from event_gateway.repository import EventRepository

from pathlib import Path


ROOT = Path(__file__).parents[4]


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_real_http_replay_and_websocket(test_connection):
    connection = test_connection
    apply_migrations(connection, ROOT / "database/migrations")
    run_id = uuid4()
    EventRepository(connection).ensure_run(run_id, "mock", "mock")
    schema = connection.execute("SHOW search_path").fetchone()[0]
    test_dsn = Settings.load(ROOT / ".env").test_database_url
    dsn = make_conninfo(test_dsn, options=f"-c search_path={schema}")
    app = create_app(Settings(database_url=dsn))
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port,
                                            log_level="error", lifespan="off"))
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.02)
        assert server.started
        event = EventCreate.model_validate({
            "schema_version": 1, "event_id": str(uuid4()),
            "event_type": "anomaly.detected", "source": "test", "severity": "warning",
            "occurred_at": "2026-10-14T00:00:00Z", "payload": {"lot_id": "LOT-1"},
        })
        receipt = EventRepository(connection).ingest(event, run_id)
        params = {"run_id": str(run_id), "after_sequence": 0}
        response = httpx.get(f"http://127.0.0.1:{port}/api/v1/events", params=params,
                             timeout=3)
        assert response.status_code == 200
        assert response.json()["events"][0]["sequence"] == receipt.sequence
        with connect(f"ws://127.0.0.1:{port}/api/v1/stream?"
                     f"run_id={run_id}&after_sequence=0", open_timeout=3) as websocket:
            message = json.loads(websocket.recv(timeout=3))
            assert message["event_id"] == str(event.event_id)
            assert message["sequence"] == receipt.sequence
        from importlib.util import find_spec
        assert find_spec('event_gateway.communication_check') is not None
        from event_gateway.communication_check import check_gateway
        checked = check_gateway(
            f'http://127.0.0.1:{port}',
            f'ws://127.0.0.1:{port}/api/v1/stream', run_id, timeout=3)
        assert checked['event_id'] == str(event.event_id)
        assert checked['sequence'] == receipt.sequence
    finally:
        server.should_exit = True
        thread.join(timeout=3)
