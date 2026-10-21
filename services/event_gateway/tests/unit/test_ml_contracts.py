from uuid import uuid4

import pytest
from pydantic import ValidationError

from event_gateway.ml_contracts import validate_model_response
from mock_surrogate.app import diagnose, predict


def base_response(status="succeeded"):
    return {
        "request_id": str(uuid4()),
        "job_id": str(uuid4()),
        "model_contract_version": "fab-ml-v1",
        "model_version": "mosfet-gp-2026-10-18",
        "result_origin": "prod",
        "status": status,
        "anomaly_detected": False if status == "succeeded" else None,
        "result_payload": {"vth": 2.1, "gm": 10.0, "id_on": 20.0, "bv": 40.0}
        if status == "succeeded" else None,
        "metadata": {
            "model": {"name": "mosfet-gp-surrogate", "version": "2026-10-18",
                      "artifact_hash": "sha256:abc", "git_commit": None,
                      "device": "cpu", "precision": "float64"},
            "timing_ms": {"inference_total": 2.5, "service_total": 3.0},
            "stages": [{"stage": "inference", "status": "succeeded", "duration_ms": 2.5}],
            "id_conditions": {"vgs_v": 4.0, "vds_v": 0.1, "temperature_c": 26.85},
        },
        "tcad_proposal": None,
    }


def test_predict_accepts_service_v11_metadata_without_git_commit():
    response = base_response()
    parsed = validate_model_response("surrogate", response)
    assert parsed.metadata.model.git_commit is None
    assert parsed.metadata.id_conditions["temperature_c"] == 26.85
    assert parsed.result_payload["id_on"] == 20.0


@pytest.mark.parametrize("route", ["no_action", "manual"])
def test_diagnosis_non_tcad_routes_require_null_proposal(route):
    response = base_response()
    response["result_payload"] = {
        "decision": {"top_category": "normal", "category_probabilities": {"normal": 1.0}},
        "compensation": {"route": route, "requires_human_approval": True},
    }
    assert validate_model_response("diagnosis", response).tcad_proposal is None


def test_diagnosis_tcad_route_requires_proposal():
    response = base_response()
    response["result_payload"] = {
        "decision": {"top_category": "oxide", "category_probabilities": {"oxide": 0.9}},
        "compensation": {"route": "tcad_verify", "requires_human_approval": True},
    }
    with pytest.raises(ValidationError):
        validate_model_response("diagnosis", response)


def test_out_of_domain_failed_response_keeps_top_level_error():
    response = base_response("failed")
    response.update(error_code="OUT_OF_DOMAIN", error_message="outside training domain")
    parsed = validate_model_response("surrogate", response)
    assert parsed.status == "failed"
    assert parsed.error_code == "OUT_OF_DOMAIN"


def test_old_error_code_and_korean_category_are_rejected():
    failed = base_response("failed")
    failed.update(error_code="INTERNAL", error_message="legacy")
    with pytest.raises(ValidationError):
        validate_model_response("surrogate", failed)

    diagnosis = base_response()
    diagnosis["result_payload"] = {
        "decision": {"top_category": "산화막", "category_probabilities": {"산화막": 1.0}},
        "compensation": {"route": "manual", "requires_human_approval": True},
    }
    with pytest.raises(ValidationError):
        validate_model_response("diagnosis", diagnosis)


def test_mock_surrogate_implements_v11_contract():
    request = {
        "request_id": str(uuid4()), "job_id": str(uuid4()), "run_id": str(uuid4()),
        "model_contract_version": "fab-ml-v1", "input_payload": {"scenario": "normal"},
    }
    parsed = validate_model_response("surrogate", predict(request))
    assert "id_on" in parsed.result_payload
    assert parsed.metadata.model.name == "mock-gp-surrogate"


@pytest.mark.parametrize("scenario,route,has_proposal", [
    ("normal", "no_action", False),
    ("manual", "manual", False),
    ("anomaly", "tcad_verify", True),
])
def test_mock_diagnosis_implements_routes(scenario, route, has_proposal):
    request = {
        "request_id": str(uuid4()), "job_id": str(uuid4()), "run_id": str(uuid4()),
        "model_contract_version": "fab-ml-v1", "input_payload": {"scenario": scenario},
    }
    parsed = validate_model_response("diagnosis", diagnose(request))
    assert parsed.result_payload.compensation.route == route
    assert (parsed.tcad_proposal is not None) is has_proposal


def test_surrogate_requires_all_four_named_outputs():
    response = base_response()
    response["result_payload"].pop("id_on")
    response["result_payload"]["id"] = 20.0
    with pytest.raises(ValidationError):
        validate_model_response("surrogate", response)


def test_diagnosis_rejects_korean_candidate_and_unknown_recommendation_code():
    response = base_response()
    response["result_payload"] = {
        "decision": {
            "top_category": "oxide", "category_probabilities": {"oxide": 1.0},
            "candidates": [{"category": "산화막", "probability": 1.0}],
        },
        "next_measurement": {"recommendation_code": "다시측정", "actions": []},
        "compensation": {"route": "manual", "requires_human_approval": True},
    }
    with pytest.raises(ValidationError):
        validate_model_response("diagnosis", response)


def test_tcad_proposal_requires_outputs_and_human_approval():
    response = base_response()
    response["result_payload"] = {
        "decision": {"top_category": "oxide", "category_probabilities": {"oxide": 1.0}},
        "compensation": {"route": "tcad_verify", "requires_human_approval": True},
    }
    response["tcad_proposal"] = {
        "requires_human_approval": False, "high_confidence": True,
        "candidates": [{"predicted_outputs": {"vth": 1, "gm": 2, "id_on": 3}}],
    }
    with pytest.raises(ValidationError):
        validate_model_response("diagnosis", response)


def test_failed_response_requires_null_proposal():
    response = base_response("failed")
    response.update(error_code="INFERENCE_FAILED", error_message="failed",
                    tcad_proposal={"candidates": []})
    with pytest.raises(ValidationError):
        validate_model_response("diagnosis", response)


def test_tcad_candidate_requires_process_parameters():
    response = base_response()
    response["anomaly_detected"] = True
    response["result_payload"] = {
        "decision": {"top_category": "oxide", "category_probabilities": {"oxide": 1.0}},
        "compensation": {"route": "tcad_verify", "requires_human_approval": True},
    }
    response["tcad_proposal"] = {
        "requires_human_approval": True, "high_confidence": True,
        "candidates": [{
            "predicted_outputs": {"vth": 1, "gm": 2, "id_on": 3, "bv": 4},
        }],
    }
    with pytest.raises(ValidationError):
        validate_model_response("diagnosis", response)


def test_tcad_proposal_rejects_empty_candidate_list():
    response = base_response()
    response["anomaly_detected"] = True
    response["result_payload"] = {
        "decision": {"top_category": "oxide", "category_probabilities": {"oxide": 1.0}},
        "compensation": {"route": "tcad_verify", "requires_human_approval": True},
    }
    response["tcad_proposal"] = {
        "requires_human_approval": True, "high_confidence": True, "candidates": [],
    }
    with pytest.raises(ValidationError):
        validate_model_response("diagnosis", response)
