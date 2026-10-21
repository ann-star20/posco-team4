from uuid import uuid4

import httpx

from fab_virtual_lot.ml_client import ModelHttpClient
from fab_virtual_lot.diagnosis_worker import DiagnosisRuntime, handle_ack


def request():
    return {
        "request_id": str(uuid4()), "job_id": str(uuid4()), "run_id": str(uuid4()),
        "attempt": 1, "task_type": "diagnosis", "diagnosis_mode": "prod",
        "model_contract_version": "fab-ml-v1",
        "input_payload": {"measurements": {"vth": 2.1, "gm": 10, "id_on": 20, "bv": None}},
    }


def test_diagnosis_client_calls_diagnose_endpoint_and_keeps_failed_response():
    item = request()
    response = {
        "request_id": item["request_id"], "job_id": item["job_id"],
        "model_contract_version": "fab-ml-v1", "model_version": "diagnosis-v1",
        "result_origin": "prod", "status": "failed", "anomaly_detected": None,
        "error_code": "OUT_OF_DOMAIN", "error_message": "outside", "result_payload": None,
        "metadata": {"model": {}, "timing_ms": {}, "stages": []}, "tcad_proposal": None,
    }
    def serve(http_request):
        assert str(http_request.url) == "http://127.0.0.1:8300/api/v1/diagnose"
        return httpx.Response(200, json=response)
    with httpx.Client(transport=httpx.MockTransport(serve)) as http:
        client = ModelHttpClient("prod", "http://127.0.0.1:8300", "/api/v1/diagnose", http)
        assert client(item)["error_code"] == "OUT_OF_DOMAIN"


def test_diagnosis_runtime_persists_completed_event(tmp_path):
    item = request()
    runtime = DiagnosisRuntime(tmp_path / "diagnosis.sqlite")
    runtime.accept(item)
    response = {
        "request_id": item["request_id"], "job_id": item["job_id"],
        "model_contract_version": "fab-ml-v1", "result_origin": "prod", "status": "succeeded",
    }
    event = runtime.process_next(lambda _: response)
    assert event["event_type"] == "diagnosis.completed"
    assert event["source"] == "jetson.diagnosis"
    assert event["payload"]["response"] == response
    assert len(runtime.pending_events()) == 1
    runtime.close()


def test_dead_letter_ack_stops_diagnosis_republish(tmp_path):
    item = request()
    runtime = DiagnosisRuntime(tmp_path / "diagnosis.sqlite")
    runtime.accept(item)
    event = runtime.process_next(lambda _: {
        "request_id": item["request_id"], "job_id": item["job_id"],
        "model_contract_version": "fab-ml-v1", "result_origin": "prod", "status": "succeeded",
    })
    handle_ack(runtime, {"status": "dead_lettered", "event_id": event["event_id"],
                         "run_id": event["run_id"], "sequence": None})
    assert runtime.pending_events() == []
    runtime.close()
