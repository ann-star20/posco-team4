from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from event_gateway.contracts import CorrectionProposal, VerificationResult


def proposal_data():
    current = {"oxide_thickness": 1.0, "body_dose": 1.0, "diffusion_time": 1.0, "epi_doping": 1.0}
    delta = {"oxide_thickness": -0.03, "body_dose": 0.05, "diffusion_time": 0.0, "epi_doping": 0.0}
    return {
        "proposal_id": str(uuid4()), "run_id": str(uuid4()),
        "representation": "normalized_ratio", "baseline_version": "demo-v1",
        "x_current": current, "delta_x": delta,
        "x_candidate": {"oxide_thickness": 0.97, "body_dose": 1.05, "diffusion_time": 1.0, "epi_doping": 1.0},
        "y_observed": {"vth": 1.08, "gm": 0.94, "id_on": 0.91, "bv": 0.99},
        "targets": {key: {"min": 0.9, "max": 1.1} for key in ("vth", "gm", "id_on", "bv")},
    }


def test_candidate_arithmetic_and_epi_control():
    assert CorrectionProposal.model_validate(proposal_data()).x_candidate["body_dose"] == 1.05
    invalid = proposal_data()
    invalid["x_candidate"]["body_dose"] = 1.07
    with pytest.raises(ValidationError):
        CorrectionProposal.model_validate(invalid)
    invalid = proposal_data()
    invalid["delta_x"]["epi_doping"] = 0.01
    with pytest.raises(ValidationError):
        CorrectionProposal.model_validate(invalid)


def test_finite_values_and_targets():
    invalid = proposal_data()
    invalid["x_current"]["body_dose"] = float("nan")
    with pytest.raises(ValidationError):
        CorrectionProposal.model_validate(invalid)
    invalid = proposal_data()
    invalid["targets"]["vth"]["min"] = 2.0
    with pytest.raises(ValidationError):
        CorrectionProposal.model_validate(invalid)


def test_result_requires_all_outputs():
    payload = {"request_id": str(uuid4()), "job_id": "job-1", "result_origin": "mock",
               "deck_template_version": "demo-v1",
               "y_verified": {"vth": 1.0, "gm": 1.0, "id_on": 1.0, "bv": 1.0}}
    assert VerificationResult.model_validate(payload).result_origin == "mock"
    invalid = deepcopy(payload)
    del invalid["y_verified"]["bv"]
    with pytest.raises(ValidationError):
        VerificationResult.model_validate(invalid)
