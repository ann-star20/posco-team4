"""Persist diagnosis responses and derive safe follow-up routing."""

from uuid import UUID

from psycopg.types.json import Jsonb

from .ml_contracts import validate_model_response
from .ml_execution import store_ml_execution
from .repository import EventConflict
from .tcad_queue import admit_tcad_candidates


def ingest_diagnosis(repository, event, run_id, settings):
    db = repository.connection
    payload = event.payload
    with db.transaction():
        receipt = repository._insert_event(event, run_id)
        row = db.execute(
            "SELECT run_id,request_id,stage_attempt,task_type,request_body,result_event_id,status "
            "FROM inference_jobs WHERE job_id=%s FOR UPDATE", (UUID(payload["job_id"]),)
        ).fetchone()
        if (not row or row[:4] != (run_id, UUID(payload["request_id"]),
                                   int(payload["attempt"]), "diagnosis")
                or event.source != "jetson.diagnosis"):
            raise EventConflict("diagnosis result does not match request")
        if row[5] is not None:
            if row[5] != event.event_id:
                raise EventConflict("diagnosis job already closed")
            return receipt
        if row[6] == "cancelled":
            raise EventConflict("diagnosis job cancelled")
        response = payload["response"]
        parsed = validate_model_response("diagnosis", response)
        expected_origin = row[4].get("diagnosis_mode", "mock")
        if (str(parsed.request_id) != str(row[1]) or str(parsed.job_id) != payload["job_id"]
                or parsed.result_origin != expected_origin):
            raise EventConflict("diagnosis response identity or origin mismatch")

        route_status = "failed"
        category = probability = compensation_route = high_confidence = None
        if parsed.status == "succeeded":
            result = parsed.result_payload
            category = result.decision.top_category
            probability = (response["result_payload"].get("decision", {})
                           .get("top_probability"))
            compensation = result.compensation
            compensation_route = compensation.route
            high_confidence = (response["result_payload"].get("compensation", {})
                               .get("high_confidence"))
            route_status = "normal" if compensation.route == "no_action" else "review_required"

        job_id = UUID(payload["job_id"])
        proposal_id = admit_tcad_candidates(
            db, event=event, run_id=run_id, job_id=job_id, request_id=row[1],
            request_body=row[4], parsed=parsed, response=response, settings=settings,
        )
        if proposal_id is not None:
            route_status = "verification_queued"
        db.execute(
            "INSERT INTO diagnosis_results(job_id,source_event_id,response_body,top_category,"
            "top_probability,compensation_route,high_confidence,routing_status) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (job_id, event.event_id, Jsonb(response), category, probability,
             compensation_route, high_confidence, route_status),
        )
        if proposal_id is not None:
            db.execute(
                "UPDATE diagnosis_results SET tcad_proposal_group_id=%s WHERE job_id=%s",
                (proposal_id, job_id),
            )
        store_ml_execution(db, event.event_id, job_id, payload["attempt"], "diagnosis", response,
                           payload.get("execution_attempt", 1))
        db.execute("UPDATE inference_jobs SET status=%s,result_event_id=%s,updated_at=now() "
                   "WHERE job_id=%s",
                   ("failed" if parsed.status == "failed" else "completed", event.event_id, job_id))
        db.execute("UPDATE inference_dispatches SET status='completed' WHERE job_id=%s", (job_id,))
        return receipt
