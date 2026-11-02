from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from event_gateway.contracts import OperationsEventCreate
from event_gateway.migrate import apply_migrations
from event_gateway.repository import OperationsRepository, StateConflict


ROOT = Path(__file__).parents[4]


def make_event(**overrides) -> OperationsEventCreate:
    fields = {
        "schema_version": 1,
        "event_id": uuid4(),
        "event_type": "equipment.state_changed",
        "source": "unity.factory",
        "severity": "info",
        "factory_session_id": uuid4(),
        "payload": {},
        "occurred_at": datetime.now(timezone.utc),
    }
    fields.update(overrides)
    return OperationsEventCreate(**fields)


def start_session(repo: OperationsRepository, session_id):
    repo.register_session_started(make_event(
        event_type="session.started", factory_session_id=session_id,
    ))


def state_event(session_id, equipment_id, state, state_version, prev_event_id, **extra):
    return make_event(
        factory_session_id=session_id, event_type="equipment.state_changed",
        payload={"equipment_id": equipment_id, "state": state,
                 "state_version": state_version,
                 "prev_event_id": str(prev_event_id) if prev_event_id is not None else None,
                 **extra},
    )


def test_sequential_versions_apply_in_order(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    start_session(repo, session_id)

    e1 = state_event(session_id, "OX-01", "running", 1, None)
    r1 = repo.apply_equipment_state_changed(e1)
    e2 = state_event(session_id, "OX-01", "idle", 2, e1.event_id)
    r2 = repo.apply_equipment_state_changed(e2)

    assert r2.sequence > r1.sequence
    row = test_connection.execute(
        "SELECT state_version, last_event_id FROM factory_object_versions "
        "WHERE factory_session_id=%s AND object_key='equipment:OX-01'", (session_id,),
    ).fetchone()
    assert row == (2, e2.event_id)


def test_version_3_before_2_is_rejected_then_2_then_3_succeeds(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    start_session(repo, session_id)
    e1 = state_event(session_id, "OX-01", "running", 1, None)
    repo.apply_equipment_state_changed(e1)

    e3 = state_event(session_id, "OX-01", "down", 3, uuid4())
    with pytest.raises(StateConflict) as exc_info:
        repo.apply_equipment_state_changed(e3)
    assert exc_info.value.expected_state_version == 2
    assert exc_info.value.last_event_id == e1.event_id

    e2 = state_event(session_id, "OX-01", "blocked", 2, e1.event_id)
    repo.apply_equipment_state_changed(e2)

    e3_retry = state_event(session_id, "OX-01", "down", 3, e2.event_id)
    repo.apply_equipment_state_changed(e3_retry)

    row = test_connection.execute(
        "SELECT state_version, last_event_id FROM factory_object_versions "
        "WHERE factory_session_id=%s AND object_key='equipment:OX-01'", (session_id,),
    ).fetchone()
    assert row == (3, e3_retry.event_id)


def test_concurrent_same_next_version_one_wins_one_conflicts(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    start_session(repo, session_id)
    e1 = state_event(session_id, "OX-01", "running", 1, None)
    repo.apply_equipment_state_changed(e1)

    branch_a = state_event(session_id, "OX-01", "idle", 2, e1.event_id)
    branch_b = state_event(session_id, "OX-01", "down", 2, e1.event_id)
    repo.apply_equipment_state_changed(branch_a)
    with pytest.raises(StateConflict):
        repo.apply_equipment_state_changed(branch_b)


def test_resending_identical_ack_lost_event_is_idempotent(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    start_session(repo, session_id)
    e1 = state_event(session_id, "OX-01", "running", 1, None)

    first = repo.apply_equipment_state_changed(e1)
    second = repo.apply_equipment_state_changed(e1)

    assert first.sequence == second.sequence


def test_state_and_disposition_versions_are_independent(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    start_session(repo, session_id)

    equip = state_event(session_id, "OX-01", "running", 1, None)
    repo.apply_equipment_state_changed(equip)

    activity = make_event(
        factory_session_id=session_id, event_type="lot.activity_changed",
        payload={"lot_id": "LOT-001", "activity_status": "waiting",
                 "state_version": 1, "prev_event_id": None},
    )
    disposition = make_event(
        factory_session_id=session_id, event_type="lot.disposition_changed",
        payload={"lot_id": "LOT-001", "disposition_status": "result_wait",
                 "state_version": 1, "prev_event_id": None},
    )
    repo.apply_lot_activity_changed(activity)
    repo.apply_lot_disposition_changed(disposition)

    rows = test_connection.execute(
        "SELECT object_key, state_version FROM factory_object_versions "
        "WHERE factory_session_id=%s ORDER BY object_key", (session_id,),
    ).fetchall()
    assert rows == [
        ("equipment:OX-01", 1),
        ("lot:LOT-001:activity", 1),
        ("lot:LOT-001:disposition", 1),
    ]


def test_state_changed_requires_active_session(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)

    with pytest.raises(Exception):
        repo.apply_equipment_state_changed(
            state_event(uuid4(), "OX-01", "running", 1, None)
        )
