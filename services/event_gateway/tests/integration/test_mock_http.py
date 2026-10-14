import socket
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
import time
from uuid import uuid4

import httpx
import uvicorn

from event_gateway.tcad_client import TcadClient
from mock_tcad.app import create_app


def test_mock_tcad_real_http_and_request_idempotency(tmp_path):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    app = create_app(tmp_path / "tcad.sqlite")
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
        request_id = str(uuid4())
        body = {"request_id": request_id, "proposal_id": str(uuid4()),
                "targets": {key: {"min": 0.9, "max": 1.1}
                            for key in ("vth", "gm", "id_on", "bv")}}
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=3) as http:
            client = TcadClient(http)
            first = client.submit(body)
            assert client.submit(body).job_id == first.job_id
            result = client.poll(first.job_id)
        def submit_again(_):
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=3) as parallel_http:
                return TcadClient(parallel_http).submit(body).job_id

        with ThreadPoolExecutor(max_workers=4) as pool:
            accepted = list(pool.map(submit_again, range(4)))
        assert accepted == [first.job_id] * 4
        assert result["request_id"] == request_id
        assert result["result_origin"] == "mock"
    finally:
        server.should_exit = True
        thread.join(timeout=3)
