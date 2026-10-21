"""Durable admission and state helpers for diagnosis TCAD candidates."""

from uuid import UUID, uuid5

from psycopg.types.json import Jsonb

from .tcad_contracts import TcadVerificationRequest, make_tcad_request_id


def admit_tcad_candidates(
    db, *, event, run_id: UUID, job_id: UUID, request_id: UUID,
    request_body: dict, parsed, response: dict, settings,
) -> UUID | None:
    if (
        not settings.tcad_auto_submit_enabled
        or parsed.status != "succeeded"
        or parsed.anomaly_detected is not True
        or parsed.result_payload.compensation.route != "tcad_verify"
        or parsed.tcad_proposal is None
    ):
        return None

    proposal_id = uuid5(event.event_id, "tcad-proposal-group-v1")
    candidates = parsed.tcad_proposal.candidates
    routing_snapshot = {
        "compensation": response["result_payload"]["compensation"],
        "tcad_proposal": response["tcad_proposal"],
    }
    db.execute(
        "INSERT INTO tcad_proposal_groups(proposal_id,diagnosis_job_id,source_event_id,run_id,"
        "original_request_id,model_contract_version,policy_version,routing_snapshot,candidate_count) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (source_event_id) DO NOTHING",
        (proposal_id, job_id, event.event_id, run_id, request_id,
         parsed.model_contract_version, settings.tcad_policy_version,
         Jsonb(routing_snapshot), len(candidates)),
    )
    stored = db.execute(
        "SELECT proposal_id FROM tcad_proposal_groups WHERE source_event_id=%s",
        (event.event_id,),
    ).fetchone()
    if stored is None or stored[0] != proposal_id:
        raise ValueError("TCAD proposal identity conflict")

    for candidate_index, candidate in enumerate(candidates):
        tcad_request_id = make_tcad_request_id(proposal_id, candidate_index)
        outgoing = TcadVerificationRequest(
            request_id=tcad_request_id,
            job_id=job_id,
            run_id=run_id,
            lot_id=request_body.get("lot_id"),
            process_parameters=candidate.process_parameters,
            predicted_outputs=candidate.predicted_outputs.model_dump(mode="json"),
            requested_outputs=["vth", "gm", "id_on", "bv"],
            options={"timeout_seconds": 5400},
        ).model_dump(mode="json")
        db.execute(
            "INSERT INTO tcad_verification_candidates(tcad_request_id,proposal_id,candidate_index,"
            "process_parameters,predicted_outputs,requested_outputs,request_body,deadline_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,now()+(%s * interval '1 second')) "
            "ON CONFLICT (proposal_id,candidate_index) DO NOTHING",
            (tcad_request_id, proposal_id, candidate_index,
             Jsonb(candidate.process_parameters.model_dump(mode="json")),
             Jsonb(candidate.predicted_outputs.model_dump(mode="json")),
             Jsonb(outgoing["requested_outputs"]), Jsonb(outgoing),
             settings.tcad_job_deadline_seconds),
        )
    return proposal_id
