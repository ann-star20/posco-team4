"""Explicitly unready service scaffold. Never generates simulated prod results."""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException

from event_gateway.config import _read_dotenv


def create_app() -> FastAPI:
    app = FastAPI(title="TCAD workstation service")

    @app.get("/health/live")
    def live():
        return {"status": "ok", "backend": "unconfigured"}

    def unavailable():
        raise HTTPException(503, detail={"code": "backend_not_configured"})

    app.get("/health/ready")(unavailable)
    app.post("/api/v1/verifications")(unavailable)

    @app.get("/api/v1/verifications/{job_id}")
    def get_job(job_id: str):
        raise HTTPException(404, detail={"code": "job_not_found"})

    return app


def main() -> None:
    import uvicorn

    values = _read_dotenv(Path(".env")) | dict(os.environ)
    uvicorn.run(create_app(), host=values.get("TCAD_BIND_HOST", "127.0.0.1"),
                port=int(values.get("TCAD_BIND_PORT", "8200")))


if __name__ == "__main__":
    main()
