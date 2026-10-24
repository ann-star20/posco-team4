"""Explicit human approval of simulation-only corrections."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

from .contracts import EventCreate
from .repository import EventRepository


class ApprovalConflict(ValueError):
    pass


def approve_proposal(
    connection: psycopg.Connection, proposal_id: UUID, approved_by: str,
    effective_from_lot: str,
    target: str = 'jetson',
) -> UUID:
    if target not in {'jetson','unity'}:raise ValueError('invalid delivery target')
    if not approved_by.strip() or not effective_from_lot.strip():
        raise ValueError("approver and effective lot are required")
    with connection.transaction():
        row = connection.execute(
            "SELECT p.status,p.result_origin,p.run_id,p.x_candidate,r.unity_mode,p.approved_by,"
            "p.x_current "
            "FROM correction_proposals p JOIN integration_runs r USING(run_id) "
            "WHERE p.proposal_id=%s FOR UPDATE OF p", (proposal_id,),
        ).fetchone()
        if row is None:
            raise ApprovalConflict("proposal not found")
        status, origin, run_id, candidate, unity_mode, existing_approver, current = row
        existing = connection.execute(
            "SELECT command_id,effective_from_lot,delivery_target FROM commands WHERE proposal_id=%s",
            (proposal_id,),
        ).fetchone()
        if existing:
            if existing[1] != effective_from_lot or existing_approver != approved_by or existing[2]!=target:
                raise ApprovalConflict("proposal already approved differently")
            return existing[0]
        if status != "verified" or (unity_mode == "prod" and origin != "prod"):
            raise ApprovalConflict("proposal is not eligible for approval")
        if candidate.get("epi_doping") != current.get("epi_doping"):
            raise ApprovalConflict("epi doping cannot be changed")
        command_id = uuid4()
        payload = {
            "command_id": str(command_id), "proposal_id": str(proposal_id),
            "run_id": str(run_id), "scope": "simulation",
            "effective_from_lot": effective_from_lot,
            "x_candidate": candidate,
            "x_current": current,
        }
        connection.execute(
            "UPDATE correction_proposals SET status='approved',approved_by=%s,approved_at=now() "
            "WHERE proposal_id=%s", (approved_by, proposal_id),
        )
        connection.execute(
            "INSERT INTO commands(command_id,proposal_id,run_id,scope,effective_from_lot,payload,delivery_target) "
            "VALUES (%s,%s,%s,'simulation',%s,%s,%s)",
            (command_id, proposal_id, run_id, effective_from_lot, Jsonb(payload),target),
        )
        EventRepository(connection)._insert_event(EventCreate(
            schema_version=1, event_id=uuid4(), event_type="correction.approved",
            source="gateway.approval", severity="info",
            payload={"proposal_id": str(proposal_id), "command_id": str(command_id),
                     "approved_by": approved_by, "effective_from_lot": effective_from_lot},
            occurred_at=datetime.now(timezone.utc),
        ), run_id)
        return command_id
