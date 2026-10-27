"""Synthetic event publisher; keeps events until PostgreSQL commit ACK."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from .outbox import Outbox


def make_demo_event(run_id: UUID, lot_id: str) -> dict:
    return {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "run_id": str(run_id),
        "event_type": "anomaly.detected",
        "source": "jetson.virtual_lot",
        "severity": "warning",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {"lot_id": lot_id, "input_origin": "synthetic"},
    }


def make_demo_proposal(run_id: UUID) -> dict:
    """Synthetic contract fixture, not a physical TCAD/ML prediction."""
    current = {key: 1.0 for key in (
        "oxide_thickness", "body_dose", "diffusion_time", "epi_doping"
    )}
    delta = {key: 0.0 for key in current}
    delta["oxide_thickness"] = -0.02
    delta["body_dose"] = 0.01
    observed = {key: 1.0 for key in ("vth", "gm", "id_on", "bv")}
    return {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "run_id": str(run_id),
        "event_type": "correction.proposed",
        "source": "jetson.virtual_lot",
        "severity": "info",
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "proposal_id": str(uuid4()), "run_id": str(run_id),
            "representation": "normalized_ratio", "baseline_version": "demo-v1",
            "x_current": current, "delta_x": delta,
            "x_candidate": {key: current[key] + delta[key] for key in current},
            "y_observed": observed,
            "targets": {key: {"min": 0.9, "max": 1.1} for key in observed},
        },
    }


def main() -> None:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    project_path = Path(os.environ.get("JETSON_PROJECT_PATH", "/home/jetson/project/smart_factory"))
    data_path = project_path / "data"
    data_path.mkdir(parents=True, exist_ok=True)
    run_path = data_path / "demo-run-id"
    if os.environ.get("FAB_RUN_ID"):
        run_id = UUID(os.environ["FAB_RUN_ID"])
    elif run_path.exists():
        run_id = UUID(run_path.read_text(encoding="utf-8").strip())
    else:
        run_id = uuid4()
        run_path.write_text(str(run_id), encoding="utf-8")
    outbox = Outbox(data_path / "event-outbox.sqlite")
    rclpy.init()

    class Publisher(Node):
        def __init__(self):
            super().__init__("fab_virtual_lot")
            event_topic = os.environ.get("ROS_EVENT_TOPIC", "/fab/events")
            ack_topic = os.environ.get("ROS_EVENT_ACK_TOPIC", "/fab/event_acks")
            self.publisher = self.create_publisher(String, event_topic, 10)
            self.create_subscription(String, ack_topic, self.on_ack, 10)
            self.create_timer(2.0, self.republish)

        def on_ack(self, message):
            try:
                receipt = json.loads(message.data)
                if receipt.get("status") == "committed":
                    outbox.ack(UUID(receipt["event_id"]), UUID(receipt["run_id"]),
                               int(receipt["sequence"]))
                elif receipt.get("status") == "dead_lettered":
                    outbox.dead_letter(UUID(receipt["event_id"]), UUID(receipt["run_id"]))
            except (ValueError, KeyError, TypeError):
                self.get_logger().warning("invalid commit receipt")

        def republish(self):
            for pending in outbox.pending():
                message = String()
                message.data = pending.body
                self.publisher.publish(message)

    node = Publisher()
    event = make_demo_event(run_id, f"DEMO-{datetime.now(timezone.utc):%Y%m%d%H%M%S}")
    body = json.dumps(event, separators=(",", ":"))
    outbox.enqueue(UUID(event["event_id"]), run_id, body)
    proposal = make_demo_proposal(run_id)
    outbox.enqueue(UUID(proposal["event_id"]), run_id,
                   json.dumps(proposal, separators=(",", ":")))
    try:
        rclpy.spin(node)
    finally:
        outbox.close()
        node.destroy_node()
        rclpy.shutdown()
