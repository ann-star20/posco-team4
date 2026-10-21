from event_gateway.app import create_app
from event_gateway.config import Settings


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
