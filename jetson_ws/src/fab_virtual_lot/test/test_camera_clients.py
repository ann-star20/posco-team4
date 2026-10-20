import json
import os
from pathlib import Path
import subprocess
import sys

from tools.mock_unity.aoi_frame_client import inspect_frame
from tools.mock_unity.camera_aoi_flow_client import inspect_latest_preview
from tools.mock_unity.camera_preview_client import receive_preview


class FakeConnection:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.sent = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def send(self, value):
        self.sent.append(json.loads(value))

    def recv(self, timeout=None):
        return next(self.replies)


def test_preview_client_returns_displayable_frame_id_and_binary():
    jpeg = b"\xff\xd8preview\xff\xd9"
    metadata = {
        "type": "camera.preview.frame", "schema_version": 1,
        "camera_id": "camera-1", "frame_id": 41,
        "width": 1280, "height": 720, "byte_length": len(jpeg),
    }
    fake = FakeConnection([
        json.dumps({"type": "camera.preview.subscribed"}), json.dumps(metadata), jpeg
    ])

    actual, image = receive_preview("ws://jetson:8500/camera/preview", "token",
                                    "camera-1", connector=lambda *a, **k: fake)

    assert actual["frame_id"] == 41
    assert image == jpeg
    assert fake.sent[0]["type"] == "camera.preview.subscribe"


def test_aoi_client_uses_preview_frame_and_waits_for_completed_binary():
    jpeg = b"\xff\xd8annotated\xff\xd9"
    fake = FakeConnection([
        json.dumps({"type": "aoi.inspection.accepted", "job_id": "job", "frame_id": 41}),
        json.dumps({
            "type": "aoi.inspection.completed", "job_id": "job", "verdict": "pass",
            "image": {"byte_length": len(jpeg)},
        }),
        jpeg,
    ])

    accepted, completed, image = inspect_frame(
        "ws://jetson:8400/aoi", "token", "camera-1", 41,
        connector=lambda *a, **k: fake,
    )

    assert accepted["type"] == "aoi.inspection.accepted"
    assert completed["verdict"] == "pass"
    assert image == jpeg
    assert fake.sent[0]["frame_id"] == 41


def test_combined_client_forwards_received_preview_frame_without_manual_copy():
    inspected = []

    def receive(*_args, **_kwargs):
        return ({"camera_id": "camera-1", "frame_id": 64}, b"preview")

    def inspect(_url, _token, camera_id, frame_id, **_kwargs):
        inspected.append((camera_id, frame_id))
        return ({"frame_id": frame_id}, {"job_id": "job", "verdict": "pass"}, b"result")

    result = inspect_latest_preview(
        "ws://jetson:8500/camera/preview", "preview-token",
        "ws://jetson:8400/aoi", "aoi-token", "camera-1",
        preview_receiver=receive, frame_inspector=inspect,
    )

    assert inspected == [("camera-1", 64)]
    assert result[0]["frame_id"] == 64


def test_combined_client_can_run_as_documented_file_path():
    root = Path(__file__).resolve().parents[4]
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)

    result = subprocess.run(
        [sys.executable, str(root / "tools/mock_unity/camera_aoi_flow_client.py"),
         "--help"],
        cwd=root, env=env, capture_output=True, text=True, timeout=10,
    )

    assert result.returncode == 0, result.stderr
