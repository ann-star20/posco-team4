"""Direct Jetson AOI WebSocket endpoint for Unity real-time display."""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from queue import Queue
import sqlite3
from threading import Event, Lock, Thread
import time
from typing import Callable, Mapping
from uuid import UUID, uuid4

from websockets.exceptions import ConnectionClosed

from .aoi_pipeline import AoiConfig, inspect_image
from .aoi_dispatcher import AoiCompletion, AoiDispatcher, AoiQueueFull
from .camera_buffer import FrameRingBuffer
from .camera_preview import CameraPreviewService, PreviewSettings
from .camera_service import CameraCaptureService
from .camera_source import CameraSettings, make_camera_source
from .outbox import Outbox


def websocket_max_bytes(env=os.environ) -> int:
    value = int(env.get("AOI_UNITY_MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))
    if value < 1024 * 1024 or value > 64 * 1024 * 1024:
        raise ValueError("AOI_UNITY_MAX_IMAGE_BYTES must be between 1 MiB and 64 MiB")
    return value


def ros_persistence_enabled(env=os.environ) -> bool:
    value = env.get("AOI_ROS_PERSISTENCE_ENABLED", "true").strip().lower()
    if value not in {"true", "false"}:
        raise ValueError("AOI_ROS_PERSISTENCE_ENABLED must be true or false")
    return value == "true"


class AoiUnityOutbox:
    """Thread-safe facade over the on-device SQLite event outbox."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = Lock()

    def enqueue(self, event: dict) -> None:
        event_id = UUID(event["event_id"])
        run_id = UUID(event["run_id"])
        body = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with self.lock, Outbox(self.path) as outbox:
            outbox.enqueue(event_id, run_id, body)

    def pending_bodies(self) -> list[str]:
        with self.lock, Outbox(self.path) as outbox:
            return [event.body for event in outbox.pending()]

    def receive_ack(self, raw: str) -> bool:
        ack = json.loads(raw)
        event_id = UUID(ack["event_id"])
        run_id = UUID(ack["run_id"])
        with self.lock, Outbox(self.path) as outbox:
            if ack.get("status") == "committed":
                return outbox.ack(event_id, run_id, int(ack["sequence"]))
            if ack.get("status") == "dead_lettered":
                return outbox.dead_letter(event_id, run_id)
        return False


def _validate_request(request: dict, token: str) -> None:
    if request.get("type") != "aoi.inspection.requested" or request.get("schema_version") != 1:
        raise ValueError("invalid AOI Unity request type")
    for key in ("request_id", "job_id", "run_id"):
        UUID(str(request[key]))
    if int(request.get("attempt", 0)) < 1:
        raise ValueError("invalid AOI attempt")
    for key in ("lot_id", "unit_id"):
        if not isinstance(request.get(key), str) or not request[key].strip():
            raise ValueError(f"invalid {key}")
    fixture = request.get("fixture_name")
    if (not isinstance(fixture, str) or not fixture or fixture in {".", ".."}
            or "/" in fixture or "\\" in fixture):
        raise ValueError("fixture_name must be a file name")
    if token and request.get("api_token") != token:
        raise ValueError("invalid Unity token")


def _public_detection(detection: dict) -> dict:
    return {key: detection[key] for key in
            ("class_id", "class_name", "confidence", "bbox_xyxy")}


def build_unity_result(event: dict) -> tuple[dict, bytes]:
    payload = event["payload"]
    image = payload.get("images", {}).get("annotated")
    if not image:
        raise ValueError("annotated image metadata is missing")
    path = Path(image["local_directory"]) / image["file_name"]
    if not path.is_file():
        raise ValueError("annotated image file is missing")
    data = path.read_bytes()
    digest = sha256(data).hexdigest()
    if digest != image["sha256"] or len(data) != int(image["byte_size"]):
        raise ValueError("annotated image integrity check failed")
    detections = payload.get("detections", [])
    result = {
        "type": "aoi.inspection.completed",
        "schema_version": 1,
        "message_id": event["event_id"],
        "request_id": payload["request_id"],
        "job_id": payload["job_id"],
        "run_id": event["run_id"],
        "lot_id": payload["lot_id"],
        "unit_id": payload["unit_id"],
        "attempt": payload["attempt"],
        "device_id": payload["device_id"],
        "result_origin": payload["result_origin"],
        "verdict": payload["verdict"],
        "defect_detected": any(d["model_stage"] == "defect" for d in detections),
        "processing_ms": payload["processing_ms"],
        "thresholds": payload["thresholds"],
        "parts": [_public_detection(d) for d in detections if d["model_stage"] == "part"],
        "defects": [_public_detection(d) for d in detections if d["model_stage"] == "defect"],
        "image": {
            "image_id": image["artifact_id"],
            "frame_role": "annotated",
            "mime_type": "image/jpeg",
            "file_name": image["file_name"],
            "byte_length": len(data),
            "sha256": digest,
            "width": image["width"],
            "height": image["height"],
            "jetson_path": str(path),
            "binary_frame_follows": True,
        },
        "occurred_at": event["occurred_at"],
    }
    return result, data


def make_aoi_event(request: dict, result: dict) -> dict:
    """Build the durable event shared by direct and queued AOI paths."""
    return {
        "schema_version": 1,
        "event_id": str(uuid4()),
        "run_id": request["run_id"],
        "event_type": "aoi.inspection.completed",
        "source": "jetson.aoi",
        "severity": "warning" if result["verdict"] != "pass" else "info",
        "correlation_id": request["request_id"],
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {
            **result,
            "request_id": request["request_id"],
            "lot_id": request["lot_id"],
            "unit_id": request["unit_id"],
            "camera_id": request.get("camera_id"),
            "frame_id": request.get("frame_id"),
            "processing_ms": result.get("processing_ms", 0.0),
        },
    }


def _validate_camera_request(request: dict, camera_id: str, token: str) -> None:
    if request.get("type") != "aoi.inspection.requested" or request.get("schema_version") != 1:
        raise ValueError("invalid AOI request type")
    for key in ("request_id", "job_id", "run_id"):
        UUID(str(request[key]))
    if int(request.get("attempt", 0)) < 1:
        raise ValueError("invalid AOI attempt")
    for key in ("lot_id", "unit_id"):
        if not isinstance(request.get(key), str) or not request[key].strip():
            raise ValueError(f"invalid {key}")
    if request.get("camera_id") != camera_id:
        raise ValueError("invalid camera_id")
    if not isinstance(request.get("frame_id"), int) or request["frame_id"] < 0:
        raise ValueError("invalid frame_id")
    if token and request.get("api_token") != token:
        raise ValueError("invalid Unity token")


class QueuedAoiUnityService:
    """Frame-specific asynchronous Unity AOI control connection."""

    def __init__(self, buffer: FrameRingBuffer, dispatcher: AoiDispatcher,
                 camera_id: str, token: str, max_image_bytes: int = 8 * 1024 * 1024,
                 completion_wait_seconds: float = 30) -> None:
        self.buffer = buffer
        self.dispatcher = dispatcher
        self.camera_id = camera_id
        self.token = token
        self.max_image_bytes = max_image_bytes
        self.completion_wait_seconds = completion_wait_seconds

    def handle(self, websocket) -> None:
        outgoing: Queue = Queue()
        pending: set[str] = set()
        pending_lock = Lock()
        all_done = Event()
        all_done.set()

        def sender() -> None:
            failed = False
            while True:
                item = outgoing.get()
                if item is None:
                    return
                if failed:
                    continue
                try:
                    metadata, image = item
                    websocket.send(json.dumps(metadata, ensure_ascii=False,
                                              separators=(",", ":")))
                    if image is not None:
                        websocket.send(image)
                except Exception:
                    failed = True

        send_thread = Thread(target=sender, name="aoi-unity-sender", daemon=True)
        send_thread.start()

        def completed(completion: AoiCompletion) -> None:
            try:
                if completion.status == "succeeded" and completion.result is not None:
                    metadata, image = build_unity_result(completion.result)
                    if len(image) > self.max_image_bytes:
                        raise ValueError("annotated image exceeds configured WebSocket limit")
                    outgoing.put((metadata, image))
                else:
                    outgoing.put(({
                        "type": "aoi.inspection.failed", "schema_version": 1,
                        "job_id": completion.job_id,
                        "error_code": completion.error_code or "inference_failed",
                    }, None))
            except Exception:
                outgoing.put(({
                    "type": "aoi.inspection.failed", "schema_version": 1,
                    "job_id": completion.job_id,
                    "error_code": "result_unavailable",
                }, None))
            finally:
                with pending_lock:
                    pending.discard(completion.job_id)
                    if not pending:
                        all_done.set()

        try:
            for raw in websocket:
                try:
                    if not isinstance(raw, str):
                        raise ValueError("request must be JSON text")
                    request = json.loads(raw)
                    _validate_camera_request(request, self.camera_id, self.token)
                    selected = self.buffer.get_copy(request["frame_id"])
                    if selected is None:
                        bounds = self.buffer.bounds()
                        outgoing.put(({
                            "type": "aoi.inspection.rejected", "schema_version": 1,
                            "request_id": request["request_id"],
                            "error_code": "stale_frame",
                            "requested_frame_id": request["frame_id"],
                            "oldest_available_frame_id": bounds.oldest_frame_id,
                            "latest_available_frame_id": bounds.latest_frame_id,
                        }, None))
                        continue
                    accepted = self.dispatcher.submit(request, selected)
                    with pending_lock:
                        pending.add(accepted.job_id)
                        all_done.clear()
                    outgoing.put(({
                        "type": "aoi.inspection.accepted", "schema_version": 1,
                        "request_id": accepted.request_id, "job_id": accepted.job_id,
                        "frame_id": accepted.frame_id, "status": accepted.status,
                    }, None))
                    self.dispatcher.subscribe(accepted.job_id, completed)
                except AoiQueueFull:
                    outgoing.put(({
                        "type": "aoi.inspection.rejected", "schema_version": 1,
                        "request_id": request.get("request_id"),
                        "error_code": "queue_full", "retry_after_ms": 1000,
                    }, None))
                except (ValueError, KeyError, TypeError, json.JSONDecodeError):
                    outgoing.put(({
                        "type": "aoi.inspection.rejected", "schema_version": 1,
                        "error_code": "invalid_request",
                    }, None))
            all_done.wait(self.completion_wait_seconds)
        except ConnectionClosed:
            pass
        finally:
            outgoing.put(None)
            send_thread.join(timeout=3)


@dataclass
class CameraAoiComponents:
    buffer: FrameRingBuffer
    camera: CameraCaptureService
    preview: CameraPreviewService
    dispatcher: AoiDispatcher
    aoi: QueuedAoiUnityService

    def close(self) -> None:
        self.camera.stop()
        self.preview.close()
        self.dispatcher.close()


def build_camera_aoi_services(config: AoiConfig, models: tuple,
                              event_sink: Callable[[dict], None] | None,
                              env: Mapping[str, str] = os.environ) -> CameraAoiComponents:
    camera_settings = CameraSettings.from_env(env)
    buffer = FrameRingBuffer(
        max_age_seconds=float(env.get("CAMERA_RING_BUFFER_SECONDS", "2")),
        max_bytes=int(float(env.get("CAMERA_RING_BUFFER_MAX_MB", "128")) * 1024 * 1024),
    )
    camera = CameraCaptureService(
        lambda: make_camera_source(camera_settings), buffer, camera_settings.camera_id,
        capture_fps=float(env.get("CAMERA_CAPTURE_FPS", "10")),
        reconnect_interval_seconds=float(
            env.get("CAMERA_RECONNECT_INTERVAL_SECONDS", "3")
        ),
    )
    preview_settings = PreviewSettings(
        camera_id=camera_settings.camera_id,
        token=env.get("CAMERA_PREVIEW_TOKEN", ""),
        width=int(env.get("CAMERA_PREVIEW_WIDTH", "1280")),
        height=int(env.get("CAMERA_PREVIEW_HEIGHT", "720")),
        fps=int(env.get("CAMERA_PREVIEW_FPS", "5")),
        jpeg_quality=int(env.get("CAMERA_PREVIEW_JPEG_QUALITY", "75")),
        max_clients=int(env.get("CAMERA_PREVIEW_MAX_CLIENTS", "2")),
    )
    preview = CameraPreviewService(preview_settings)
    camera.subscribe(preview.publish)
    part_model, defect_model = models

    def infer(request: dict, image) -> dict:
        started = time.perf_counter()
        result = inspect_image(image, UUID(request["job_id"]), int(request["attempt"]),
                               config, part_model, defect_model)
        result = {**result,
                  "processing_ms": round((time.perf_counter() - started) * 1000, 3)}
        event = make_aoi_event(request, result)
        if event_sink is not None:
            event_sink(event)
        return event

    runtime_db = Path(env.get(
        "AOI_RUNTIME_DB", str(config.result_dir.parent / "aoi-unity.sqlite")
    ))
    spool_dir = Path(env.get(
        "AOI_FRAME_SPOOL_DIR", str(config.result_dir.parent / "aoi-frame-spool")
    ))
    dispatcher = AoiDispatcher(
        runtime_db, spool_dir, infer,
        queue_size=int(env.get("AOI_QUEUE_SIZE", "10")),
        workers=int(env.get("AOI_EXECUTOR_WORKERS", "1")),
    )
    dispatcher.recover()
    aoi = QueuedAoiUnityService(
        buffer, dispatcher, camera_settings.camera_id,
        env.get("AOI_UNITY_TOKEN", ""),
        max_image_bytes=websocket_max_bytes(env),
        completion_wait_seconds=float(env.get("AOI_COMPLETION_WAIT_SECONDS", "30")),
    )
    return CameraAoiComponents(buffer, camera, preview, dispatcher, aoi)


class AoiUnityService:
    def __init__(self, config: AoiConfig, capture: Callable, part_model, defect_model,
                 token: str = "", max_image_bytes: int = 8 * 1024 * 1024,
                 event_sink: Callable[[dict], None] | None = None) -> None:
        self.config = config
        self.capture = capture
        self.part_model = part_model
        self.defect_model = defect_model
        self.token = token
        self.max_image_bytes = max_image_bytes
        self.event_sink = event_sink

    def inspect(self, request: dict) -> tuple[dict, bytes]:
        _validate_request(request, self.token)
        started = time.perf_counter()
        result = inspect_image(self.capture(request), UUID(request["job_id"]),
                               int(request["attempt"]), self.config,
                               self.part_model, self.defect_model)
        event = {
            "schema_version": 1,
            "event_id": str(uuid4()),
            "run_id": request["run_id"],
            "event_type": "aoi.inspection.completed",
            "source": "jetson.aoi",
            "severity": "warning" if result["verdict"] != "pass" else "info",
            "correlation_id": request["request_id"],
            "occurred_at": datetime.now(timezone.utc).isoformat(),
            "payload": {
                **result,
                "request_id": request["request_id"],
                "lot_id": request["lot_id"],
                "unit_id": request["unit_id"],
                "processing_ms": round((time.perf_counter() - started) * 1000, 3),
            },
        }
        metadata, image = build_unity_result(event)
        if len(image) > self.max_image_bytes:
            raise ValueError("annotated image exceeds configured WebSocket limit")
        if self.event_sink is not None:
            self.event_sink(event)
        metadata["persistence_status"] = "queued" if self.event_sink is not None else "disabled"
        return metadata, image

    def handle(self, websocket) -> None:
        for raw in websocket:
            try:
                if not isinstance(raw, str):
                    raise ValueError("request must be JSON text")
                metadata, image = self.inspect(json.loads(raw))
                websocket.send(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")))
                websocket.send(image)
            except (ValueError, KeyError, TypeError, OSError, sqlite3.Error,
                    json.JSONDecodeError):
                websocket.send(json.dumps({"type": "aoi.inspection.failed",
                                           "schema_version": 1,
                                           "error_code": "invalid_or_unavailable_input"}))


def main() -> None:
    from websockets.sync.server import serve
    from .aoi_worker import make_models

    config = AoiConfig.from_env()
    models = make_models(config)
    max_bytes = websocket_max_bytes()
    persistence = ros_persistence_enabled()
    outbox = None
    node = None
    ros = None
    spin_thread = None
    if persistence:
        import rclpy
        from rclpy.node import Node
        from std_msgs.msg import String

        ros = rclpy
        runtime_db = Path(os.environ.get(
            "AOI_RUNTIME_DB", str(config.result_dir.parent / "aoi-unity.sqlite")))
        outbox = AoiUnityOutbox(runtime_db)
        ros.init()

        class Bridge(Node):
            def __init__(self):
                super().__init__("fab_aoi_unity_bridge")
                self.publisher = self.create_publisher(
                    String, os.environ.get("ROS_EVENT_TOPIC", "/fab/events"), 10)
                self.create_subscription(
                    String, os.environ.get("ROS_EVENT_ACK_TOPIC", "/fab/event_acks"),
                    self.on_ack, 10)
                self.create_timer(1.0, self.publish_pending)

            def on_ack(self, message):
                try:
                    outbox.receive_ack(message.data)
                except (ValueError, KeyError, TypeError, sqlite3.Error,
                        json.JSONDecodeError):
                    self.get_logger().warning("invalid AOI persistence ACK")

            def publish_pending(self):
                for body in outbox.pending_bodies():
                    message = String()
                    message.data = body
                    self.publisher.publish(message)

        node = Bridge()
        spin_thread = Thread(target=ros.spin, args=(node,), daemon=True)
        spin_thread.start()

    components = build_camera_aoi_services(
        config, models, outbox.enqueue if outbox is not None else None
    )
    host = os.environ.get("AOI_UNITY_WS_HOST", "0.0.0.0")
    port = int(os.environ.get("AOI_UNITY_WS_PORT", "8400"))
    preview_host = os.environ.get("CAMERA_PREVIEW_HOST", "0.0.0.0")
    preview_port = int(os.environ.get("CAMERA_PREVIEW_PORT", "8500"))
    print(f"AOI Unity WebSocket ready: ws://{host}:{port}/aoi "
          f"ROS persistence={'enabled' if persistence else 'disabled'}", flush=True)
    print(f"Camera Preview WebSocket ready: "
          f"ws://{preview_host}:{preview_port}/camera/preview", flush=True)
    preview_thread = None
    try:
        components.preview.start()
        components.camera.start()
        with serve(components.preview.handle, preview_host, preview_port,
                   max_size=1024 * 1024) as preview_server, \
                serve(components.aoi.handle, host, port, max_size=max_bytes) as aoi_server:
            preview_thread = Thread(target=preview_server.serve_forever,
                                    name="camera-preview-ws", daemon=True)
            preview_thread.start()
            aoi_server.serve_forever()
    finally:
        components.close()
        if preview_thread is not None:
            preview_thread.join(timeout=3)
        if node is not None:
            node.destroy_node()
        if ros is not None and ros.ok():
            ros.shutdown()
        if spin_thread is not None:
            spin_thread.join(timeout=3)


if __name__ == "__main__":
    main()
