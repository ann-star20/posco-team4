"""Validation boundary for fab-ml-v1 model service responses."""

from math import isfinite
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator


DiagnosisCategory = Literal[
    "normal", "dose", "epi", "oxide", "dose+epi", "dose+oxide",
    "epi+oxide", "dose+epi+oxide",
]
DiagnosisRoute = Literal["tcad_verify", "no_action", "manual"]
ModelStatus = Literal["succeeded", "failed"]
ErrorCode = Literal[
    "INVALID_INPUT", "UNSUPPORTED_CONTRACT_VERSION", "INFERENCE_FAILED",
    "OUT_OF_DOMAIN", "UNSUPPORTED_TASK_TYPE", "UNAUTHORIZED", "MODEL_NOT_READY",
]


class ModelIdentity(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    version: str
    artifact_hash: str
    git_commit: str | None = None
    device: str
    precision: str


class StageMetric(BaseModel):
    model_config = ConfigDict(extra="allow")
    stage: str
    status: Literal["succeeded", "failed"]
    duration_ms: float
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_duration(self):
        if not isfinite(self.duration_ms) or self.duration_ms < 0:
            raise ValueError("duration_ms must be finite and non-negative")
        return self


class ModelMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: ModelIdentity
    timing_ms: dict[str, float]
    stages: list[StageMetric]
    id_conditions: dict[str, float] | None = None

    @model_validator(mode="after")
    def validate_timings(self):
        if any(not isfinite(value) or value < 0 for value in self.timing_ms.values()):
            raise ValueError("timing values must be finite and non-negative")
        return self


class ElectricalOutputs(BaseModel):
    model_config = ConfigDict(extra="allow")
    vth: float
    gm: float
    id_on: float
    bv: float


class ValidatedModelResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    request_id: UUID
    job_id: UUID
    model_contract_version: Literal["fab-ml-v1"]
    model_version: str
    result_origin: Literal["mock", "prod"]
    status: ModelStatus
    anomaly_detected: bool | None
    result_payload: dict[str, Any] | None
    metadata: ModelMetadata
    error_code: ErrorCode | None = None
    error_message: str | None = None
    tcad_proposal: dict[str, Any] | None

    @model_validator(mode="after")
    def validate_status_payload(self):
        if self.status == "failed" and (not self.error_code or not self.error_message):
            raise ValueError("failed response requires top-level error fields")
        if self.status == "succeeded" and self.result_payload is None:
            raise ValueError("succeeded response requires result_payload")
        if self.status == "failed" and self.tcad_proposal is not None:
            raise ValueError("failed response requires null tcad_proposal")
        return self


class DiagnosisDecision(BaseModel):
    model_config = ConfigDict(extra="allow")
    top_category: DiagnosisCategory
    category_probabilities: dict[DiagnosisCategory, float]
    candidates: list["DiagnosisCandidate"] = []


class DiagnosisCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")
    category: DiagnosisCategory
    probability: float


class MeasurementAction(BaseModel):
    model_config = ConfigDict(extra="allow")
    action_code: str

    @model_validator(mode="after")
    def validate_code(self):
        if not self.action_code or not self.action_code.isascii():
            raise ValueError("action_code must be an English code")
        return self


class NextMeasurement(BaseModel):
    model_config = ConfigDict(extra="allow")
    recommendation_code: Literal[
        "none_needed", "no_improvement", "measure_bv", "more_wafers_2x", "more_wafers_4x"
    ]
    actions: list[MeasurementAction] = []


class Compensation(BaseModel):
    model_config = ConfigDict(extra="allow")
    route: DiagnosisRoute
    requires_human_approval: Literal[True]


class DiagnosisResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    decision: DiagnosisDecision
    compensation: Compensation
    next_measurement: NextMeasurement | None = None


class TcadCandidate(BaseModel):
    model_config = ConfigDict(extra="allow")
    predicted_outputs: ElectricalOutputs


class TcadProposal(BaseModel):
    model_config = ConfigDict(extra="allow")
    requires_human_approval: Literal[True]
    high_confidence: bool
    candidates: list[TcadCandidate]


class DiagnosisModelResponse(ValidatedModelResponse):
    result_payload: DiagnosisResult | None
    tcad_proposal: TcadProposal | None

    @model_validator(mode="after")
    def validate_route(self):
        if self.status != "succeeded":
            return self
        route = self.result_payload.compensation.route
        if route == "tcad_verify" and self.tcad_proposal is None:
            raise ValueError("tcad_verify requires tcad_proposal")
        if route != "tcad_verify" and self.tcad_proposal is not None:
            raise ValueError("non-TCAD route requires null tcad_proposal")
        return self


def validate_model_response(task_type: str, response: dict) -> ValidatedModelResponse:
    if task_type == "diagnosis":
        return DiagnosisModelResponse.model_validate(response)
    if task_type != "surrogate":
        raise ValueError("unsupported ML task type")
    parsed = ValidatedModelResponse.model_validate(response)
    if parsed.status == "succeeded":
        ElectricalOutputs.model_validate(parsed.result_payload)
    return parsed
