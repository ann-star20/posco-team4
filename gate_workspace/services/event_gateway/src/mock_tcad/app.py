"""Deterministic mock TCAD server with durable request ID mapping."""

from hashlib import sha256
import json
from pathlib import Path
import secrets
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from event_gateway.tcad_contracts import TcadVerificationRequest


class RequestBody(BaseModel):
    # Include all process inputs in the request identity, not only targets.
    model_config = ConfigDict(extra="allow")
    request_id: str
    proposal_id: str
    targets: dict[str, dict[str, float]]


def create_app(path: Path, scenario: str = "pass", api_token: str = "") -> FastAPI:
    if scenario not in {"pass", "out_of_spec", "timeout", "server_error", "malformed_response",
                        "failed", "cancelled"}:
        raise ValueError("unknown mock scenario")
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS jobs("
            "request_id TEXT PRIMARY KEY,job_id TEXT UNIQUE NOT NULL,body_hash TEXT NOT NULL,"
            "result TEXT NOT NULL)"
        )
        db.execute(
            "CREATE TABLE IF NOT EXISTS candidate_jobs("
            "request_id TEXT PRIMARY KEY,body_hash TEXT NOT NULL,body TEXT NOT NULL,"
            "accepted_at TEXT NOT NULL,poll_count INTEGER NOT NULL DEFAULT 0)"
        )
    app = FastAPI()

    @app.get("/health/live")
    def live():
        return {"status": "ok", "result_origin": "mock"}

    @app.get("/health/ready")
    def ready():
        return {"status": "ready", "result_origin": "mock"}

    def authorize(token: str | None):
        if api_token and (token is None or not secrets.compare_digest(token, api_token)):
            raise HTTPException(401, "invalid TCAD token")

    @app.post("/api/v1/tcad/verify", status_code=202)
    def submit_candidate(body: TcadVerificationRequest,
                         x_fab_token: str | None = Header(default=None)):
        authorize(x_fab_token)
        if scenario == "server_error":
            raise HTTPException(503, "synthetic TCAD failure")
        dumped = body.model_dump(mode="json", exclude_none=True)
        canonical = json.dumps(dumped, sort_keys=True, separators=(",", ":"))
        digest = sha256(canonical.encode()).hexdigest()
        with sqlite3.connect(path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT body_hash,accepted_at FROM candidate_jobs WHERE request_id=?",
                (str(body.request_id),),
            ).fetchone()
            if row and row[0] != digest:
                raise HTTPException(409, "request_id content conflict")
            if row:
                accepted_at = row[1]
            else:
                accepted_at = datetime.now(timezone.utc).isoformat()
                db.execute(
                    "INSERT INTO candidate_jobs(request_id,body_hash,body,accepted_at) "
                    "VALUES (?,?,?,?)",
                    (str(body.request_id), digest, canonical, accepted_at),
                )
        return {
            "request_id": str(body.request_id), "status": "queued", "queue_position": 1,
            "estimated_seconds": body.options.timeout_seconds, "accepted_at": accepted_at,
        }

    @app.get("/api/v1/tcad/jobs/{request_id}")
    def get_candidate(request_id: str, x_fab_token: str | None = Header(default=None)):
        authorize(x_fab_token)
        with sqlite3.connect(path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT body,poll_count FROM candidate_jobs WHERE request_id=?", (request_id,),
            ).fetchone()
            if not row:
                raise HTTPException(404, "job not found")
            body, poll_count = json.loads(row[0]), row[1] + 1
            db.execute(
                "UPDATE candidate_jobs SET poll_count=? WHERE request_id=?",
                (poll_count, request_id),
            )
        if scenario == "timeout":
            poll_count = 1
        if poll_count == 1:
            return {
                "request_id": request_id, "status": "running",
                "progress": {"stage": "iv", "stages": [{"stage": "iv", "status": "running"}]},
            }
        if scenario == "failed":
            return {
                "request_id": request_id, "status": "failed", "result_payload": None,
                "error_code": "SILVACO_FAILED", "error_message": "synthetic deck failure",
            }
        if scenario == "cancelled":
            return {
                "request_id": request_id, "status": "cancelled",
                "cancelled_at": datetime.now(timezone.utc).isoformat(),
            }
        if scenario == "malformed_response":
            return {"status": "succeeded"}
        result = dict(body.get("predicted_outputs") or {})
        if scenario == "out_of_spec" and "vth" in result:
            result["vth"] += 0.5
        return {
            "request_id": request_id, "status": "succeeded", "result_payload": result,
            "metadata": {
                "result_origin": "mock",
                "units": {"vth": "V", "gm": "uS/um", "id_on": "uA/um", "bv": "V"},
                "duration_seconds": 0.01, "warnings": [],
            },
        }

    @app.post("/api/v1/verifications", status_code=202)
    def submit(body: RequestBody):
        if scenario == "server_error":
            raise HTTPException(503, "synthetic TCAD failure")
        canonical = json.dumps(body.model_dump(), sort_keys=True)
        digest = sha256(canonical.encode()).hexdigest()
        with sqlite3.connect(path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT job_id,body_hash FROM jobs WHERE request_id=?", (body.request_id,)
            ).fetchone()
            if row:
                if row[1] != digest:
                    raise HTTPException(409, "request_id content conflict")
                return {"request_id": body.request_id, "job_id": row[0]}
            job_id = str(uuid4())
            values = {key: (range_["min"] + range_["max"]) / 2
                      for key, range_ in body.targets.items()}
            if scenario == "out_of_spec":
                values["vth"] = body.targets["vth"]["max"] + 0.1
            result = {
                "status": "succeeded", "request_id": body.request_id, "job_id": job_id,
                "result_origin": "mock", "deck_template_version": "mock-fixture-v1",
                "y_verified": values,
            }
            db.execute(
                "INSERT INTO jobs VALUES (?,?,?,?)",
                (body.request_id, job_id, digest, json.dumps(result)),
            )
        return {"request_id": body.request_id, "job_id": job_id}

    @app.get("/api/v1/verifications/{job_id}")
    def get(job_id: str):
        with sqlite3.connect(path) as db:
            row = db.execute("SELECT result FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        if not row:
            raise HTTPException(404, "job not found")
        if scenario == "malformed_response":
            return {"status": "succeeded", "job_id": job_id}
        if scenario == "timeout":
            return {"status": "running", "job_id": job_id}
        return json.loads(row[0])

    return app


def main() -> None:
    import os
    import uvicorn
    from event_gateway.config import _read_dotenv

    values = _read_dotenv(Path(".env")) | dict(os.environ)
    path = Path(values.get("TCAD_MOCK_DB_PATH", "data/mock-tcad.sqlite"))
    scenario = values.get("TCAD_MOCK_SCENARIO", "pass")
    uvicorn.run(create_app(path, scenario, values.get("TCAD_API_TOKEN", "")),
                host=values.get("TCAD_BIND_HOST", "127.0.0.1"),
                port=int(values.get("TCAD_BIND_PORT", "8100")))


if __name__ == "__main__":
    main()
