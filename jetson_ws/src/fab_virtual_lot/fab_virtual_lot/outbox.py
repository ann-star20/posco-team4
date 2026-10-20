"""On-device durable ROS event outbox."""

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import UUID


@dataclass(frozen=True)
class PendingEvent:
    event_id: UUID
    run_id: UUID
    body: str


class Outbox:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS pending("
            "event_id TEXT PRIMARY KEY,run_id TEXT NOT NULL,body TEXT NOT NULL,"
            "delivered_sequence INTEGER,created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        self.connection.commit()

    def enqueue(self, event_id: UUID, run_id: UUID, body: str) -> None:
        with self.lock, self.connection:
            existing = self.connection.execute(
                "SELECT run_id,body FROM pending WHERE event_id=?", (str(event_id),)
            ).fetchone()
            if existing is not None:
                if existing != (str(run_id), body):
                    raise ValueError("event_id has different content")
                return
            self.connection.execute(
                "INSERT INTO pending(event_id,run_id,body) VALUES (?,?,?)",
                (str(event_id), str(run_id), body),
            )

    def pending(self, limit: int = 100) -> list[PendingEvent]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT event_id,run_id,body FROM pending WHERE delivered_sequence IS NULL "
                "ORDER BY created_at,rowid LIMIT ?", (limit,)
            ).fetchall()
        return [PendingEvent(UUID(row[0]), UUID(row[1]), row[2]) for row in rows]

    def ack(self, event_id: UUID, run_id: UUID, sequence: int) -> bool:
        if sequence < 1:
            return False
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "UPDATE pending SET delivered_sequence=? WHERE event_id=? AND run_id=? "
                "AND delivered_sequence IS NULL", (sequence, str(event_id), str(run_id)),
            )
            return cursor.rowcount == 1

    def dead_letter(self, event_id: UUID, run_id: UUID) -> bool:
        """Stop retry only after Gateway has durably quarantined the raw body."""
        with self.lock, self.connection:
            cursor = self.connection.execute(
                "UPDATE pending SET delivered_sequence=-1 WHERE event_id=? AND run_id=? "
                "AND delivered_sequence IS NULL", (str(event_id), str(run_id)),
            )
            return cursor.rowcount == 1

    def close(self) -> None:
        with self.lock:
            self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
