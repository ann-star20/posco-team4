"""Shared mock/prod TCAD HTTP contract."""

from dataclasses import dataclass
import httpx

from .contracts import VerificationResult
from .tcad_contracts import TcadAcceptance, TcadJobStatus, TcadVerificationRequest


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


class TcadCandidateClient:
    """Authenticated adapter for the request-id keyed TCAD v1 API."""

    def __init__(self, http: httpx.Client, api_token: str):
        self.http = http
        self._api_token = api_token

    def __repr__(self) -> str:
        return f"{type(self).__name__}(http={self.http!r}, api_token=<redacted>)"

    @property
    def _headers(self) -> dict[str, str]:
        return {"X-Fab-Token": self._api_token}

    def submit(self, request: TcadVerificationRequest) -> TcadAcceptance:
        response = self.http.post(
            "/api/v1/tcad/verify",
            json=request.model_dump(mode="json", exclude_none=True),
            headers=self._headers,
        )
        if response.status_code != 202:
            if response.is_error:
                response.raise_for_status()
            raise ValueError("TCAD acceptance must use HTTP 202")
        accepted = TcadAcceptance.model_validate(response.json())
        if accepted.request_id != request.request_id:
            raise ValueError("TCAD acceptance identity mismatch")
        return accepted

    def poll(self, tcad_request_id) -> TcadJobStatus:
        response = self.http.get(
            f"/api/v1/tcad/jobs/{tcad_request_id}", headers=self._headers,
        )
        response.raise_for_status()
        status = TcadJobStatus.model_validate(response.json())
        if str(status.request_id) != str(tcad_request_id):
            raise ValueError("TCAD poll identity mismatch")
        return status
