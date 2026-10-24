from pathlib import Path
from uuid import uuid4

from event_gateway.dead_letters import record_dead_letter
from event_gateway.migrate import apply_migrations


ROOT = Path(__file__).parents[4]


def test_dead_letter_preserves_raw_message_and_deduplicates(test_connection):
    connection = test_connection
    apply_migrations(connection, ROOT / "database/migrations")
    event_id, run_id = uuid4(), uuid4()
    raw = '{"bad": "event"}'
    record_dead_letter(connection, raw, "validation_error", event_id, run_id)
    record_dead_letter(connection, raw, "validation_error", event_id, run_id)
    assert connection.execute(
        "SELECT raw_message,error_code,attempt_count FROM dead_letters"
    ).fetchone() == (raw, "validation_error", 2)
