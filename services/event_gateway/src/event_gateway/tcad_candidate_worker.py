"""Lease-backed worker for request-id keyed diagnosis TCAD candidates."""

from datetime import datetime, timezone
from uuid import uuid4

import httpx
from psycopg.types.json import Jsonb

from .contracts import EventCreate
from .repository import EventRepository
from .tcad_client import TcadCandidateClient
from .tcad_contracts import TcadVerificationRequest

_EPSILON = 1e-6


def evaluate_spec(vth, bv, spec):
    if not spec:
        return {"overall": "spec_unavailable"}
    vth_pass = spec["vth_min"] - _EPSILON <= vth <= spec["vth_max"] + _EPSILON
    if bv is None:
        return {"vth_pass": vth_pass, "bv_pass": None, "overall": "bv_unconfirmed", "spec_source": spec.get("status")}
    bv_pass = bv >= spec["bv_min"] - _EPSILON
    overall = "in_spec" if vth_pass and bv_pass else "out_of_spec"
    return {"vth_pass": vth_pass, "bv_pass": bv_pass, "overall": overall, "spec_source": spec.get("status")}


class TcadCandidateWorker:
    def __init__(self, connection, settings, http_factory=None):
        self.connection = connection
        self.settings = settings
        self.http_factory = http_factory or (
            lambda url: httpx.Client(
                base_url=url,
                timeout=httpx.Timeout(
                    settings.tcad_request_timeout_seconds,
                    connect=settings.tcad_connect_timeout_seconds,
                ),
            )
        )
        self.repository = EventRepository(connection)

    def run_once(self) -> int:
        if self._expire_due_jobs():
            return 1
        claimed = self._claim()
        if claimed is None:
            return 0
        (request_id, proposal_id, previous_status, request_body, run_id,
         original_request_id, candidate_index, job_id, lease) = claimed
        try:
            with self.http_factory(self.settings.tcad_url) as http:
                client = TcadCandidateClient(http, self.settings.tcad_api_token)
                if previous_status in {"pending", "submitting"}:
                    accepted = client.submit(TcadVerificationRequest.model_validate(request_body))
                    self._record_acceptance(
                        request_id, proposal_id, run_id, original_request_id,
                        candidate_index, job_id, lease, accepted,
                    )
                else:
                    result = client.poll(request_id)
                    self._record_poll(
                        request_id, proposal_id, run_id, original_request_id,
                        candidate_index, job_id, previous_status, lease, result,
                    )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 409:
                self._recover_conflict(request_id, lease)
            elif exc.response.status_code in {408, 429}:
                self._retry(request_id, previous_status, lease, f"http_{exc.response.status_code}")
            elif 400 <= exc.response.status_code < 500:
                self._record_failure(
                    request_id, proposal_id, run_id, original_request_id,
                    candidate_index, job_id, lease, f"http_{exc.response.status_code}",
                    "TCAD request rejected",
                )
            else:
                self._retry(request_id, previous_status, lease, f"http_{exc.response.status_code}")
        except httpx.HTTPError as exc:
            self._retry(request_id, previous_status, lease, type(exc).__name__)
        except ValueError as exc:
            self._record_failure(
                request_id, proposal_id, run_id, original_request_id,
                candidate_index, job_id, lease, "CONTRACT_ERROR", str(exc),
            )
        return 1

    def _expire_due_jobs(self) -> bool:
        with self.connection.transaction():
            rows = self.connection.execute(
                "UPDATE tcad_verification_candidates c SET status='expired',completed_at=now(),"
                "last_error_code='DEADLINE_EXCEEDED',last_error_message='TCAD job deadline exceeded',"
                "lease_token=NULL,lease_until=NULL,updated_at=now() "
                "FROM tcad_proposal_groups g WHERE c.proposal_id=g.proposal_id "
                "AND c.status IN ('pending','submitting','queued','running') AND c.deadline_at<=now() "
                "RETURNING c.tcad_request_id,c.proposal_id,c.candidate_index,g.run_id,"
                "g.original_request_id,g.diagnosis_job_id",
            ).fetchall()
            groups = {}
            for request_id, proposal_id, candidate_index, run_id, original_request_id, job_id in rows:
                self._audit(run_id, "tcad.verification.candidate_expired", {
                    "request_id": str(original_request_id), "job_id": str(job_id),
                    "proposal_id": str(proposal_id), "tcad_request_id": str(request_id),
                    "candidate_index": candidate_index, "status": "expired",
                    "error_code": "DEADLINE_EXCEEDED",
                    "error_message": "TCAD job deadline exceeded",
                })
                groups[proposal_id] = (run_id, original_request_id, job_id)
            for proposal_id, correlation in groups.items():
                self._aggregate_group(proposal_id, *correlation)
            return bool(rows)

    def _claim(self):
        with self.connection.transaction():
            # Serialize count-and-claim across worker processes in this schema.
            self.connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(current_schema()),"
                "hashtext('event_gateway_tcad_claim'))"
            )
            row = self.connection.execute(
                "SELECT c.tcad_request_id,c.proposal_id,c.status,c.request_body,g.run_id,"
                "g.original_request_id,c.candidate_index,g.diagnosis_job_id "
                "FROM tcad_verification_candidates c JOIN tcad_proposal_groups g USING(proposal_id) "
                "WHERE c.status IN ('submitting','queued','running') AND c.next_attempt_at<=now() "
                "AND (c.lease_until IS NULL OR c.lease_until<now()) "
                "ORDER BY c.next_attempt_at,c.created_at FOR UPDATE OF c SKIP LOCKED LIMIT 1"
            ).fetchone()
            if row is None:
                active = self.connection.execute(
                    "SELECT count(*) FROM tcad_verification_candidates "
                    "WHERE status IN ('submitting','queued','running')"
                ).fetchone()[0]
                if active >= self.settings.tcad_max_concurrent_jobs:
                    return None
                row = self.connection.execute(
                    "SELECT c.tcad_request_id,c.proposal_id,c.status,c.request_body,g.run_id,"
                    "g.original_request_id,c.candidate_index,g.diagnosis_job_id "
                    "FROM tcad_verification_candidates c JOIN tcad_proposal_groups g USING(proposal_id) "
                    "WHERE c.status='pending' AND c.next_attempt_at<=now() "
                    "AND (c.lease_until IS NULL OR c.lease_until<now()) "
                    "ORDER BY c.created_at,c.candidate_index FOR UPDATE OF c SKIP LOCKED LIMIT 1"
                ).fetchone()
            if row is None:
                return None
            lease = uuid4()
            previous_status = row[2]
            claimed_status = "submitting" if previous_status == "pending" else previous_status
            self.connection.execute(
                "UPDATE tcad_verification_candidates SET status=%s,lease_token=%s,"
                "lease_until=now()+(%s*interval '1 second'),attempt_count=attempt_count+1,updated_at=now() "
                "WHERE tcad_request_id=%s", (claimed_status, lease,
                self.settings.tcad_lease_seconds, row[0]),
            )
            return (*row[:2], previous_status, *row[3:], lease)

    def _record_acceptance(self, request_id, proposal_id, run_id, original_request_id,
                           candidate_index, job_id, lease, accepted):
        with self.connection.transaction():
            updated = self.connection.execute(
                "UPDATE tcad_verification_candidates SET status='queued',acceptance_body=%s,"
                "queue_position=%s,accepted_at=%s,next_attempt_at=now()+(%s*interval '1 second'),"
                "lease_token=NULL,lease_until=NULL,last_error_code=NULL,last_error_message=NULL,"
                "updated_at=now() WHERE tcad_request_id=%s AND lease_token=%s RETURNING tcad_request_id",
                (Jsonb(accepted.model_dump(mode="json")), accepted.queue_position,
                 accepted.accepted_at, self.settings.tcad_poll_interval_seconds,
                 request_id, lease),
            ).fetchone()
            if updated is None:
                return
            self.connection.execute(
                "UPDATE tcad_proposal_groups SET status='running',updated_at=now() "
                "WHERE proposal_id=%s AND status='queued'", (proposal_id,),
            )
            self._audit(run_id, "tcad.verification.candidate_queued", {
                "request_id": str(original_request_id), "job_id": str(job_id),
                "proposal_id": str(proposal_id),
                "tcad_request_id": str(request_id), "candidate_index": candidate_index,
                "status": "queued", "queue_position": accepted.queue_position,
            })

    def _record_poll(self, request_id, proposal_id, run_id, original_request_id,
                     candidate_index, job_id, previous_status, lease, result):
        data = result.model_dump(mode="json", exclude_none=True)
        if result.status in {"queued", "running"}:
            stage = (result.progress or {}).get("stage")
            with self.connection.transaction():
                previous_stage = self.connection.execute(
                    "SELECT last_stage FROM tcad_verification_candidates WHERE tcad_request_id=%s",
                    (request_id,),
                ).fetchone()[0]
                updated = self.connection.execute(
                    "UPDATE tcad_verification_candidates SET status=%s,latest_response_body=%s,"
                    "queue_position=%s,progress=%s,last_stage=%s,started_at=CASE WHEN %s='running' "
                    "THEN COALESCE(started_at,now()) ELSE started_at END,"
                    "next_attempt_at=now()+(%s*interval '1 second'),lease_token=NULL,lease_until=NULL,"
                    "updated_at=now() WHERE tcad_request_id=%s AND lease_token=%s "
                    "RETURNING tcad_request_id",
                    (result.status, Jsonb(data), result.queue_position,
                     Jsonb(result.progress) if result.progress is not None else None,
                     stage, result.status, self.settings.tcad_poll_interval_seconds,
                    request_id, lease),
                ).fetchone()
                if updated is not None and (result.status != previous_status or stage != previous_stage):
                    self._audit(run_id, f"tcad.verification.candidate_{result.status}", {
                        "request_id": str(original_request_id), "job_id": str(job_id),
                        "proposal_id": str(proposal_id),
                        "tcad_request_id": str(request_id), "candidate_index": candidate_index,
                        "status": result.status, "progress": result.progress,
                    })
            return
        if result.status == "failed":
            self._record_failure(
                request_id, proposal_id, run_id, original_request_id, candidate_index, job_id, lease,
                result.error_code or "TCAD_FAILED", result.error_message or "TCAD failed", data,
            )
            return
        with self.connection.transaction():
            spec = self.connection.execute(
                "SELECT routing_snapshot->'spec' FROM tcad_proposal_groups WHERE proposal_id=%s",
                (proposal_id,),
            ).fetchone()[0]
            outputs = result.result_payload
            vth = outputs.vth if outputs is not None else None
            bv = outputs.bv if outputs is not None else None
            verdict = evaluate_spec(vth, bv, spec)
            updated = self.connection.execute(
                "UPDATE tcad_verification_candidates SET status=%s,latest_response_body=%s,"
                "result_payload=%s,prediction_error=%s,metadata=%s,spec_verdict=%s,completed_at=now(),"
                "lease_token=NULL,lease_until=NULL,updated_at=now() "
                "WHERE tcad_request_id=%s AND lease_token=%s RETURNING tcad_request_id",
                (result.status, Jsonb(data),
                 Jsonb(data.get("result_payload")) if result.result_payload is not None else None,
                 Jsonb(result.prediction_error) if result.prediction_error is not None else None,
                 Jsonb(result.metadata) if result.metadata is not None else None,
                 Jsonb(verdict),
                request_id, lease),
            ).fetchone()
            if updated is None:
                return
            self._audit(run_id, f"tcad.verification.candidate_{result.status}", {
                "request_id": str(original_request_id), "job_id": str(job_id),
                "proposal_id": str(proposal_id),
                "tcad_request_id": str(request_id), "candidate_index": candidate_index,
                "status": result.status, "result_payload": data.get("result_payload"),
                "spec_verdict": verdict,
            })
            self._aggregate_group(proposal_id, run_id, original_request_id, job_id)

    def _record_failure(self, request_id, proposal_id, run_id, original_request_id,
                        candidate_index, job_id, lease, code, message, response=None):
        with self.connection.transaction():
            updated = self.connection.execute(
                "UPDATE tcad_verification_candidates SET status='failed',latest_response_body=%s,"
                "last_error_code=%s,last_error_message=%s,completed_at=now(),"
                "lease_token=NULL,lease_until=NULL,updated_at=now() "
                "WHERE tcad_request_id=%s AND lease_token=%s RETURNING tcad_request_id",
                (Jsonb(response) if response is not None else None, code, message,
                 request_id, lease),
            ).fetchone()
            if updated is None:
                return
            self._audit(run_id, "tcad.verification.candidate_failed", {
                "request_id": str(original_request_id), "job_id": str(job_id),
                "proposal_id": str(proposal_id),
                "tcad_request_id": str(request_id), "candidate_index": candidate_index,
                "status": "failed", "error_code": code, "error_message": message,
            })
            self._aggregate_group(proposal_id, run_id, original_request_id, job_id)

    def _retry(self, request_id, previous_status, lease, code):
        retry_status = "pending" if previous_status in {"pending", "submitting"} else previous_status
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE tcad_verification_candidates SET status=%s,last_error_code=%s,"
                "next_attempt_at=now()+(LEAST(300.0,5.0*power(2.0,GREATEST(attempt_count-1,0)))"
                "*interval '1 second'),lease_token=NULL,lease_until=NULL,"
                "updated_at=now() WHERE tcad_request_id=%s AND lease_token=%s",
                (retry_status, code, request_id, lease),
            )

    def _recover_conflict(self, request_id, lease):
        with self.connection.transaction():
            self.connection.execute(
                "UPDATE tcad_verification_candidates SET status='queued',next_attempt_at=now(),"
                "last_error_code='http_409_recovered',lease_token=NULL,lease_until=NULL,updated_at=now() "
                "WHERE tcad_request_id=%s AND lease_token=%s", (request_id, lease),
            )

    def _aggregate_group(self, proposal_id, run_id=None, original_request_id=None, job_id=None):
        total, terminal, succeeded, cancelled = self.connection.execute(
            "SELECT count(*),count(*) FILTER (WHERE status IN "
            "('succeeded','failed','cancelled','expired')),"
            "count(*) FILTER (WHERE status='succeeded'),"
            "count(*) FILTER (WHERE status='cancelled') "
            "FROM tcad_verification_candidates WHERE proposal_id=%s", (proposal_id,),
        ).fetchone()
        if terminal < total:
            self.connection.execute(
                "UPDATE tcad_proposal_groups SET terminal_count=%s,updated_at=now() "
                "WHERE proposal_id=%s", (terminal, proposal_id),
            )
            return
        status = "review_required" if succeeded else ("cancelled" if cancelled == total else "failed")
        transitioned = self.connection.execute(
            "UPDATE tcad_proposal_groups SET terminal_count=%s,status=%s,updated_at=now() "
            "WHERE proposal_id=%s AND status NOT IN ('review_required','failed','cancelled') "
            "RETURNING run_id,original_request_id,diagnosis_job_id",
            (terminal, status, proposal_id),
        ).fetchone()
        if transitioned is None:
            return
        run_id = run_id or transitioned[0]
        original_request_id = original_request_id or transitioned[1]
        job_id = job_id or transitioned[2]
        summary = [
            {"tcad_request_id": str(row[0]), "candidate_index": row[1], "status": row[2]}
            for row in self.connection.execute(
                "SELECT tcad_request_id,candidate_index,status FROM tcad_verification_candidates "
                "WHERE proposal_id=%s ORDER BY candidate_index", (proposal_id,),
            ).fetchall()
        ]
        common = {
            "request_id": str(original_request_id), "job_id": str(job_id),
            "proposal_id": str(proposal_id),
            "status": status, "candidates": summary, "succeeded_count": succeeded,
        }
        self._audit(run_id, "tcad.verification.batch_completed", common)
        if status == "review_required":
            self._audit(run_id, "tcad.verification.review_required", common)

    def _audit(self, run_id, event_type, payload):
        self.repository._insert_event(EventCreate(
            schema_version=1, event_id=uuid4(), event_type=event_type,
            source="gateway.tcad", severity="info", payload=payload,
            occurred_at=datetime.now(timezone.utc),
        ), run_id)
