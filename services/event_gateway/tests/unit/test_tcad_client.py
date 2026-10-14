from uuid import uuid4

import httpx

from event_gateway.tcad_client import TcadClient


def test_submit_and_poll_use_same_request_id():
    request_id = str(uuid4())
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(202, json={"job_id": "job-1", "request_id": request_id})
        return httpx.Response(200, json={
            "status": "succeeded", "job_id": "job-1", "request_id": request_id,
            "result_origin": "mock", "deck_template_version": "demo-v1",
            "y_verified": {"vth": 1, "gm": 1, "id_on": 1, "bv": 1},
        })

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://tcad.test") as http:
        client = TcadClient(http)
        accepted = client.submit({"request_id": request_id})
        result = client.poll(accepted.job_id)
    assert accepted.request_id == request_id
    assert result["result_origin"] == "mock"
    assert requests[0].url.path == "/api/v1/verifications"
    assert requests[1].url.path == "/api/v1/verifications/job-1"


def test_invalid_accepted_body_fails():
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(202, json={"job_id": "job-1"})
    ), base_url="http://tcad.test") as http:
        with __import__("pytest").raises(ValueError):
            TcadClient(http).submit({"request_id": str(uuid4())})
