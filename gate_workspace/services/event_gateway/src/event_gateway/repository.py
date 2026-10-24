"""Transactional event and correction storage."""

from dataclasses import dataclass
from datetime import timezone
import json
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from .contracts import CorrectionProposal, EventCreate
from .command_auth import verify_applied_receipt


class EventConflict(ValueError):
    pass


@dataclass(frozen=True)
class Receipt:
    event_id: UUID
    run_id: UUID
    sequence: int


class EventRepository:
    def __init__(self, connection: psycopg.Connection, command_signing_key: str = ""):
        self.connection = connection
        self.command_signing_key = command_signing_key

    def ensure_run(
        self, run_id: UUID, tcad_mode: str, unity_mode: str,
        input_origin: str = "synthetic", baseline_version: str = "demo-v1"
    ) -> None:
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO integration_runs(run_id,tcad_mode,unity_mode,input_origin,baseline_version)"
                " VALUES (%s,%s,%s,%s,%s) ON CONFLICT (run_id) DO NOTHING",
                (run_id, tcad_mode, unity_mode, input_origin, baseline_version),
            )
            actual = self.connection.execute(
                "SELECT tcad_mode,unity_mode,input_origin,baseline_version "
                "FROM integration_runs WHERE run_id=%s", (run_id,),
            ).fetchone()
            if actual != (tcad_mode, unity_mode, input_origin, baseline_version):
                raise EventConflict("run_id mode or baseline differs")

    def resolve_run(
        self, run_id: UUID, tcad_mode: str, unity_mode: str,
        input_origin: str = "synthetic", baseline_version: str = "demo-v1",
    ) -> tuple[str, str, str, str]:
        """Pin new runs; preserve existing modes for delayed/retried events."""
        with self.connection.transaction():
            self.connection.execute(
                "INSERT INTO integration_runs(run_id,tcad_mode,unity_mode,input_origin,baseline_version) "
                "VALUES (%s,%s,%s,%s,%s) ON CONFLICT(run_id) DO NOTHING",
                (run_id, tcad_mode, unity_mode, input_origin, baseline_version),
            )
            return self.connection.execute(
                "SELECT tcad_mode,unity_mode,input_origin,baseline_version "
                "FROM integration_runs WHERE run_id=%s", (run_id,),
            ).fetchone()

    def ingest(self, event: EventCreate, run_id: UUID) -> Receipt:
        with self.connection.transaction():
            receipt = self._insert_event(event, run_id)
            if event.event_type == "aoi.inspection.completed" and event.source == "jetson.aoi":
                self._store_aoi_images(event)
                self._store_aoi_metrics(event)
                self._complete_aoi_job(event, run_id)
            if event.event_type == "aoi.inspection.failed" and event.source == "jetson.aoi":
                self._fail_aoi_job(event, run_id)
            if event.event_type == "correction.applied":
                self._mark_applied(event, run_id)
            return receipt

    def _complete_aoi_job(self, event: EventCreate, run_id: UUID) -> None:
        payload = event.payload
        job_id = UUID(payload["job_id"])
        row = self.connection.execute(
            "SELECT run_id,stage_attempt,status,result_event_id FROM inference_jobs "
            "WHERE job_id=%s FOR UPDATE", (job_id,),
        ).fetchone()
        if row is None:
            return  # Direct ROS diagnostic request; no Gateway admission row.
        if row[0] != run_id or row[1] != int(payload["attempt"]):
            raise EventConflict("AOI result does not match job")
        if row[3] is not None and row[3] != event.event_id:
            raise EventConflict("AOI job already completed by another event")
        if row[2] == "cancelled":
            return
        self.connection.execute(
            "UPDATE inference_jobs SET status='completed',result_event_id=%s,updated_at=now() "
            "WHERE job_id=%s", (event.event_id, job_id),
        )
        self.connection.execute(
            "UPDATE inference_dispatches SET status='completed' WHERE job_id=%s", (job_id,),
        )

    def _fail_aoi_job(self, event: EventCreate, run_id: UUID) -> None:
        payload = event.payload
        job_id = UUID(payload["job_id"])
        row = self.connection.execute(
            "SELECT run_id,stage_attempt,status,result_event_id FROM inference_jobs "
            "WHERE job_id=%s FOR UPDATE", (job_id,),
        ).fetchone()
        if row is None:
            return
        if row[0] != run_id or row[1] != int(payload["attempt"]):
            raise EventConflict("AOI failure does not match job")
        if row[3] is not None and row[3] != event.event_id:
            raise EventConflict("AOI job already closed by another event")
        if row[2] == "cancelled":
            return
        self.connection.execute(
            "UPDATE inference_jobs SET status='failed',result_event_id=%s,updated_at=now() "
            "WHERE job_id=%s", (event.event_id, job_id),
        )
        self.connection.execute(
            "UPDATE inference_dispatches SET status='completed' WHERE job_id=%s", (job_id,),
        )

    def _store_aoi_images(self, event: EventCreate) -> None:
        payload = event.payload
        job_id = UUID(payload["job_id"])
        attempt = int(payload["attempt"])
        device_id = str(payload["device_id"])
        for role, image in payload["images"].items():
            self.connection.execute(
                "INSERT INTO aoi_image_artifacts (artifact_id,job_id,attempt,source_event_id,"
                "image_role,device_id,local_directory,file_name,sha256,byte_size,width,height,captured_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (artifact_id) DO NOTHING",
                (UUID(image["artifact_id"]), job_id, attempt, event.event_id,
                 role, device_id, image["local_directory"], image["file_name"],
                 image["sha256"], image["byte_size"], image["width"], image["height"],
                 event.occurred_at),
            )

    def _store_aoi_metrics(self, event: EventCreate) -> None:
        payload = event.payload
        timings = payload.get("timings")
        models = payload.get("models")
        if not timings or not models:
            return
        self.connection.execute(
            "INSERT INTO aoi_inference_metrics (job_id,attempt,source_event_id,"
            "part_inference_ms,defect_inference_ms,total_processing_ms,part_model,defect_model) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (job_id,attempt) DO NOTHING",
            (UUID(payload["job_id"]), int(payload["attempt"]), event.event_id,
             timings["part_inference_ms"], timings["defect_inference_ms"],
             timings["total_processing_ms"], Jsonb(models["part"]), Jsonb(models["defect"])),
        )

    def _mark_applied(self, event: EventCreate, run_id: UUID) -> None:
        if event.source != "jetson.virtual_lot":
            raise EventConflict("untrusted correction applied source")
        if (event.payload.get("run_id") != str(run_id)
                or not verify_applied_receipt(event.payload, event.event_id,
                                              self.command_signing_key)):
            raise EventConflict("invalid applied receipt signature")
        try:
            command_id = UUID(event.payload["command_id"])
            proposal_id = UUID(event.payload["proposal_id"])
            lot = event.payload["effective_from_lot"]
        except (KeyError, TypeError, ValueError) as exc:
            raise EventConflict("invalid command ACK") from exc
        row = self.connection.execute(
            "SELECT run_id,proposal_id,effective_from_lot,status,applied_event_id "
            "FROM commands WHERE command_id=%s AND delivery_target='jetson' FOR UPDATE", (command_id,),
        ).fetchone()
        if row is None or row[:3] != (run_id, proposal_id, lot):
            raise EventConflict("command ACK does not match pending command")
        if row[3] == "applied":
            if row[4] != event.event_id:
                raise EventConflict("command applied by another event")
            return
        if row[3] not in {"pending", "sent"}:
            raise EventConflict("command is not awaiting application")
        self.connection.execute(
            "UPDATE commands SET status='applied',applied_event_id=%s,applied_at=now(),"
            "lease_token=NULL,lease_until=NULL WHERE command_id=%s",
            (event.event_id, command_id),
        )
        self.connection.execute(
            "UPDATE correction_proposals SET status='applied' WHERE proposal_id=%s",
            (proposal_id,),
        )

    def _insert_event(self, event: EventCreate, run_id: UUID) -> Receipt:
        self.connection.execute("SELECT pg_advisory_xact_lock(4184, 1)")
        record = self.connection.execute(
            "SELECT sequence,run_id,schema_version,event_type,source,severity,"
            "correlation_id,causation_id,payload,occurred_at "
            "FROM events WHERE event_id=%s", (event.event_id,),
        ).fetchone()
        if record:
            existing = (
                record[1], record[2], record[3], record[4], record[5], record[6],
                record[7], record[8], record[9].astimezone(timezone.utc)
            )
            incoming = (
                run_id, event.schema_version, event.event_type, event.source,
                event.severity, event.correlation_id, event.causation_id,
                event.payload, event.occurred_at.astimezone(timezone.utc)
            )
            if existing != incoming:
                raise EventConflict("event_id has different content")
            return Receipt(event.event_id, run_id, record[0])
        row = self.connection.execute(
            "INSERT INTO events(run_id,event_id,schema_version,event_type,source,severity,"
            "correlation_id,causation_id,payload,occurred_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING sequence",
            (run_id, event.event_id, event.schema_version, event.event_type, event.source,
             event.severity, event.correlation_id, event.causation_id,
             Jsonb(event.payload), event.occurred_at),
        ).fetchone()
        return Receipt(event.event_id, run_id, row[0])

    def ingest_proposal(
        self, event: EventCreate, proposal: CorrectionProposal, request_id: UUID,
        tcad_mode: str, endpoint_url: str
    ) -> Receipt:
        with self.connection.transaction():
            receipt = self._insert_event(event, proposal.run_id)
            existing = self.connection.execute(
                "SELECT proposal_id FROM correction_proposals WHERE source_event_id=%s",
                (event.event_id,),
            ).fetchone()
            if existing:
                if existing[0] != proposal.proposal_id:
                    raise EventConflict("event_id maps to another proposal")
                return receipt
            self.connection.execute(
                "INSERT INTO correction_proposals("
                "proposal_id,run_id,source_event_id,representation,x_current,delta_x,"
                "x_candidate,y_observed,targets) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (proposal.proposal_id, proposal.run_id, event.event_id, proposal.representation,
                 Jsonb(proposal.x_current), Jsonb(proposal.delta_x),
                 Jsonb(proposal.x_candidate), Jsonb(proposal.y_observed),
                 Jsonb({k: v.model_dump() for k, v in proposal.targets.items()})),
            )
            self.connection.execute(
                "INSERT INTO verification_jobs(request_id,proposal_id,tcad_mode,endpoint_url,request_body)"
                " VALUES (%s,%s,%s,%s,%s)",
                (request_id, proposal.proposal_id, tcad_mode, endpoint_url,
                 Jsonb(proposal.model_dump(mode="json"))),
            )
            return receipt

    def list_after(self, run_id: UUID, cursor: int, limit: int = 200) -> list[dict]:
        if cursor < 0 or not 1 <= limit <= 1000:
            raise ValueError("invalid cursor or limit")
        rows = self.connection.execute(
            "SELECT e.sequence,e.event_id,e.event_type,e.source,e.severity,e.payload,"
            "e.occurred_at,e.received_at,r.unity_mode "
            "FROM events e JOIN integration_runs r ON r.run_id=e.run_id "
            "WHERE e.run_id=%s AND e.sequence>%s ORDER BY e.sequence LIMIT %s",
            (run_id, cursor, limit),
        ).fetchall()
        return [
            dict(sequence=row[0], event_id=str(row[1]), event_type=row[2], source=row[3],
                 severity=row[4], payload=row[5], occurred_at=row[6].isoformat(),
                 received_at=row[7].isoformat(), run_id=str(run_id), unity_mode=row[8])
            for row in rows
        ]
