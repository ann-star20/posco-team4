from uuid import uuid4

import pytest
from pydantic import ValidationError

from event_gateway.contracts import OperationsEventCreate


VALID_SESSION_STARTED = {
    "schema_version": 1,
    "event_id": str(uuid4()),
    "event_type": "session.started",
    "source": "unity.factory",
    "severity": "info",
    "factory_session_id": str(uuid4()),
    "payload": {},
    "occurred_at": "2026-10-24T01:30:00.000Z",
}


def test_session_started_accepts_empty_payload() -> None:
    event = OperationsEventCreate.model_validate(VALID_SESSION_STARTED)

    assert event.event_type == "session.started"
    assert event.data_source == "simulation"


def test_equipment_registered_requires_equipment_id_and_kind() -> None:
    invalid = {
        **VALID_SESSION_STARTED,
        "event_type": "equipment.registered",
        "payload": {"equipment_id": "OX-01"},
    }

    with pytest.raises(ValidationError):
        OperationsEventCreate.model_validate(invalid)


def test_equipment_registered_rejects_unknown_kind() -> None:
    invalid = {
        **VALID_SESSION_STARTED,
        "event_type": "equipment.registered",
        "payload": {"equipment_id": "OX-01", "equipment_kind": "furnace"},
    }

    with pytest.raises(ValidationError):
        OperationsEventCreate.model_validate(invalid)


def test_equipment_registered_accepts_stocker_with_slot_count() -> None:
    valid = {
        **VALID_SESSION_STARTED,
        "event_type": "equipment.registered",
        "payload": {"equipment_id": "STOCKER-01", "equipment_kind": "stocker", "slot_count": 6},
    }

    event = OperationsEventCreate.model_validate(valid)

    assert event.payload["slot_count"] == 6


def test_lot_registered_wafer_route_requires_representative_wafer_id() -> None:
    invalid = {
        **VALID_SESSION_STARTED,
        "event_type": "lot.registered",
        "payload": {"lot_id": "LOT-001", "lot_kind": "wafer_route"},
    }

    with pytest.raises(ValidationError):
        OperationsEventCreate.model_validate(invalid)


def test_lot_registered_wafer_route_rejects_product_id() -> None:
    invalid = {
        **VALID_SESSION_STARTED,
        "event_type": "lot.registered",
        "payload": {
            "lot_id": "LOT-001", "lot_kind": "wafer_route",
            "representative_wafer_id": "WAFER-001", "product_id": "MOSFET-1",
        },
    }

    with pytest.raises(ValidationError):
        OperationsEventCreate.model_validate(invalid)


def test_lot_registered_aoi_product_requires_product_id() -> None:
    valid = {
        **VALID_SESSION_STARTED,
        "event_type": "lot.registered",
        "payload": {"lot_id": "LOT-AOI-1", "lot_kind": "aoi_product", "product_id": "MOSFET-1"},
    }

    event = OperationsEventCreate.model_validate(valid)

    assert event.payload["product_id"] == "MOSFET-1"


def test_lot_registered_rejects_unknown_lot_kind() -> None:
    invalid = {
        **VALID_SESSION_STARTED,
        "event_type": "lot.registered",
        "payload": {"lot_id": "LOT-001", "lot_kind": "batch"},
    }

    with pytest.raises(ValidationError):
        OperationsEventCreate.model_validate(invalid)


def test_rejects_unknown_event_type() -> None:
    invalid = {**VALID_SESSION_STARTED, "event_type": "equipment.state_changed"}

    with pytest.raises(ValidationError):
        OperationsEventCreate.model_validate(invalid)
