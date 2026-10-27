from datetime import datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from event_gateway.contracts import EventCreate


VALID_EVENT = {
    "schema_version": 1,
    "event_id": "0199f0a4-5a8c-7b8e-9c10-0123456789ab",
    "event_type": "diagnosis.completed",
    "source": "jetson.orchestrator",
    "occurred_at": "2026-10-14T01:30:00.123Z",
    "severity": "info",
    "correlation_id": "lot-2026-0012",
    "causation_id": "0199f09f-1111-7222-8333-444444444444",
    "payload": {"lot_id": 12, "ambiguous": False},
}


def test_event_create_accepts_version_one() -> None:
    event = EventCreate.model_validate(VALID_EVENT)

    assert event.schema_version == 1
    assert event.event_id == UUID(VALID_EVENT["event_id"])
    assert event.occurred_at == datetime.fromisoformat("2026-10-14T01:30:00.123+00:00")
    assert event.severity == "info"
    assert event.payload == {"lot_id": 12, "ambiguous": False}


def test_event_create_rejects_unknown_severity() -> None:
    invalid = {**VALID_EVENT, "severity": "notice"}

    with pytest.raises(ValidationError):
        EventCreate.model_validate(invalid)


def test_event_create_requires_timezone() -> None:
    invalid = {**VALID_EVENT, "occurred_at": "2026-10-14T01:30:00.123"}

    with pytest.raises(ValidationError, match="timezone"):
        EventCreate.model_validate(invalid)


def test_event_create_does_not_accept_sequence() -> None:
    invalid = {**VALID_EVENT, "sequence": 99}

    with pytest.raises(ValidationError):
        EventCreate.model_validate(invalid)
