"""Contracts for the asynchronous external TCAD verification service."""

from datetime import datetime
from math import isfinite
from typing import Any, Literal
from uuid import UUID, UUID as UUIDType, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator


TCAD_REQUEST_NAMESPACE = UUIDType("cfc8f620-b1dc-5c85-92d8-22bb48611651")
RequestedOutput = Literal["vth", "gm", "id_on", "bv"]
ExternalStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class ProcessParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body_dose: float
    epi_doping: float
    oxide_thickness: float

    @model_validator(mode="after")
    def validate_positive_finite(self):
        if any(not isfinite(value) or value <= 0 for value in (
            self.body_dose, self.epi_doping, self.oxide_thickness,
        )):
            raise ValueError("process parameters must be finite and positive")
        return self


class PredictedOutputs(BaseModel):
    model_config = ConfigDict(extra="allow")
    vth: float
    gm: float
    id_on: float
    bv: float

    @model_validator(mode="after")
    def validate_finite(self):
        if any(not isfinite(value) for value in (self.vth, self.gm, self.id_on, self.bv)):
            raise ValueError("predicted outputs must be finite")
        return self


class VerificationOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeout_seconds: int = Field(default=5400, gt=0)


class TcadVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    process_parameters: ProcessParameters
    requested_outputs: list[RequestedOutput] = Field(
        default_factory=lambda: ["vth", "gm", "id_on", "bv"], min_length=1,
    )
    job_id: UUID | None = None
    run_id: UUID | None = None
    lot_id: str | None = None
    predicted_outputs: PredictedOutputs | None = None
    options: VerificationOptions = Field(default_factory=VerificationOptions)

    @model_validator(mode="after")
    def validate_unique_outputs(self):
        if len(self.requested_outputs) != len(set(self.requested_outputs)):
            raise ValueError("requested_outputs must be unique")
        return self


class TcadAcceptance(BaseModel):
    model_config = ConfigDict(extra="allow")
    request_id: UUID
    status: Literal["queued"]
    queue_position: int = Field(ge=0)
    estimated_seconds: int = Field(ge=0)
    accepted_at: datetime


class TcadJobStatus(BaseModel):
    model_config = ConfigDict(extra="allow")
    request_id: UUID
    status: ExternalStatus
    queue_position: int | None = Field(default=None, ge=0)
    estimated_seconds: int | None = Field(default=None, ge=0)
    progress: dict[str, Any] | None = None
    result_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    prediction_error: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    cancelled_at: datetime | None = None

    @model_validator(mode="after")
    def validate_terminal_payload(self):
        if self.status == "succeeded" and self.result_payload is None:
            raise ValueError("succeeded status requires result_payload")
        if self.status == "failed":
            if not self.error_code or not self.error_message:
                raise ValueError("failed status requires error fields")
            if self.result_payload is not None:
                raise ValueError("failed status requires null result_payload")
        return self


def make_tcad_request_id(proposal_id: UUID, candidate_index: int) -> UUID:
    if candidate_index < 0:
        raise ValueError("candidate_index must be non-negative")
    return uuid5(TCAD_REQUEST_NAMESPACE, f"{proposal_id}:tcad-candidate:{candidate_index}")
