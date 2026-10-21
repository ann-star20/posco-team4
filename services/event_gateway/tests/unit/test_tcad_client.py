from uuid import uuid4

import httpx

import pytest

from event_gateway.tcad_client import TcadCandidateClient, TcadClient
from event_gateway.tcad_contracts import TcadVerificationRequest


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


def candidate_request():
    return TcadVerificationRequest.model_validate({
        "request_id": uuid4(),
        "process_parameters": {
            "body_dose": 7.7e12, "epi_doping": 1.7e16, "oxide_thickness": 0.06,
        },
        "predicted_outputs": {"vth": 2.1, "gm": 10, "id_on": 20, "bv": 40},
    })


def test_candidate_client_uses_authenticated_request_id_paths():
    outgoing = candidate_request()
    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(202, json={
                "request_id": str(outgoing.request_id), "status": "queued",
                "queue_position": 1, "estimated_seconds": 5400,
                "accepted_at": "2026-10-21T12:00:00Z",
            })
        return httpx.Response(200, json={
            "request_id": str(outgoing.request_id), "status": "running",
            "progress": {"stage": "iv", "stages": []},
        })

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://tcad.test") as http:
        client = TcadCandidateClient(http, "tomato-tcadv")
        accepted = client.submit(outgoing)
        status = client.poll(outgoing.request_id)

    assert accepted.request_id == outgoing.request_id
    assert status.status == "running"
    assert [request.url.path for request in requests] == [
        "/api/v1/tcad/verify", f"/api/v1/tcad/jobs/{outgoing.request_id}",
    ]
    assert all(request.headers["X-Fab-Token"] == "tomato-tcadv" for request in requests)
    assert "tomato-tcadv" not in repr(client)


def test_candidate_client_rejects_non_202_and_mismatched_identity():
    outgoing = candidate_request()
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={})
    ), base_url="http://tcad.test") as http:
        with pytest.raises(ValueError, match="202"):
            TcadCandidateClient(http, "token").submit(outgoing)

    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(202, json={
            "request_id": str(uuid4()), "status": "queued", "queue_position": 1,
            "estimated_seconds": 1, "accepted_at": "2026-10-21T12:00:00Z",
        })
    ), base_url="http://tcad.test") as http:
        with pytest.raises(ValueError, match="identity"):
            TcadCandidateClient(http, "token").submit(outgoing)


def test_candidate_client_validates_terminal_response_and_poll_identity():
    request_id = uuid4()
    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={
            "request_id": str(request_id), "status": "succeeded",
        })
    ), base_url="http://tcad.test") as http:
        with pytest.raises(ValueError):
            TcadCandidateClient(http, "token").poll(request_id)

    with httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={
            "request_id": str(uuid4()), "status": "running",
        })
    ), base_url="http://tcad.test") as http:
        with pytest.raises(ValueError, match="identity"):
            TcadCandidateClient(http, "token").poll(request_id)
