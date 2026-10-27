"""Durable AOI inbox and event outbox shared by Jetson and WSL ROS nodes."""

from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import UUID, uuid5

from .aoi_pipeline import AoiConfig, inspect_image
from .outbox import Outbox


class AoiRuntime:
    def __init__(self, db_path: Path, config: AoiConfig):
        self.outbox = Outbox(db_path)
        self.db = self.outbox.connection
        self.config = config
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS aoi_inbox ("
            "request_id TEXT PRIMARY KEY,job_id TEXT NOT NULL UNIQUE,run_id TEXT NOT NULL,"
            "body TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'queued',"
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        self.db.commit()

    def accept(self, request: dict) -> bool:
        for name in ("request_id", "job_id", "run_id"):
            UUID(request[name])
        if request.get("task_type") != "aoi" or int(request["attempt"]) < 1:
            raise ValueError("invalid AOI request")
        body = json.dumps(request, sort_keys=True, separators=(",", ":"))
        with self.db:
            row = self.db.execute("SELECT body FROM aoi_inbox WHERE request_id=?",
                                  (request["request_id"],)).fetchone()
            if row is not None:
                return row[0] == body
            self.db.execute(
                "INSERT INTO aoi_inbox(request_id,job_id,run_id,body) VALUES (?,?,?,?)",
                (request["request_id"], request["job_id"], request["run_id"], body),
            )
        return True

    def process_next(self, capture, part_model, defect_model) -> dict | None:
        row = self.db.execute(
            "SELECT request_id,body FROM aoi_inbox WHERE status='queued' "
            "ORDER BY created_at,rowid LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        request_id, body = row
        request = json.loads(body)
        job_id = UUID(request["job_id"])
        run_id = UUID(request["run_id"])
        attempt = int(request["attempt"])
        try:
            frame = capture(request)
        except ValueError:
            event_id = uuid5(job_id, f"aoi.inspection.failed:{attempt}")
            event = {
                "schema_version": 1, "event_id": str(event_id), "run_id": str(run_id),
                "event_type": "aoi.inspection.failed", "source": "jetson.aoi",
                "severity": "error", "correlation_id": str(request_id),
                "occurred_at": datetime.now(timezone.utc).isoformat(),
                "payload": {"job_id": str(job_id), "attempt": attempt,
                            "request_id": str(request_id), "lot_id": request.get("lot_id", ""),
                            "error_code": "image_unreadable"},
            }
            with self.db:
                self.db.execute(
                    "INSERT INTO pending(event_id,run_id,body) VALUES (?,?,?) "
                    "ON CONFLICT(event_id) DO NOTHING",
                    (str(event_id), str(run_id), json.dumps(event, sort_keys=True, separators=(",", ":"))),
                )
                self.db.execute("UPDATE aoi_inbox SET status='failed' WHERE request_id=?",
                                (request_id,))
            return event
        result = inspect_image(frame, job_id, attempt, self.config, part_model, defect_model)
        event_id = uuid5(job_id, f"aoi.inspection.completed:{attempt}")
        event = {
            "schema_version": 1, "event_id": str(event_id), "run_id": str(run_id),
            "event_type": "aoi.inspection.completed", "source": "jetson.aoi",
            "severity": "warning" if result["verdict"] != "pass" else "info",
            "correlation_id": str(request_id),
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {**result, "request_id": str(request_id),
                        "fixture_name": request.get("fixture_name"),
                        "lot_id": request.get("lot_id", "")},
        }
        event_body = json.dumps(event, sort_keys=True, separators=(",", ":"))
        with self.db:
            self.db.execute(
                "INSERT INTO pending(event_id,run_id,body) VALUES (?,?,?) "
                "ON CONFLICT(event_id) DO NOTHING",
                (str(event_id), str(run_id), event_body),
            )
            self.db.execute("UPDATE aoi_inbox SET status='completed' WHERE request_id=?",
                            (request_id,))
        return event

    def pending_events(self) -> list[tuple[str, str, str]]:
        return self.db.execute(
            "SELECT event_id,run_id,body FROM pending WHERE delivered_sequence IS NULL "
            "ORDER BY created_at,rowid LIMIT 100"
        ).fetchall()

    def ack(self, event_id: str, run_id: str, sequence: int) -> bool:
        return self.outbox.ack(UUID(event_id), UUID(run_id), sequence)

    def close(self):
        self.outbox.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
