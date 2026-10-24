"""ROS 2 AOI worker. Runs unchanged on Jetson or a WSL test host."""

import json
import os
from pathlib import Path
from uuid import UUID

import cv2

from .aoi_pipeline import AoiConfig, RelativeMockModel, UltralyticsModel, model_paths
from .aoi_runtime import AoiRuntime


def load_fixture(request: dict):
    name = request.get("fixture_name")
    if name is None:
        path = Path(os.environ["CAMERA_FIXTURE_PATH"])
    else:
        if not isinstance(name, str) or not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError("fixture_name must be a file name")
        path = Path(os.environ["AOI_IMAGE_DIR"]) / name
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("AOI fixture image cannot be read")
    return image


def capture_camera(_request: dict):
    url = os.environ["CAMERA_SOURCE_URL"]
    capture = cv2.VideoCapture(url)
    try:
        if not capture.isOpened():
            raise OSError("AOI camera unavailable")
        for _ in range(3):
            okay, frame = capture.read()
            if not okay:
                raise OSError("AOI camera frame unavailable")
        return frame
    finally:
        capture.release()


def make_models(config: AoiConfig):
    if config.mode == "mock":
        defect = os.environ.get("AOI_MOCK_DEFECT", "none")
        if defect not in {"none", "crash", "bend"}:
            raise ValueError("invalid AOI_MOCK_DEFECT")
        return (RelativeMockModel(0, .97, (.38, .42, .64, .66)),
                RelativeMockModel({"crash": 0, "bend": 1}.get(defect, 0),
                                  .92 if defect != "none" else 0,
                                  (.40, .47, .63, .58)))
    part, defect = model_paths()
    device = os.environ.get("AOI_INFER_DEVICE", "cpu")
    precision = os.environ.get("AOI_INFER_PRECISION", "fp32")
    return (UltralyticsModel(part, device, precision),
            UltralyticsModel(defect, device, precision))


def main():
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    config = AoiConfig.from_env()
    print("AOI config loaded", flush=True)
    runtime_db = Path(os.environ.get("AOI_RUNTIME_DB", str(config.result_dir.parent / "aoi.sqlite")))
    runtime_db.parent.mkdir(parents=True, exist_ok=True)
    models = make_models(config)
    print("AOI models loaded", flush=True)
    camera_mode = os.environ.get("CAMERA_MODE", "mock")
    if camera_mode not in {"mock", "prod"}:
        raise ValueError("CAMERA_MODE must be mock or prod")
    capture = load_fixture if camera_mode == "mock" else capture_camera
    runtime = AoiRuntime(runtime_db, config)
    print("AOI inbox open", flush=True)
    rclpy.init()
    print("AOI ROS initialized", flush=True)

    class Worker(Node):
        def __init__(self):
            super().__init__("fab_aoi_worker")
            self.results = self.create_publisher(String, os.environ.get("ROS_EVENT_TOPIC", "/fab/events"), 10)
            self.create_subscription(String, os.environ.get("ROS_INFERENCE_REQUEST_TOPIC", "/fab/inference_requests"),
                                     self.on_request, 10)
            self.create_subscription(String, os.environ.get("ROS_EVENT_ACK_TOPIC", "/fab/event_acks"),
                                     self.on_ack, 10)
            self.create_timer(1.0, self.tick)

        def on_request(self, message):
            try:
                request = json.loads(message.data)
                runtime.accept(request)
            except (ValueError, KeyError, TypeError) as exc:
                self.get_logger().warning("invalid AOI request: " + type(exc).__name__)

        def on_ack(self, message):
            try:
                ack = json.loads(message.data)
                if ack.get("status") == "committed":
                    runtime.ack(ack["event_id"], ack["run_id"], int(ack["sequence"]))
                elif ack.get("status") == "dead_lettered":
                    runtime.outbox.dead_letter(UUID(ack["event_id"]), UUID(ack["run_id"]))
            except (ValueError, KeyError, TypeError):
                self.get_logger().warning("invalid AOI ACK")

        def tick(self):
            try:
                runtime.process_next(capture, *models)
            except (ValueError, OSError, KeyError) as exc:
                self.get_logger().error("AOI processing failed: " + type(exc).__name__)
            for _, _, body in runtime.pending_events():
                message = String()
                message.data = body
                self.results.publish(message)

    node = Worker()
    print("AOI ROS subscriptions ready", flush=True)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        runtime.close()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
