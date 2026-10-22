from event_gateway.app import create_app
from event_gateway.config import Settings
from pathlib import Path


ROOT = Path(__file__).parents[4]


def test_gateway_exposes_replay_and_stream():
    app = create_app(Settings(database_url="postgresql://example:secret@localhost/test"))
    paths = {route.path for route in app.routes}
    assert "/api/v1/events" in paths
    assert "/api/v1/stream" in paths
    assert "/health/live" in paths
    assert "/api/v1/inspection-jobs" in paths
    assert "/api/v1/control" in paths
    assert "/api/v1/inspection-jobs/{job_id}" in paths
    assert "/api/v1/diagnosis-jobs" in paths


def test_tcad_v1_contract_and_korean_e2e_runbook_are_published():
    openapi = (ROOT / "docs/api/openapi.yaml").read_text(encoding="utf-8")
    assert "/api/v1/tcad/verify:" in openapi
    assert "/api/v1/tcad/jobs/{request_id}:" in openapi
    assert "name: X-Fab-Token" in openapi
    for status in ("queued", "running", "succeeded", "failed", "cancelled"):
        assert status in openapi
    for field in ("proposal_id", "tcad_request_id", "candidate_index"):
        assert field in openapi

    runbook = (ROOT / "docs/runbooks/tcad-verification-service-e2e.md").read_text(
        encoding="utf-8"
    )
    for text in ("TCAD_MODE=mock", "TCAD_MODE=prod", "schema_migrations",
                 "tcad_verification_candidates", "after_sequence", "review_required"):
        assert text in runbook
    assert "tomato-tcadv" not in runbook
