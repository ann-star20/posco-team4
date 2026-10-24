"""One-shot ROS AOI request publisher for a single-host integration test."""

import argparse
import json
import os
import time
from uuid import UUID, uuid4


def make_request(run_id: UUID, lot_id: str) -> dict:
    if not lot_id.strip():
        raise ValueError("lot_id is required")
    return {"schema_version": 1, "request_id": str(uuid4()),
            "job_id": str(uuid4()), "run_id": str(run_id),
            "attempt": 1, "lot_id": lot_id, "task_type": "aoi"}


def main():
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    parser = argparse.ArgumentParser(description="단일 호스트 AOI ROS 시험 요청")
    parser.add_argument("--run-id", type=UUID, default=None)
    parser.add_argument("--lot-id", default="WSL-AOI-TEST")
    args = parser.parse_args()
    request = make_request(args.run_id or uuid4(), args.lot_id)
    rclpy.init()
    node = Node("fab_aoi_request_cli")
    publisher = node.create_publisher(
        String, os.environ.get("ROS_INFERENCE_REQUEST_TOPIC", "/fab/inference_requests"), 10)
    try:
        for _ in range(50):
            if publisher.get_subscription_count():
                break
            time.sleep(.1)
        if not publisher.get_subscription_count():
            raise RuntimeError("AOI request subscriber unavailable")
        msg = String()
        msg.data = json.dumps(request, separators=(",", ":"))
        publisher.publish(msg)
        time.sleep(.5)
        print(json.dumps(request, ensure_ascii=False))
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
