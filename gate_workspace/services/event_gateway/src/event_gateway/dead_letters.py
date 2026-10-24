"""Persist unprocessable ROS messages without losing their original bytes."""

from hashlib import sha256
from uuid import UUID

import psycopg


def record_dead_letter(
    connection: psycopg.Connection, raw: str, error_code: str,
    event_id: UUID | None = None, run_id: UUID | None = None,
) -> str:
    message_hash = sha256(raw.encode("utf-8")).hexdigest()
    with connection.transaction():
        connection.execute(
            "INSERT INTO dead_letters(message_hash,event_id,run_id,raw_message,error_code) "
            "VALUES (%s,%s,%s,%s,%s) "
            "ON CONFLICT(message_hash) DO UPDATE SET "
            "attempt_count=dead_letters.attempt_count+1,last_seen_at=now(),"
            "error_code=EXCLUDED.error_code",
            (message_hash, event_id, run_id, raw, error_code[:100]),
        )
    return message_hash
