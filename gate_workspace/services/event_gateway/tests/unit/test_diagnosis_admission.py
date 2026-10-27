from contextlib import nullcontext
from uuid import uuid4

import event_gateway.app as app_module
from event_gateway.app import DiagnosisRequest, create_app, request_model_for_type
from event_gateway.config import Settings
from event_gateway.ros_adapter import publisher_for_task


def payload():
    return {
        "schema_version": 1, "request_id": str(uuid4()), "run_id": str(uuid4()),
        "lot_id": "LOT-1", "unit_id": "UNIT-1", "stage_attempt": 1,
        "model_contract_version": "fab-ml-v1",
        "input_payload": {"measurements": {"vth": 2.1, "gm": 10, "id_on": 20, "bv": None}},
    }


def configured_app(monkeypatch):
    accepted = {"job_id": str(uuid4()), "status": "queued"}
    monkeypatch.setattr(app_module.psycopg, "connect", lambda *_a, **_k: nullcontext(object()))
    monkeypatch.setattr(app_module, "submit_inference_job", lambda *_a, **_k: accepted)
    settings = Settings(database_url="postgresql://unused", unity_api_token="unity-test",
                        diagnosis_mode="prod")
    return create_app(settings), accepted


def test_authenticated_http_diagnosis_request_is_accepted(monkeypatch):
    app, accepted = configured_app(monkeypatch)
    endpoint = next(route.endpoint for route in app.routes
                    if route.path == "/api/v1/diagnosis-jobs")
    assert endpoint(DiagnosisRequest.model_validate(payload()), "unity-test") == accepted


def test_control_websocket_maps_diagnosis_message_to_contract():
    assert request_model_for_type("diagnosis.requested") is DiagnosisRequest
    assert request_model_for_type("unknown") is None


def test_ros_dispatch_chooses_diagnosis_publisher():
    class Node:
        inference_pub = object()
        surrogate_pub = object()
        diagnosis_pub = object()

    node = Node()
    assert publisher_for_task(node, "diagnosis") is node.diagnosis_pub
    assert publisher_for_task(node, "surrogate") is node.surrogate_pub
    assert publisher_for_task(node, "aoi") is node.inference_pub
