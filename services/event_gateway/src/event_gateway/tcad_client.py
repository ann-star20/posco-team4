"""Shared mock/prod TCAD HTTP contract."""

from dataclasses import dataclass
import httpx

from .contracts import VerificationResult


@dataclass(frozen=True)
class AcceptedJob:
    request_id: str
    job_id: str


class TcadClient:
    def __init__(self, http: httpx.Client):
        self.http = http

    def submit(self, payload: dict) -> AcceptedJob:
        response = self.http.post("/api/v1/verifications", json=payload)
        if response.status_code != 202:
            response.raise_for_status()
            raise ValueError("TCAD acceptance must use HTTP 202")
        data = response.json()
        if data.get("request_id") != payload.get("request_id") or not data.get("job_id"):
            raise ValueError("invalid TCAD acceptance response")
        return AcceptedJob(data["request_id"], data["job_id"])

    def poll(self, job_id: str) -> dict:
        response = self.http.get(f"/api/v1/verifications/{job_id}")
        response.raise_for_status()
        data = response.json()
        if data.get("status") == "succeeded":
            VerificationResult.model_validate({
                key: value for key, value in data.items() if key != "status"
            })
        elif data.get("status") not in {"queued", "running", "failed"}:
            raise ValueError("invalid TCAD status")
        return data
