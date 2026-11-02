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
        "event_type": "session.started",
        "source": "unity.factory",
        "severity": "info",
        "factory_session_id": uuid4(),
        "payload": {},
        "occurred_at": datetime.now(timezone.utc),
    }
    fields.update(overrides)
    return OperationsEventCreate(**fields)


def start_session(repo, session_id):
    repo.register_session_started(make_event(event_type="session.started", factory_session_id=session_id))


def equip_event(session_id, equipment_id, state, version, prev, occurred_at=None):
    return make_event(
        factory_session_id=session_id, event_type="equipment.state_changed",
        occurred_at=occurred_at or datetime.now(timezone.utc),
        payload={"equipment_id": equipment_id, "state": state, "state_version": version,
                 "prev_event_id": str(prev) if prev is not None else None},
    )


def open_intervals(conn, session_id, equipment_id):
    return conn.execute(
        "SELECT state, started_at, ended_at, start_event_id, end_event_id "
        "FROM equipment_state_intervals WHERE factory_session_id=%s AND equipment_id=%s "
        "ORDER BY started_at", (session_id, equipment_id),
    ).fetchall()


def test_first_transition_opens_interval_and_second_closes_it(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    start_session(repo, session_id)

    e1 = equip_event(session_id, "OX-01", "running", 1, None)
    repo.apply_equipment_state_changed(e1)
    rows = open_intervals(test_connection, session_id, "OX-01")
    assert len(rows) == 1
    assert rows[0][0] == "running"
    assert rows[0][2] is None  # ended_at NULL — still open
    assert rows[0][3] == e1.event_id

    e2 = equip_event(session_id, "OX-01", "idle", 2, e1.event_id)
    repo.apply_equipment_state_changed(e2)
    rows = open_intervals(test_connection, session_id, "OX-01")
    assert len(rows) == 2
    assert rows[0][2] == e2.occurred_at  # first interval closed by e2
    assert rows[0][4] == e2.event_id
    assert rows[1][0] == "idle"
    assert rows[1][2] is None  # second interval still open


def test_zero_length_interval_allowed_for_same_timestamp_transition(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    start_session(repo, session_id)
    same_ts = datetime.now(timezone.utc)

    e1 = equip_event(session_id, "OX-01", "running", 1, None, occurred_at=same_ts)
    repo.apply_equipment_state_changed(e1)
    e2 = equip_event(session_id, "OX-01", "idle", 2, e1.event_id, occurred_at=same_ts)
    repo.apply_equipment_state_changed(e2)

    rows = open_intervals(test_connection, session_id, "OX-01")
    assert rows[0][1] == rows[0][2] == same_ts  # zero-length first interval


def test_resending_identical_event_does_not_duplicate_interval(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    start_session(repo, session_id)
    e1 = equip_event(session_id, "OX-01", "running", 1, None)

    repo.apply_equipment_state_changed(e1)
    repo.apply_equipment_state_changed(e1)  # ACK lost, Unity resends identical event

    rows = open_intervals(test_connection, session_id, "OX-01")
    assert len(rows) == 1


def test_rejected_out_of_order_transition_does_not_touch_intervals(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    start_session(repo, session_id)
    e1 = equip_event(session_id, "OX-01", "running", 1, None)
    repo.apply_equipment_state_changed(e1)

    bad = equip_event(session_id, "OX-01", "down", 3, uuid4())
    with pytest.raises(StateConflict):
        repo.apply_equipment_state_changed(bad)

    rows = open_intervals(test_connection, session_id, "OX-01")
    assert len(rows) == 1
    assert rows[0][2] is None  # still open, untouched by the rejected transition


def test_concurrent_branches_only_one_interval_created(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    start_session(repo, session_id)
    e1 = equip_event(session_id, "OX-01", "running", 1, None)
    repo.apply_equipment_state_changed(e1)

    branch_a = equip_event(session_id, "OX-01", "idle", 2, e1.event_id)
    branch_b = equip_event(session_id, "OX-01", "down", 2, e1.event_id)
    repo.apply_equipment_state_changed(branch_a)
    with pytest.raises(StateConflict):
        repo.apply_equipment_state_changed(branch_b)

    rows = open_intervals(test_connection, session_id, "OX-01")
    assert len(rows) == 2
    assert rows[1][0] == "idle"


def test_lot_activity_and_disposition_intervals_are_independent(test_connection):
    apply_migrations(test_connection, ROOT / "database/migrations")
    repo = OperationsRepository(test_connection)
    session_id = uuid4()
    start_session(repo, session_id)

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
        "SELECT category, status FROM lot_activity_intervals "
        "WHERE factory_session_id=%s ORDER BY category", (session_id,),
    ).fetchall()
    assert rows == [("activity", "waiting"), ("disposition", "result_wait")]
