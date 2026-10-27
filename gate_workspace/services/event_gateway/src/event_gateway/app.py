"""HTTP replay and WebSocket stream backed by committed PostgreSQL events."""

import asyncio
import secrets
from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import Literal

import psycopg
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .commands import ApprovalConflict, approve_proposal
from .contracts import EventCreate
from .inference_jobs import JobConflict, submit_aoi_job, submit_inference_job
from .config import Settings
from .repository import EventRepository
from .stream import format_unity_event


class ApprovalRequest(BaseModel):
    approved_by: str
    effective_from_lot: str


class TcadDecisionRequest(BaseModel):
    decided_by: str = Field(min_length=1)
    decision: Literal["approved", "rejected"]
    selected_tcad_request_id: UUID | None = None


class InspectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    request_id: UUID
    run_id: UUID
    lot_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)
    stage_id: str = Field(default="final_aoi", min_length=1)
    stage_attempt: int = Field(default=1, ge=1)
    expected_stage_version: int | None = Field(default=None, ge=0)
    fixture_name: str | None = Field(default=None, min_length=1)

    @field_validator("fixture_name")
    @classmethod
    def safe_fixture_name(cls, value: str | None) -> str | None:
        if value is not None and (value in {".", ".."} or "/" in value or "\\" in value):
            raise ValueError("fixture_name must be a single file name")
        return value


class SurrogateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    schema_version: Literal[1] = 1
    request_id: UUID
    run_id: UUID
    lot_id: str = Field(min_length=1)
    unit_id: str = Field(min_length=1)
    stage_id: str = Field(default='electrical', min_length=1)
    stage_attempt: int = Field(default=1, ge=1)
    model_contract_version: Literal['fab-ml-v1'] = 'fab-ml-v1'
    input_payload: dict


class DiagnosisRequest(SurrogateRequest):
    stage_id: str = Field(default='diagnosis', min_length=1)


def request_model_for_type(message_type: str):
    return {
        'inspection.requested': InspectionRequest,
        'surrogate.requested': SurrogateRequest,
        'diagnosis.requested': DiagnosisRequest,
    }.get(message_type)


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Virtual Fab event gateway")

    def authorize_unity(token: str | None) -> None:
        if not settings.unity_api_token:
            raise HTTPException(status_code=503, detail="Unity API token not configured")
        if not token or not secrets.compare_digest(token, settings.unity_api_token):
            raise HTTPException(status_code=401, detail="invalid Unity API token")

    def submit(request: InspectionRequest) -> dict:
        try:
            with psycopg.connect(settings.database_url, autocommit=True) as connection:
                return submit_aoi_job(connection, request.model_dump(mode="json"),
                                      settings.tcad_mode, settings.unity_mode)
        except JobConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def replay(run_id: UUID, after_sequence: int, limit: int) -> list[dict]:
        with psycopg.connect(settings.database_url, autocommit=True) as connection:
            return [format_unity_event(row, row["unity_mode"])
                    for row in EventRepository(connection).list_after(run_id, after_sequence, limit)]

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    def submit_surrogate(request: SurrogateRequest):
        try:
            with psycopg.connect(settings.database_url, autocommit=True) as connection:
                body=request.model_dump(mode='json') | {'surrogate_mode':settings.surrogate_mode}
                return submit_inference_job(connection,body,settings.tcad_mode,settings.unity_mode,'surrogate')
        except JobConflict as exc:
            raise HTTPException(409,str(exc)) from exc

    def submit_diagnosis(request: DiagnosisRequest):
        try:
            with psycopg.connect(settings.database_url, autocommit=True) as connection:
                body=request.model_dump(mode='json') | {'diagnosis_mode':settings.diagnosis_mode}
                body['input_payload']=dict(body['input_payload']) | {'refine':True}
                return submit_inference_job(connection,body,settings.tcad_mode,settings.unity_mode,'diagnosis')
        except JobConflict as exc:
            raise HTTPException(409,str(exc)) from exc

    @app.post('/api/v1/surrogate-jobs',status_code=202)
    def create_surrogate_job(request: SurrogateRequest,x_unity_token: str | None = Header(default=None)):
        authorize_unity(x_unity_token)
        return submit_surrogate(request)

    @app.post('/api/v1/diagnosis-jobs',status_code=202)
    def create_diagnosis_job(request: DiagnosisRequest,x_unity_token: str | None = Header(default=None)):
        authorize_unity(x_unity_token)
        return submit_diagnosis(request)

    @app.post("/api/v1/inspection-jobs", status_code=202)
    def create_inspection_job(request: InspectionRequest,
                              x_unity_token: str | None = Header(default=None)):
        authorize_unity(x_unity_token)
        return submit(request)

    @app.get("/api/v1/inspection-jobs/{job_id}")
    @app.get('/api/v1/jobs/{job_id}')
    def get_inspection_job(job_id: UUID, x_unity_token: str | None = Header(default=None)):
        authorize_unity(x_unity_token)
        with psycopg.connect(settings.database_url, autocommit=True) as connection:
            row = connection.execute(
                "SELECT request_id,run_id,status,result_event_id FROM inference_jobs WHERE job_id=%s",
                (job_id,),
            ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="AOI job not found")
        return {"job_id": str(job_id), "request_id": str(row[0]), "run_id": str(row[1]),
                "status": row[2], "result_event_id": str(row[3]) if row[3] else None}

    @app.websocket("/api/v1/control")
    async def control(websocket: WebSocket):
        try:
            authorize_unity(websocket.headers.get("x-unity-token"))
        except HTTPException:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        try:
            while True:
                raw = await websocket.receive_json()
                if not isinstance(raw,dict) or raw.get("type") not in {'inspection.requested','surrogate.requested','diagnosis.requested'}:
                    await websocket.send_json({"type": "request.rejected", "code": "unsupported_type"})
                    continue
                try:
                    model = request_model_for_type(raw['type'])
                    request = model.model_validate(
                        {key: value for key, value in raw.items() if key != "type"})
                    submitter = submit_surrogate if model is SurrogateRequest else (
                        submit_diagnosis if model is DiagnosisRequest else submit)
                    result = await asyncio.to_thread(submitter, request)
                except ValidationError:
                    await websocket.send_json({"type": "request.rejected", "code": "invalid_request"})
                    continue
                except HTTPException as exc:
                    await websocket.send_json({"type": "request.rejected", "code": exc.status_code,
                                               "detail": exc.detail})
                    continue
                await websocket.send_json({"type": "request.accepted", "request_id": str(request.request_id),
                                           **result})
        except WebSocketDisconnect:
            return

    @app.get("/api/v1/events")
    def events(run_id: UUID, after_sequence: int = 0, limit: int = 200):
        try:
            return {"events": replay(run_id, after_sequence, limit)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.websocket('/api/v1/commands')
    async def unity_commands(websocket: WebSocket, run_id: UUID):
        from .command_dispatcher import claim_due_commands
        from .unity_delivery import accept_applied
        try:authorize_unity(websocket.headers.get('x-unity-token'))
        except HTTPException:
            await websocket.close(code=1008);return
        def claim():
            with psycopg.connect(settings.database_url,autocommit=True) as db:
                return claim_due_commands(db,target='unity',run_id=run_id)
        def apply(ack):
            if not isinstance(ack,dict) or ack.get('run_id')!=str(run_id):raise ValueError('wrong run')
            with psycopg.connect(settings.database_url,autocommit=True) as db:return accept_applied(db,ack)
        await websocket.accept()
        try:
            while True:
                for command in await asyncio.to_thread(claim):
                    await websocket.send_json({'type':'correction.command',**command})
                try:
                    ack=await asyncio.wait_for(websocket.receive_json(),timeout=.5)
                except asyncio.TimeoutError:continue
                try:
                    if not isinstance(ack,dict) or ack.get('type')!='correction.applied':raise ValueError('invalid type')
                    result=await asyncio.to_thread(apply,ack)
                    await websocket.send_json({'type':'application.ack',**result})
                except (ValueError,KeyError,TypeError):
                    await websocket.send_json({'type':'application.rejected'})
        except WebSocketDisconnect:return

    @app.websocket("/api/v1/stream")
    async def stream(websocket: WebSocket, run_id: UUID, after_sequence: int = 0):
        if after_sequence < 0:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        cursor = after_sequence
        try:
            while True:
                batch = await asyncio.to_thread(replay, run_id, cursor, 200)
                for event in batch:
                    await websocket.send_json(event)
                    cursor = event["sequence"]
                if not batch:
                    try:
                        message = await asyncio.wait_for(websocket.receive(), timeout=0.25)
                        if message["type"] == "websocket.disconnect":
                            return
                    except asyncio.TimeoutError:
                        pass
        except WebSocketDisconnect:
            return

    @app.post("/api/v1/proposals/{proposal_id}/approval")
    def approve(proposal_id: UUID, request: ApprovalRequest,
                x_approval_token: str | None = Header(default=None)):
        if not settings.approval_token or not settings.approval_operator:
            raise HTTPException(status_code=503, detail="approval operator not configured")
        if not x_approval_token or not secrets.compare_digest(
            x_approval_token, settings.approval_token
        ):
            raise HTTPException(status_code=401, detail="invalid approval token")
        if request.approved_by != settings.approval_operator:
            raise HTTPException(status_code=403, detail="approver identity mismatch")
        try:
            with psycopg.connect(settings.database_url, autocommit=True) as connection:
                command_id = approve_proposal(
                    connection, proposal_id, settings.approval_operator,
                    request.effective_from_lot,
                    target=settings.correction_target,
                )
        except ApprovalConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"command_id": str(command_id), "status": "pending"}

    @app.get("/api/v1/tcad/proposals")
    def list_tcad_proposals(status: str = "review_required",
                            x_unity_token: str | None = Header(default=None)):
        authorize_unity(x_unity_token)
        with psycopg.connect(settings.database_url, autocommit=True) as connection:
            groups = connection.execute(
                "SELECT proposal_id, diagnosis_job_id, run_id, status, created_at "
                "FROM tcad_proposal_groups WHERE status=%s ORDER BY created_at", (status,),
            ).fetchall()
            result = []
            for proposal_id, job_id, run_id, group_status, created_at in groups:
                candidates = connection.execute(
                    "SELECT tcad_request_id, candidate_index, process_parameters, "
                    "result_payload, spec_verdict, result_origin FROM tcad_verification_candidates "
                    "WHERE proposal_id=%s ORDER BY candidate_index", (proposal_id,),
                ).fetchall()
                result.append({
                    "proposal_id": str(proposal_id), "job_id": str(job_id),
                    "run_id": str(run_id), "status": group_status,
                    "created_at": created_at.isoformat(),
                    "candidates": [
                        {"tcad_request_id": str(c[0]), "candidate_index": c[1],
                         "process_parameters": c[2], "result_payload": c[3],
                         "spec_verdict": c[4], "result_origin": c[5] or "unknown"}
                        for c in candidates
                    ],
                })
        return {"proposals": result}

    @app.post("/api/v1/tcad/proposals/{proposal_id}/decision")
    def decide_tcad_proposal(proposal_id: UUID, request: TcadDecisionRequest,
                             x_unity_token: str | None = Header(default=None)):
        authorize_unity(x_unity_token)
        if request.decision == "approved" and request.selected_tcad_request_id is None:
            raise HTTPException(status_code=400, detail="selected_tcad_request_id is required to approve")
        with psycopg.connect(settings.database_url, autocommit=True) as connection:
            group = connection.execute(
                "SELECT run_id FROM tcad_proposal_groups WHERE proposal_id=%s AND status='review_required'",
                (proposal_id,),
            ).fetchone()
            if group is None:
                raise HTTPException(status_code=404, detail="proposal not found or not review_required")
            run_id = group[0]
            if request.decision == "approved":
                candidate = connection.execute(
                    "SELECT process_parameters FROM tcad_verification_candidates "
                    "WHERE proposal_id=%s AND tcad_request_id=%s",
                    (proposal_id, request.selected_tcad_request_id),
                ).fetchone()
                if candidate is None:
                    raise HTTPException(status_code=400, detail="selected candidate does not belong to this proposal")
                connection.execute(
                    "UPDATE tcad_proposal_groups SET status='completed',approved_by=%s,"
                    "approved_at=now(),selected_tcad_request_id=%s,updated_at=now() WHERE proposal_id=%s",
                    (request.decided_by, request.selected_tcad_request_id, proposal_id),
                )
                process_parameters = candidate[0]
            else:
                connection.execute(
                    "UPDATE tcad_proposal_groups SET status='failed',updated_at=now() WHERE proposal_id=%s",
                    (proposal_id,),
                )
                process_parameters = None
            EventRepository(connection)._insert_event(EventCreate(
                schema_version=1, event_id=uuid4(),
                event_type="tcad.verification.decided", source="gateway.tcad", severity="info",
                payload={
                    "proposal_id": str(proposal_id), "decision": request.decision,
                    "decided_by": request.decided_by,
                    "selected_tcad_request_id": str(request.selected_tcad_request_id)
                    if request.selected_tcad_request_id else None,
                },
                occurred_at=datetime.now(timezone.utc),
            ), run_id)
        return {"proposal_id": str(proposal_id), "status": request.decision,
                "process_parameters": process_parameters}

    return app


def main() -> None:
    from pathlib import Path
    import uvicorn

    settings = Settings.load(Path(".env"))
    uvicorn.run(create_app(settings), host=settings.gateway_host, port=settings.gateway_port)


if __name__ == "__main__":
    main()
