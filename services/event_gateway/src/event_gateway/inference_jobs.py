"""Durable AOI request admission and ROS dispatch source of truth."""

from hashlib import sha256
import json
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from .repository import EventRepository


class JobConflict(ValueError):
    pass


def submit_aoi_job(connection: psycopg.Connection, request: dict,
                   tcad_mode: str, unity_mode: str) -> dict:
    return submit_inference_job(connection, request, tcad_mode, unity_mode, 'aoi')


def submit_inference_job(connection: psycopg.Connection, request: dict,
                         tcad_mode: str, unity_mode: str, task_type: str) -> dict:
    if task_type not in {'aoi', 'surrogate'}:
        raise ValueError('invalid task type')
    # Keep legacy AOI request hashes stable across this extension.
    if task_type == 'surrogate':
        request = {**request, 'task_type': task_type}
    request_id = UUID(request["request_id"])
    run_id = UUID(request["run_id"])
    lot_id = str(request["lot_id"])
    unit_id = str(request["unit_id"])
    stage_id = str(request["stage_id"])
    attempt = int(request["stage_attempt"])
    if not all(x.strip() for x in (lot_id, unit_id, stage_id)) or attempt < 1:
        raise ValueError("invalid AOI job scope")
    body = json.dumps(request, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fingerprint = sha256(body.encode("utf-8")).hexdigest()
    scope = f"aoi:{run_id}:{unit_id}:{stage_id}"
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (scope,))
        EventRepository(connection).ensure_run(run_id, tcad_mode, unity_mode)
        existing = connection.execute(
            "SELECT job_id,request_hash,status FROM inference_jobs WHERE request_id=%s",
            (request_id,),
        ).fetchone()
        if existing:
            if existing[1] != fingerprint:
                raise JobConflict("request_id has different content")
            return {"job_id": str(existing[0]), "status": existing[2]}
        active = connection.execute(
            "SELECT job_id FROM inference_jobs WHERE run_id=%s AND unit_id=%s AND stage_id=%s "
            "AND status IN ('queued','dispatching','accepted','running')",
            (run_id, unit_id, stage_id),
        ).fetchone()
        if active:
            raise JobConflict("active AOI job already exists: " + str(active[0]))
        job_id = uuid4()
        connection.execute(
            "INSERT INTO inference_jobs(job_id,request_id,run_id,task_type,lot_id,unit_id,stage_id,"
            "stage_attempt,expected_stage_version,request_hash,request_body) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (job_id, request_id, run_id, task_type, lot_id, unit_id, stage_id, attempt,
             request.get("expected_stage_version"), fingerprint, Jsonb(request)),
        )
        connection.execute("INSERT INTO inference_dispatches(job_id) VALUES (%s)", (job_id,))
        return {"job_id": str(job_id), "status": "queued"}


def claim_due_aoi_requests(connection: psycopg.Connection, limit: int = 20) -> list[dict]:
    """Lease committed jobs for at-least-once ROS publish."""
    with connection.transaction():
        rows = connection.execute(
            "SELECT d.job_id,j.request_id,j.run_id,j.lot_id,j.stage_attempt,j.request_body "
            "FROM inference_dispatches d JOIN inference_jobs j USING(job_id) "
            "WHERE d.status='pending' AND d.next_attempt_at<=now() "
            "ORDER BY d.next_attempt_at FOR UPDATE OF d SKIP LOCKED LIMIT %s",
            (limit,),
        ).fetchall()
        for job_id, *_ in rows:
            connection.execute(
                "UPDATE inference_dispatches SET attempt_count=attempt_count+1,"
                "next_attempt_at=now()+interval '2 seconds' WHERE job_id=%s",
                (job_id,),
            )
        return [{"schema_version": 1, "task_type": body.get('task_type', 'aoi'), "job_id": str(job_id),
                 "request_id": str(request_id), "run_id": str(run_id),
                 "lot_id": lot_id, "attempt": attempt,
                 **({"fixture_name": body["fixture_name"]} if body.get("fixture_name") else {}),
                 **({key: body[key] for key in ('model_contract_version','input_payload','surrogate_mode','surrogate_url') if key in body}
                    if body.get('task_type') == 'surrogate' else {})}
                for job_id, request_id, run_id, lot_id, attempt, body in rows]
