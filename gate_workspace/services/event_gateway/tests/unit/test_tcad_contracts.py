from math import inf, nan
from uuid import uuid4

import pytest
from pydantic import ValidationError

from event_gateway.tcad_contracts import (
    ProcessParameters,
    TcadAcceptance,
    TcadJobStatus,
    TcadVerificationRequest,
    make_tcad_request_id,
)


def valid_request():
    return {
        "request_id": str(uuid4()),
        "process_parameters": {
            "body_dose": 7.7e12,
            "epi_doping": 1.7e16,
            "oxide_thickness": 0.06,
        },
        "requested_outputs": ["vth", "gm", "id_on", "bv"],
        "predicted_outputs": {"vth": 2.1, "gm": 10.0, "id_on": 20.0, "bv": 40.0},
    }


@pytest.mark.parametrize("field,value", [
    ("body_dose", 0), ("epi_doping", -1), ("oxide_thickness", nan),
])
def test_process_parameters_must_be_finite_and_positive(field, value):
    values = {"body_dose": 7.7e12, "epi_doping": 1.7e16, "oxide_thickness": 0.06}
    values[field] = value
    with pytest.raises(ValidationError):
        ProcessParameters.model_validate(values)


def test_verification_request_rejects_unknown_or_duplicate_outputs():
    body = valid_request()
    body["requested_outputs"] = ["vth", "leakage"]
    with pytest.raises(ValidationError):
        TcadVerificationRequest.model_validate(body)

    body["requested_outputs"] = ["vth", "vth"]
    with pytest.raises(ValidationError):
        TcadVerificationRequest.model_validate(body)


def test_candidate_request_id_is_stable_per_proposal_and_index():
    proposal_id = uuid4()
    assert make_tcad_request_id(proposal_id, 0) == make_tcad_request_id(proposal_id, 0)
    assert make_tcad_request_id(proposal_id, 0) != make_tcad_request_id(proposal_id, 1)
    with pytest.raises(ValueError):
        make_tcad_request_id(proposal_id, -1)


def test_acceptance_and_job_status_allow_only_external_states():
    request_id = uuid4()
    accepted = TcadAcceptance.model_validate({
        "request_id": request_id, "status": "queued", "queue_position": 1,
        "estimated_seconds": 5400, "accepted_at": "2026-10-21T12:00:00Z",
    })
    assert accepted.status == "queued"

    payloads = {
        "queued": {},
        "running": {},
        "succeeded": {"result_payload": {"vth": 2.1, "gm": 10, "id_on": 20, "bv": 40}},
        "failed": {"error_code": "FAILED", "error_message": "failed"},
        "cancelled": {"cancelled_at": "2026-10-21T12:01:00Z"},
    }
    for status, payload in payloads.items():
        assert TcadJobStatus.model_validate({
            "request_id": request_id, "status": status, **payload,
        }).status == status
    with pytest.raises(ValidationError):
        TcadJobStatus.model_validate({"request_id": request_id, "status": "expired"})


def test_succeeded_job_requires_result_payload():
    with pytest.raises(ValidationError):
        TcadJobStatus.model_validate({"request_id": uuid4(), "status": "succeeded"})


@pytest.mark.parametrize("result_payload", [
    {},
    {"vth": 2.1},
    {"vth": 2.1, "gm": 10, "id_on": 20, "bv": nan},
    {"vth": 2.1, "gm": 10, "id_on": inf, "bv": 40},
])
def test_succeeded_job_requires_complete_finite_result_vector(result_payload):
    with pytest.raises(ValidationError):
        TcadJobStatus.model_validate({
            "request_id": uuid4(), "status": "succeeded",
            "result_payload": result_payload,
        })


def test_cancelled_job_requires_cancelled_at():
    with pytest.raises(ValidationError):
        TcadJobStatus.model_validate({"request_id": uuid4(), "status": "cancelled"})


def test_failed_job_requires_error_fields_and_null_result():
    with pytest.raises(ValidationError):
        TcadJobStatus.model_validate({"request_id": uuid4(), "status": "failed"})
    parsed = TcadJobStatus.model_validate({
        "request_id": uuid4(), "status": "failed", "error_code": "SILVACO_FAILED",
        "error_message": "deck failed", "result_payload": None,
    })
    assert parsed.error_code == "SILVACO_FAILED"
