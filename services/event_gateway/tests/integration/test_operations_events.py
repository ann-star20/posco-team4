from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from event_gateway.contracts import OperationsEventCreate
from event_gateway.migrate import apply_migrations
from event_gateway.repository import EventConflict, OperationsRepository


ROOT = Path(__file__).parents[4]


def make_event(**overrides) -> OperationsEventCreate:
    fields = {
        "schema_version": 1,
        "event_id": uuid4(),
        "event_type": "session.started",
        "source": "unity.factory",
        "severity": "info",
        "factory_session_id": uuid4(),
        "payload": {},
        "occurred_at": datetime.now(timezone.utc),
    }
    fields.update(overrides)
    return OperationsEventCreate(**fields)


def test_session_lifecycle_and_registration_populates_overview(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()

    repo.register_session_started(make_event(factory_session_id=session_id))
    repo.register_equipment(make_event(
        factory_session_id=session_id, event_type="equipment.registered",
        payload={"equipment_id": "OX-01", "equipment_kind": "oxidation"},
    ))
    repo.register_equipment(make_event(
        factory_session_id=session_id, event_type="equipment.registered",
        payload={"equipment_id": "STOCKER-01", "equipment_kind": "stocker", "slot_count": 6},
    ))
    repo.register_lot(make_event(
        factory_session_id=session_id, event_type="lot.registered",
        payload={"lot_id": "LOT-001", "lot_kind": "wafer_route",
                 "representative_wafer_id": "WAFER-001"},
    ))

    overview = repo.factory_overview(session_id)

    assert overview["status"] == "active"
    assert overview["ended_at"] is None
    assert {row["equipment_id"] for row in overview["equipment"]} == {"OX-01", "STOCKER-01"}
    stocker = next(row for row in overview["equipment"] if row["equipment_id"] == "STOCKER-01")
    assert stocker["slot_count"] == 6
    assert overview["lots"][0]["lot_id"] == "LOT-001"
    assert overview["lots"][0]["representative_wafer_id"] == "WAFER-001"

    repo.register_session_ended(make_event(factory_session_id=session_id, event_type="session.ended"))
    ended_overview = repo.factory_overview(session_id)
    assert ended_overview["status"] == "ended"
    assert ended_overview["ended_at"] is not None


def test_resending_same_event_id_is_idempotent(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    event = make_event()

    first = repo.register_session_started(event)
    second = repo.register_session_started(event)

    assert first.sequence == second.sequence


def test_different_event_registering_same_session_id_conflicts(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    repo.register_session_started(make_event(factory_session_id=session_id))

    with pytest.raises(EventConflict):
        repo.register_session_started(make_event(factory_session_id=session_id))


def test_different_event_registering_same_equipment_conflicts(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    repo.register_session_started(make_event(factory_session_id=session_id))
    repo.register_equipment(make_event(
        factory_session_id=session_id, event_type="equipment.registered",
        payload={"equipment_id": "OX-01", "equipment_kind": "oxidation"},
    ))

    with pytest.raises(EventConflict):
        repo.register_equipment(make_event(
            factory_session_id=session_id, event_type="equipment.registered",
            payload={"equipment_id": "OX-01", "equipment_kind": "oxidation"},
        ))


def test_session_ended_before_started_conflicts(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)

    with pytest.raises(EventConflict):
        repo.register_session_ended(make_event(event_type="session.ended"))


def test_equipment_registered_requires_active_session(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)

    with pytest.raises(EventConflict):
        repo.register_equipment(make_event(
            event_type="equipment.registered",
            payload={"equipment_id": "OX-01", "equipment_kind": "oxidation"},
        ))


def test_different_session_ids_do_not_see_each_others_equipment(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_a, session_b = uuid4(), uuid4()
    repo.register_session_started(make_event(factory_session_id=session_a))
    repo.register_session_started(make_event(factory_session_id=session_b))
    repo.register_equipment(make_event(
        factory_session_id=session_a, event_type="equipment.registered",
        payload={"equipment_id": "OX-01", "equipment_kind": "oxidation"},
    ))

    overview_b = repo.factory_overview(session_b)

    assert overview_b["equipment"] == []


def test_stored_event_payload_carries_factory_session_id(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    repo.register_session_started(make_event(factory_session_id=session_id))

    row = test_connection.execute(
        "SELECT run_id, payload FROM events WHERE event_type='session.started'"
    ).fetchone()

    assert row[0] is None
    assert row[1]["factory_session_id"] == str(session_id)
    assert row[1]["data_source"] == "simulation"


def test_factory_overview_returns_none_for_unknown_session(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)

    assert repo.factory_overview(uuid4()) is None
