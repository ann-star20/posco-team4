from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


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
