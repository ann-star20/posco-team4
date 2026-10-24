"""Durable ROS adapter for the Jetson diagnosis service."""

import json
import os
from pathlib import Path

import httpx

from .ml_client import ModelHttpClient
from .surrogate_worker import SingleFlightExecutor, SurrogateRuntime


class DiagnosisRuntime(SurrogateRuntime):
    def __init__(self, path):
        super().__init__(path, "diagnosis", "diagnosis.completed", "jetson.diagnosis")


def handle_ack(runtime, ack):
    from uuid import UUID
    if ack.get("status") == "committed":
        runtime.ack(ack["event_id"], ack["run_id"], ack["sequence"])
    elif ack.get("status") == "dead_lettered":
        runtime.outbox.dead_letter(UUID(ack["event_id"]), UUID(ack["run_id"]))


def main():
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    runtime = DiagnosisRuntime(Path(os.environ.get("DIAGNOSIS_RUNTIME_DB", "data/diagnosis.sqlite")))
    mode = os.environ.get("DIAGNOSIS_MODE", "mock")
    if mode not in {"mock", "prod"}:
        raise ValueError("invalid DIAGNOSIS_MODE")
    url = os.environ.get("DIAGNOSIS_PROD_URL" if mode == "prod" else "DIAGNOSIS_MOCK_URL",
                         "" if mode == "prod" else "http://127.0.0.1:8300")
    if not url:
        raise ValueError("diagnosis model URL is required")
    http = httpx.Client(timeout=float(os.environ.get("DIAGNOSIS_TIMEOUT_SECONDS", "30")))
    infer = ModelHttpClient(mode, url, "/api/v1/diagnose", http)
    rclpy.init()

    class Worker(Node):
        def __init__(self):
            super().__init__("fab_diagnosis_worker")
            self.pub = self.create_publisher(String, os.environ.get("ROS_EVENT_TOPIC", "/fab/events"), 10)
            self.create_subscription(String, os.environ.get("ROS_DIAGNOSIS_REQUEST_TOPIC", "/fab/diagnosis_requests"), self.receive, 10)
            self.create_subscription(String, os.environ.get("ROS_EVENT_ACK_TOPIC", "/fab/event_acks"), self.receipt, 10)
            self.create_timer(1.0, self.tick)
            self.runner = SingleFlightExecutor("diagnosis-cpu", self.background_error)

        def background_error(self, _exc):
            self.get_logger().warning(
                f"diagnosis unavailable or invalid response; durable request retained: {_exc!r}")

        def receive(self, msg):
            self.get_logger().warning(f"DEBUG received diagnosis request, {len(msg.data)} bytes")
            try:
                runtime.accept(json.loads(msg.data))
            except (ValueError, KeyError, TypeError):
                self.get_logger().error("invalid diagnosis request")

        def receipt(self, msg):
            try:
                ack = json.loads(msg.data)
                handle_ack(runtime, ack)
            except (ValueError, KeyError, TypeError):
                self.get_logger().error("invalid diagnosis ACK")

        def tick(self):
            self.runner.submit(lambda: runtime.process_next(infer))
            for _, _, body in runtime.pending_events():
                msg = String(); msg.data = body; self.pub.publish(msg)

    node = Worker()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.runner.close(); node.destroy_node(); runtime.close(); http.close()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
