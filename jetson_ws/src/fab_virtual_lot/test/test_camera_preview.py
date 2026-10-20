import json
from threading import Event, Lock, Thread
import time

import numpy as np

from fab_virtual_lot.camera_buffer import CameraFrame
from fab_virtual_lot.camera_preview import CameraPreviewService, PreviewSettings


def make_frame(frame_id, value=80):
    from datetime import datetime, timezone
    return CameraFrame(frame_id, "camera-1", datetime.now(timezone.utc), frame_id,
                       np.full((24, 32, 3), value, dtype=np.uint8))


class FakeWebSocket:
    def __init__(self, token="preview-secret", block_first_binary=False):
        self.request = json.dumps({
            "type": "camera.preview.subscribe", "schema_version": 1,
            "camera_id": "camera-1", "api_token": token,
            "preferred_width": 16, "preferred_height": 12, "preferred_fps": 5,
        })
        self.sent = []
        self.lock = Lock()
        self.block_first_binary = block_first_binary
        self.binary_entered = Event()
        self.release_binary = Event()

    def recv(self):
        return self.request

    def send(self, value):
        if isinstance(value, bytes) and self.block_first_binary and not self.binary_entered.is_set():
            self.binary_entered.set()
            self.release_binary.wait(1)
        with self.lock:
            self.sent.append(value)


def wait_until(predicate, timeout=1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("condition was not reached")


def settings(max_clients=2):
    return PreviewSettings("camera-1", "preview-secret", 16, 12, 5, 75, max_clients)


def test_preview_authenticates_and_sends_metadata_then_jpeg():
    service = CameraPreviewService(settings())
    service.start()
    websocket = FakeWebSocket()
    thread = Thread(target=service.handle, args=(websocket,), daemon=True)
    thread.start()
    wait_until(lambda: service.stats().subscriber_count == 1)
    service.publish(make_frame(7))
    wait_until(lambda: len(websocket.sent) >= 3)
    service.close()
    thread.join(1)

    subscribed = json.loads(websocket.sent[0])
    metadata = json.loads(websocket.sent[1])
    assert subscribed["type"] == "camera.preview.subscribed"
    assert metadata["frame_id"] == 7
    assert metadata["width"] == 16 and metadata["height"] == 12
    assert metadata["byte_length"] == len(websocket.sent[2])
    assert websocket.sent[2].startswith(b"\xff\xd8")


def test_preview_rejects_invalid_token_and_max_clients():
    service = CameraPreviewService(settings(max_clients=1))
    service.start()
    invalid = FakeWebSocket(token="wrong")
    service.handle(invalid)
    assert json.loads(invalid.sent[0])["error_code"] == "unauthorized"

    first = FakeWebSocket()
    first_thread = Thread(target=service.handle, args=(first,), daemon=True)
    first_thread.start()
    wait_until(lambda: service.stats().subscriber_count == 1)
    second = FakeWebSocket()
    service.handle(second)
    service.close()
    first_thread.join(1)
    assert json.loads(second.sent[0])["error_code"] == "max_clients"


def test_preview_does_not_encode_without_subscribers():
    encoded = []
    service = CameraPreviewService(settings(), encoder=lambda frame, cfg: encoded.append(frame))
    service.start()
    service.publish(make_frame(1))
    time.sleep(.03)
    service.close()
    assert encoded == []


def test_slow_client_receives_latest_pending_frame_only():
    service = CameraPreviewService(settings())
    service.start()
    websocket = FakeWebSocket(block_first_binary=True)
    thread = Thread(target=service.handle, args=(websocket,), daemon=True)
    thread.start()
    wait_until(lambda: service.stats().subscriber_count == 1)
    service.publish(make_frame(1, 10))
    assert websocket.binary_entered.wait(1)
    for frame_id in (2, 3, 4):
        service.publish(make_frame(frame_id, frame_id))
    wait_until(lambda: service.stats().dropped_frames >= 1)
    websocket.release_binary.set()
    wait_until(lambda: any(
        isinstance(item, str) and json.loads(item).get("frame_id") == 4
        for item in websocket.sent
    ))
    service.close()
    thread.join(1)

    delivered_ids = [json.loads(item)["frame_id"] for item in websocket.sent
                     if isinstance(item, str) and json.loads(item).get("type") == "camera.preview.frame"]
    assert delivered_ids[0] == 1
    assert delivered_ids[-1] == 4
    assert len(delivered_ids) <= 3
