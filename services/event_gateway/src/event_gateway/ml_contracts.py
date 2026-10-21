"""Validation boundary for fab-ml-v1 model service responses."""

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


class ModelMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")
    model: ModelIdentity
    timing_ms: dict[str, float]
    stages: list[StageMetric]
    id_conditions: dict[str, float] | None = None


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
        return self


class DiagnosisDecision(BaseModel):
    model_config = ConfigDict(extra="allow")
    top_category: DiagnosisCategory
    category_probabilities: dict[DiagnosisCategory, float]


class Compensation(BaseModel):
    model_config = ConfigDict(extra="allow")
    route: DiagnosisRoute
    requires_human_approval: Literal[True]


class DiagnosisResult(BaseModel):
    model_config = ConfigDict(extra="allow")
    decision: DiagnosisDecision
    compensation: Compensation


class DiagnosisModelResponse(ValidatedModelResponse):
    result_payload: DiagnosisResult | None

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
    return ValidatedModelResponse.model_validate(response)
