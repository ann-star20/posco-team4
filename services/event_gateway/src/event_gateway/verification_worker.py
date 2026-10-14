"""Recoverable DB-backed TCAD HTTP worker."""

from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

import httpx
import psycopg
from psycopg.types.json import Jsonb

from .contracts import EventCreate, VerificationResult
from .repository import EventRepository
from .tcad_client import TcadClient


class VerificationWorker:
    def __init__(self, connection: psycopg.Connection, http_factory=None):
        self.connection = connection
        self.http_factory = http_factory or (
            lambda url: httpx.Client(base_url=url, timeout=10)
        )
        self.repository = EventRepository(connection)

    def run_once(self) -> int:
        with self.connection.transaction():
            row = self.connection.execute(
                "SELECT j.request_id,j.proposal_id,j.tcad_mode,j.endpoint_url,j.remote_job_id,"
                "j.request_body,j.status,p.run_id "
                "FROM verification_jobs j JOIN correction_proposals p USING (proposal_id) "
                "WHERE j.status IN ('queued','running') AND j.next_attempt_at<=now() "
                "AND (j.lease_until IS NULL OR j.lease_until<now()) "
                "ORDER BY j.created_at FOR UPDATE OF j SKIP LOCKED LIMIT 1",
            ).fetchone()
            if row is None:
                return 0
            request_id, proposal_id, mode, url, remote_id, body, status, run_id = row
            lease = uuid4()
            self.connection.execute(
                "UPDATE verification_jobs SET lease_token=%s,lease_until=now()+interval '30 seconds',"
                "attempt_count=attempt_count+1 "
                "WHERE request_id=%s",
                (lease, request_id),
            )
        try:
            with self.http_factory(url) as http:
                client = TcadClient(http)
                if remote_id is None:
                    accepted = client.submit(body | {"request_id": str(request_id)})
                    self._accept(request_id, proposal_id, run_id, lease, accepted.job_id)
                else:
                    result = client.poll(remote_id)
                    self._finish(request_id, proposal_id, run_id, mode, lease, remote_id, result)
        except httpx.HTTPStatusError as exc:
            if 400 <= exc.response.status_code < 500:
                self._fail(request_id, proposal_id, run_id, lease,
                           f"http_{exc.response.status_code}")
            else:
                self._retry(request_id, lease, f"http_{exc.response.status_code}")
        except ValueError as exc:
            self._fail(request_id, proposal_id, run_id, lease, type(exc).__name__)
        except httpx.HTTPError as exc:
            self._retry(request_id, lease, type(exc).__name__)
        return 1

    def _accept(self, request_id, proposal_id, run_id, lease, job_id):
        with self.connection.transaction():
            updated = self.connection.execute(
                "UPDATE verification_jobs SET remote_job_id=%s,status='running',"
                "next_attempt_at=now(),lease_token=NULL,lease_until=NULL,updated_at=now() "
                "WHERE request_id=%s AND lease_token=%s RETURNING request_id",
                (job_id, request_id, lease),
            ).fetchone()
            if not updated:
                return
            self.connection.execute(
                "UPDATE correction_proposals SET status='verifying' WHERE proposal_id=%s",
                (proposal_id,),
            )
            self._audit(run_id, "verification.accepted", {
                "proposal_id": str(proposal_id), "request_id": str(request_id),
                "job_id": job_id,
            })

    def _finish(self, request_id, proposal_id, run_id, mode, lease, remote_id, result):
        if result["status"] in {"queued", "running"}:
            self._retry(request_id, lease, "still_running")
            return
        if result["status"] == "failed":
            state = "failed"
            values = None
        else:
            verified = VerificationResult.model_validate({
                key: value for key, value in result.items() if key != "status"
            })
            if (verified.request_id != request_id or verified.result_origin != mode
                    or verified.job_id != remote_id):
                raise ValueError("TCAD result identity or origin mismatch")
            values = verified.y_verified
            targets = self.connection.execute(
                "SELECT targets FROM correction_proposals WHERE proposal_id=%s",
                (proposal_id,),
            ).fetchone()[0]
            state = "verified" if all(
                targets[key]["min"] <= values[key] <= targets[key]["max"]
                for key in targets
            ) else "rejected"
        with self.connection.transaction():
            updated = self.connection.execute(
                "UPDATE verification_jobs SET status=%s,response_body=%s,"
                "lease_token=NULL,lease_until=NULL,updated_at=now() "
                "WHERE request_id=%s AND lease_token=%s RETURNING request_id",
                ("succeeded" if state in {"verified", "rejected"} else "failed",
                 Jsonb(result), request_id, lease),
            ).fetchone()
            if not updated:
                return
            self.connection.execute(
                "UPDATE correction_proposals SET status=%s,y_verified=%s,result_origin=%s "
                "WHERE proposal_id=%s",
                (state, Jsonb(values) if values is not None else None,
                 mode if values is not None else None, proposal_id),
            )
            proposal_values = self.connection.execute(
                "SELECT x_current,delta_x,x_candidate FROM correction_proposals "
                "WHERE proposal_id=%s", (proposal_id,),
            ).fetchone()
            self._audit(run_id, f"correction.{state}", {
                "proposal_id": str(proposal_id), "request_id": str(request_id),
                "result_origin": mode, "y_verified": values,
                "x_current": proposal_values[0], "delta_x": proposal_values[1],
                "x_candidate": proposal_values[2],
            })

    def _retry(self, request_id, lease, code):
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE verification_jobs SET next_attempt_at=now()+interval '5 seconds',"
                "lease_token=NULL,lease_until=NULL,last_error_code=%s,updated_at=now() "
                "WHERE request_id=%s AND lease_token=%s",
                (code, request_id, lease),
            )

    def _fail(self, request_id, proposal_id, run_id, lease, code):
        with self.connection.transaction():
            updated = self.connection.execute(
                "UPDATE verification_jobs SET status='failed',last_error_code=%s,"
                "lease_token=NULL,lease_until=NULL,updated_at=now() "
                "WHERE request_id=%s AND lease_token=%s RETURNING request_id",
                (code, request_id, lease),
            ).fetchone()
            if not updated:
                return
            self.connection.execute(
                "UPDATE correction_proposals SET status='failed' WHERE proposal_id=%s",
                (proposal_id,),
            )
            self._audit(run_id, "correction.failed", {
                "proposal_id": str(proposal_id), "request_id": str(request_id),
                "error_code": code,
            })

    def _audit(self, run_id, event_type, payload):
        self.repository._insert_event(
            EventCreate(
                schema_version=1, event_id=uuid4(), event_type=event_type,
                source="gateway.verification", severity="info", payload=payload,
                occurred_at=datetime.now(timezone.utc),
            ),
            run_id,
        )


def main() -> None:
    from .config import Settings

    settings = Settings.load(Path(".env"))
    while True:
        try:
            with psycopg.connect(settings.database_url, autocommit=True) as connection:
                count = VerificationWorker(connection).run_once()
        except (psycopg.Error, httpx.HTTPError):
            count = 0
        if not count:
            time.sleep(settings.tcad_poll_interval_seconds)


if __name__ == "__main__":
    main()
