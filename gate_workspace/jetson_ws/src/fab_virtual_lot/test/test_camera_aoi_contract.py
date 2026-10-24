from datetime import datetime, timezone
import json
from pathlib import Path
import time
from uuid import uuid4

import numpy as np
from websockets.exceptions import ConnectionClosedError

from fab_virtual_lot.aoi_dispatcher import AoiDispatcher
from fab_virtual_lot.aoi_pipeline import AoiConfig, MockModel, inspect_image
from fab_virtual_lot.aoi_unity import (
    QueuedAoiUnityService,
    build_camera_aoi_services,
    make_aoi_event,
)
from fab_virtual_lot.camera_buffer import CameraFrame, FrameRingBuffer


class FakeWebSocket:
    def __init__(self, messages, fail_after=None):
        self.messages = list(messages)
        self.sent = []
        self.fail_after = fail_after

    def __iter__(self):
        return iter(self.messages)

    def send(self, value):
        if self.fail_after is not None and len(self.sent) >= self.fail_after:
            raise OSError("Unity disconnected")
        self.sent.append(value)


class DisconnectedWebSocket:
    def __iter__(self):
        raise ConnectionClosedError(None, None)
        yield

    def send(self, _value):
        raise AssertionError("disconnected client must not receive data")


def request(frame_id=7, camera_id="camera-1", token="aoi-secret"):
    return {
        "type": "aoi.inspection.requested", "schema_version": 1,
        "request_id": str(uuid4()), "job_id": str(uuid4()),
        "run_id": str(uuid4()), "lot_id": "LOT-1", "unit_id": "MOSFET-1",
        "attempt": 1, "camera_id": camera_id, "frame_id": frame_id,
        "api_token": token,
    }


def add_frame(buffer, frame_id, value=90):
    buffer.put(CameraFrame(frame_id, "camera-1", datetime.now(timezone.utc), time.monotonic_ns(),
                           np.full((64, 96, 3), value, dtype=np.uint8)))


def make_service(tmp_path, buffer, infer=None, queue_size=10, autostart=True):
    config = AoiConfig(tmp_path / "result", .35, .20, .45, .35, "mock", "jetson-1")
    part = MockModel(1, .95, (4, 8, 50, 60))
    defect = MockModel(0, .91, (12, 18, 70, 58))

    def default_infer(req, image):
        result = inspect_image(image, uuid4_from(req["job_id"]), req["attempt"],
                               config, part, defect)
        return make_aoi_event(req, result)

    dispatcher = AoiDispatcher(tmp_path / "jobs.sqlite", tmp_path / "spool",
                               infer or default_infer, queue_size=queue_size,
                               autostart=autostart)
    return QueuedAoiUnityService(buffer, dispatcher, "camera-1", "aoi-secret",
                                 completion_wait_seconds=2), dispatcher


def uuid4_from(value):
    from uuid import UUID
    return UUID(value)


def text_messages(websocket):
    return [json.loads(value) for value in websocket.sent if isinstance(value, str)]


def test_requested_display_frame_is_accepted_and_completed_with_annotated_jpeg(tmp_path):
    buffer = FrameRingBuffer(10, 1024 * 1024)
    add_frame(buffer, 7, 123)
    service, dispatcher = make_service(tmp_path, buffer)
    body = request()
    websocket = FakeWebSocket([json.dumps(body)])

    service.handle(websocket)
    dispatcher.close()

    messages = text_messages(websocket)
    assert [message["type"] for message in messages] == [
        "aoi.inspection.accepted", "aoi.inspection.completed"
    ]
    assert messages[0]["frame_id"] == 7
    assert messages[1]["request_id"] == body["request_id"]
    assert messages[1]["image"]["binary_frame_follows"] is True
    assert websocket.sent[-1].startswith(b"\xff\xd8")


def test_stale_frame_is_rejected_without_substituting_latest(tmp_path):
    calls = []
    buffer = FrameRingBuffer(10, 1024 * 1024)
    add_frame(buffer, 11)
    service, dispatcher = make_service(tmp_path, buffer,
                                       infer=lambda req, image: calls.append(req))
    websocket = FakeWebSocket([json.dumps(request(frame_id=10))])

    service.handle(websocket)
    dispatcher.close()

    message = text_messages(websocket)[0]
    assert message["type"] == "aoi.inspection.rejected"
    assert message["error_code"] == "stale_frame"
    assert message["oldest_available_frame_id"] == 11
    assert message["latest_available_frame_id"] == 11
    assert calls == []


def test_queue_full_and_auth_or_camera_mismatch_are_rejected(tmp_path):
    buffer = FrameRingBuffer(10, 1024 * 1024)
    add_frame(buffer, 7)
    service, dispatcher = make_service(tmp_path, buffer, infer=lambda req, image: {},
                                       queue_size=1, autostart=False)
    dispatcher.submit(request(), buffer.get_copy(7))

    queue_full = FakeWebSocket([json.dumps(request())])
    service.handle(queue_full)
    assert text_messages(queue_full)[0]["error_code"] == "queue_full"

    unauthorized = FakeWebSocket([json.dumps(request(token="wrong"))])
    service.handle(unauthorized)
    assert text_messages(unauthorized)[0]["error_code"] == "invalid_request"

    wrong_camera = FakeWebSocket([json.dumps(request(camera_id="other"))])
    service.handle(wrong_camera)
    assert text_messages(wrong_camera)[0]["error_code"] == "invalid_request"
    dispatcher.close()


def test_unity_disconnect_does_not_cancel_persisted_job(tmp_path):
    buffer = FrameRingBuffer(10, 1024 * 1024)
    add_frame(buffer, 7)
    service, dispatcher = make_service(tmp_path, buffer)
    body = request()
    websocket = FakeWebSocket([json.dumps(body)], fail_after=1)

    service.handle(websocket)
    record = dispatcher.get(body["job_id"])
    dispatcher.close()

    assert record.status == "succeeded"
    assert record.result["event_type"] == "aoi.inspection.completed"


def test_client_connection_error_is_a_normal_handler_exit(tmp_path):
    buffer = FrameRingBuffer(10, 1024 * 1024)
    service, dispatcher = make_service(tmp_path, buffer)

    service.handle(DisconnectedWebSocket())
    dispatcher.close()


def test_runtime_composition_shares_one_camera_buffer(tmp_path):
    fixture = tmp_path / "fixture.jpg"
    assert cv2_write(fixture, np.full((20, 30, 3), 100, dtype=np.uint8))
    config = AoiConfig(tmp_path / "result", .35, .20, .45, .35, "mock", "jetson-1")
    env = {
        "CAMERA_MODE": "mock", "CAMERA_ID": "camera-1",
        "CAMERA_FIXTURE_PATH": str(fixture), "CAMERA_CAPTURE_FPS": "100",
        "CAMERA_RING_BUFFER_SECONDS": "2", "CAMERA_RING_BUFFER_MAX_MB": "1",
        "CAMERA_RECONNECT_INTERVAL_SECONDS": ".01",
        "CAMERA_PREVIEW_TOKEN": "preview-secret", "AOI_UNITY_TOKEN": "aoi-secret",
        "AOI_RUNTIME_DB": str(tmp_path / "runtime.sqlite"),
        "AOI_FRAME_SPOOL_DIR": str(tmp_path / "spool"),
        "AOI_QUEUE_SIZE": "2", "AOI_EXECUTOR_WORKERS": "1",
    }
    components = build_camera_aoi_services(
        config, (MockModel(1, .95, (1, 1, 10, 10)), MockModel(0, 0, (1, 1, 2, 2))),
        event_sink=None, env=env,
    )
    components.preview.start()
    components.camera.start()
    wait_deadline = time.time() + 1
    while components.buffer.stats().frame_count == 0 and time.time() < wait_deadline:
        time.sleep(.005)
    components.close()

    assert components.aoi.buffer is components.buffer
    assert components.buffer.stats().frame_count >= 1


def cv2_write(path: Path, image: np.ndarray) -> bool:
    import cv2
    return bool(cv2.imwrite(str(path), image))
