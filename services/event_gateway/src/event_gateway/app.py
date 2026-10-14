"""HTTP replay and WebSocket stream backed by committed PostgreSQL events."""

import asyncio
import secrets
from uuid import UUID

import psycopg
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .commands import ApprovalConflict, approve_proposal
from .config import Settings
from .repository import EventRepository
from .stream import format_unity_event


class ApprovalRequest(BaseModel):
    approved_by: str
    effective_from_lot: str


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="Virtual Fab event gateway")

    def replay(run_id: UUID, after_sequence: int, limit: int) -> list[dict]:
        with psycopg.connect(settings.database_url, autocommit=True) as connection:
            return [format_unity_event(row, row["unity_mode"])
                    for row in EventRepository(connection).list_after(run_id, after_sequence, limit)]

    @app.get("/health/live")
    def live():
        return {"status": "ok"}

    @app.get("/api/v1/events")
    def events(run_id: UUID, after_sequence: int = 0, limit: int = 200):
        try:
            return {"events": replay(run_id, after_sequence, limit)}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

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
                )
        except ApprovalConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"command_id": str(command_id), "status": "pending"}

    return app


def main() -> None:
    from pathlib import Path
    import uvicorn

    settings = Settings.load(Path(".env"))
    uvicorn.run(create_app(settings), host=settings.gateway_host, port=settings.gateway_port)


if __name__ == "__main__":
    main()
