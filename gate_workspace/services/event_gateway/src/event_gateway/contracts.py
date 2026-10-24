from datetime import datetime
from math import isclose, isfinite
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


Severity = Literal["debug", "info", "warning", "error", "critical"]


class EventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int
    event_id: UUID
    event_type: str
    source: str
    severity: Severity
    correlation_id: str | None = None
    causation_id: UUID | None = None
    payload: dict[str, Any]
    occurred_at: datetime

    @field_validator("schema_version")
    @classmethod
    def require_positive_schema_version(cls, value: int) -> int:
        if value < 1:
            raise ValueError("schema_version must be positive")
        return value

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must include a timezone")
        return value


class StoredEvent(EventCreate):
    sequence: int
    received_at: datetime

    @field_validator("sequence")
    @classmethod
    def require_positive_sequence(cls, value: int) -> int:
        if value < 1:
            raise ValueError("sequence must be positive")
        return value

    @field_validator("received_at")
    @classmethod
    def require_received_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("received_at must include a timezone")
        return value


X_KEYS = {"oxide_thickness", "body_dose", "diffusion_time", "epi_doping"}
Y_KEYS = {"vth", "gm", "id_on", "bv"}


class OutputRange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    min: float
    max: float

    @model_validator(mode="after")
    def validate_range(self):
        if not isfinite(self.min) or not isfinite(self.max) or self.min > self.max:
            raise ValueError("invalid output range")
        return self


def _validate_vector(value: dict[str, float], keys: set[str], positive: bool) -> dict[str, float]:
    if set(value) != keys:
        raise ValueError("incorrect vector keys")
    if not all(isfinite(number) and (not positive or number > 0) for number in value.values()):
        raise ValueError("vector values must be finite and positive where required")
    return value


class CorrectionProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    proposal_id: UUID
    run_id: UUID
    representation: Literal["normalized_ratio"]
    baseline_version: str
    x_current: dict[str, float]
    delta_x: dict[str, float]
    x_candidate: dict[str, float]
    y_observed: dict[str, float]
    y_predicted: dict[str, float] | None = None
    targets: dict[str, OutputRange]

    @model_validator(mode="after")
    def validate_values(self):
        _validate_vector(self.x_current, X_KEYS, True)
        _validate_vector(self.delta_x, X_KEYS, False)
        _validate_vector(self.x_candidate, X_KEYS, True)
        _validate_vector(self.y_observed, Y_KEYS, False)
        if self.y_predicted is not None:
            _validate_vector(self.y_predicted, Y_KEYS, False)
        if set(self.targets) != Y_KEYS:
            raise ValueError("incorrect target keys")
        if self.delta_x["epi_doping"] != 0:
            raise ValueError("epi_doping cannot be changed")
        for key in X_KEYS:
            if not isclose(self.x_candidate[key], self.x_current[key] + self.delta_x[key],
                           rel_tol=0, abs_tol=1e-9):
                raise ValueError("x_candidate differs from x_current + delta_x")
        return self


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_id: UUID
    job_id: str
    result_origin: Literal["mock", "prod"]
    deck_template_version: str
    y_verified: dict[str, float]

    @field_validator("y_verified")
    @classmethod
    def require_outputs(cls, value):
        return _validate_vector(value, Y_KEYS, False)
