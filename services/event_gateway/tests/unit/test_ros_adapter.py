import json
from uuid import uuid4

from event_gateway.ros_adapter import RosEventAdapter


def test_invalid_then_valid_message():
    received = []
    errors = []
    adapter = RosEventAdapter(received.append, errors.append)
    assert adapter.receive("hello") is False
    event = {
        "schema_version": 1, "event_id": str(uuid4()), "run_id": str(uuid4()),
        "event_type": "anomaly.detected", "source": "jetson.demo", "severity": "warning",
        "occurred_at": "2026-10-14T00:00:00Z", "payload": {"lot_id": "lot-1"}
    }
    assert adapter.receive(json.dumps(event)) is True
    assert len(received) == 1
    assert received[0][1] == event["run_id"]
    assert len(errors) == 1


def test_full_queue_does_not_report_accepted():
    adapter = RosEventAdapter(lambda item: False, lambda reason: None)
    event = {
        "schema_version": 1, "event_id": str(uuid4()), "run_id": str(uuid4()),
        "event_type": "anomaly.detected", "source": "jetson.demo", "severity": "warning",
        "occurred_at": "2026-10-14T00:00:00Z", "payload": {}
    }
    assert adapter.receive(json.dumps(event)) is False
