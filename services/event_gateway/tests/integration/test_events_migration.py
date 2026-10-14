import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg.errors import UniqueViolation


MIGRATION = (
    Path(__file__).parents[4] / "database" / "migrations" / "001_create_events.sql"
)
DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://fab_events:fab_events_test_only@localhost:55432/fab_events_test",
)


def test_events_migration_enforces_unique_event_id_and_server_sequence() -> None:
    migration_sql = MIGRATION.read_text(encoding="utf-8")

    with psycopg.connect(DATABASE_URL, autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS events")
        connection.execute(migration_sql)

        first_event_id = uuid4()
        second_event_id = uuid4()
        first_sequence = _insert_event(connection, first_event_id)
        second_sequence = _insert_event(connection, second_event_id)

        assert second_sequence > first_sequence

        with pytest.raises(UniqueViolation):
            _insert_event(connection, first_event_id)


def _insert_event(connection: psycopg.Connection, event_id) -> int:
    row = connection.execute(
        """
        INSERT INTO events (
            event_id, schema_version, event_type, source, severity,
            correlation_id, payload, occurred_at
        )
        VALUES (%s, 1, 'diagnosis.completed', 'test', 'info', 'lot-1', '{}', now())
        RETURNING sequence
        """,
        (event_id,),
    ).fetchone()
    assert row is not None
    return row[0]
