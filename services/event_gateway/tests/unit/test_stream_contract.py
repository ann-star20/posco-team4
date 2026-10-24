from uuid import uuid4

from event_gateway.stream import format_unity_event


def test_correction_event_exposes_recommended_values_and_mock_origin():
    row = {
        "sequence": 7, "event_id": str(uuid4()), "event_type": "correction.verified",
        "run_id": str(uuid4()), "payload": {
            "x_current": {"oxide_thickness": 1.0, "body_dose": 1.0},
            "delta_x": {"oxide_thickness": -0.03, "body_dose": 0.05},
            "x_candidate": {"oxide_thickness": 0.97, "body_dose": 1.05},
            "result_origin": "mock",
        },
    }
    formatted = format_unity_event(row, unity_mode="prod")
    assert formatted["correction"]["oxide_thickness"]["recommended"] == 0.97
    assert formatted["correction"]["body_dose"]["delta"] == 0.05
    assert formatted["approval_allowed"] is False
