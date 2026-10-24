from uuid import uuid4

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
