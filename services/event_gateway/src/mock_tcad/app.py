"""Deterministic mock TCAD server with durable request ID mapping."""

from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class RequestBody(BaseModel):
    request_id: str
    proposal_id: str
    targets: dict[str, dict[str, float]]


def create_app(path: Path, scenario: str = "pass") -> FastAPI:
    if scenario not in {"pass", "out_of_spec", "timeout", "server_error", "malformed_response"}:
        raise ValueError("unknown mock scenario")
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS jobs("
            "request_id TEXT PRIMARY KEY,job_id TEXT UNIQUE NOT NULL,body_hash TEXT NOT NULL,"
            "result TEXT NOT NULL)"
        )
    app = FastAPI()

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
    uvicorn.run(create_app(path, scenario), host="127.0.0.1", port=8100)


if __name__ == "__main__":
    main()
