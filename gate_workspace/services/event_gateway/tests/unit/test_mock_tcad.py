from uuid import uuid4

from fastapi.testclient import TestClient

from mock_tcad.app import RequestBody, create_app


def test_request_id_is_durable_and_scenario_is_deterministic(tmp_path):
    request_id = str(uuid4())
    body = {"request_id": request_id, "proposal_id": str(uuid4()),
            "targets": {key: {"min": 0.9, "max": 1.1} for key in ("vth", "gm", "id_on", "bv")}}
    path = tmp_path / "mock-tcad.sqlite"
    app = create_app(path, "pass")
    submit = next(route.endpoint for route in app.routes if route.path == "/api/v1/verifications")
    get = next(route.endpoint for route in app.routes if route.path == "/api/v1/verifications/{job_id}")
    first = submit(RequestBody.model_validate(body))
    job_id = first["job_id"]
    assert get(job_id)["y_verified"]["vth"] == 1.0
    restarted = create_app(path, "pass")
    submit_again = next(route.endpoint for route in restarted.routes
                        if route.path == "/api/v1/verifications")
    second = submit_again(RequestBody.model_validate(body))
    assert second["job_id"] == job_id


def candidate_body(request_id=None):
    return {
        "request_id": request_id or str(uuid4()),
        "job_id": str(uuid4()), "run_id": str(uuid4()), "lot_id": "LOT-1",
        "process_parameters": {
            "body_dose": 7.7e12, "epi_doping": 1.7e16, "oxide_thickness": 0.06,
        },
        "requested_outputs": ["vth", "gm", "id_on", "bv"],
        "predicted_outputs": {"vth": 2.1, "gm": 10, "id_on": 20, "bv": 40},
        "options": {"timeout_seconds": 5400},
    }


def test_v1_candidate_routes_require_token_and_progress_by_request_id(tmp_path):
    body = candidate_body()
    with TestClient(create_app(tmp_path / "v1.sqlite", api_token="secret")) as client:
        assert client.post("/api/v1/tcad/verify", json=body).status_code == 401
        accepted = client.post(
            "/api/v1/tcad/verify", json=body, headers={"X-Fab-Token": "secret"},
        )
        assert accepted.status_code == 202
        assert accepted.json()["status"] == "queued"

        first = client.get(
            f"/api/v1/tcad/jobs/{body['request_id']}", headers={"X-Fab-Token": "secret"},
        )
        second = client.get(
            f"/api/v1/tcad/jobs/{body['request_id']}", headers={"X-Fab-Token": "secret"},
        )
    assert first.json()["status"] == "running"
    assert first.json()["progress"]["stage"] == "iv"
    assert second.json()["status"] == "succeeded"
    assert second.json()["result_payload"] == body["predicted_outputs"]
    assert second.json()["metadata"]["result_origin"] == "mock"


def test_v1_submit_is_idempotent_and_changed_body_conflicts(tmp_path):
    body = candidate_body()
    with TestClient(create_app(tmp_path / "v1.sqlite")) as client:
        first = client.post("/api/v1/tcad/verify", json=body)
        again = client.post("/api/v1/tcad/verify", json=body)
        changed = candidate_body(body["request_id"])
        conflict = client.post("/api/v1/tcad/verify", json=changed)
    assert first.status_code == again.status_code == 202
    assert first.json()["accepted_at"] == again.json()["accepted_at"]
    assert conflict.status_code == 409


def test_v1_terminal_failure_and_cancelled_scenarios(tmp_path):
    for scenario, expected in (("failed", "failed"), ("cancelled", "cancelled")):
        body = candidate_body()
        with TestClient(create_app(tmp_path / f"{scenario}.sqlite", scenario=scenario)) as client:
            assert client.post("/api/v1/tcad/verify", json=body).status_code == 202
            client.get(f"/api/v1/tcad/jobs/{body['request_id']}")
            result = client.get(f"/api/v1/tcad/jobs/{body['request_id']}")
        assert result.json()["status"] == expected
