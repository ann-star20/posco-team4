from dataclasses import dataclass
import time

import pytest

from fab_virtual_lot.camera_observability import (
    CameraStatusReporter,
    status_log_interval,
)


@dataclass(frozen=True)
class CameraStatus:
    running: bool = True
    connected: bool = True
    latest_frame_id: int | None = 7713
    reconnect_count: int = 2
    captured_frames: int = 7713


@dataclass(frozen=True)
class PreviewStats:
    subscriber_count: int = 3
    dropped_frames: int = 4
    encoded_frames: int = 2451


class Camera:
    def status(self):
        return CameraStatus()


class Preview:
    def stats(self):
        return PreviewStats()


def test_status_reporter_emits_capture_and_preview_counters_without_secrets():
    messages = []
    reporter = CameraStatusReporter(Camera(), Preview(), interval_seconds=0.01,
                                    write=messages.append)
    reporter.start()
    deadline = time.time() + 1
    while not messages and time.time() < deadline:
        time.sleep(0.005)
    reporter.close()

    assert messages == [
        "Camera status: running=true connected=true captured=7713 "
        "latest_frame=7713 reconnects=2 | Preview status: subscribers=3 "
        "encoded=2451 dropped=4"
    ]
    assert "password" not in messages[0].lower()
    assert "source_url" not in messages[0].lower()


def test_zero_interval_disables_periodic_status_logging():
    messages = []
    reporter = CameraStatusReporter(Camera(), Preview(), interval_seconds=0,
                                    write=messages.append)
    reporter.start()
    time.sleep(0.02)
    reporter.close()

    assert messages == []


def test_status_log_interval_defaults_to_five_seconds_and_rejects_negative():
    assert status_log_interval({}) == 5.0
    assert status_log_interval({"CAMERA_STATUS_LOG_INTERVAL_SECONDS": "2.5"}) == 2.5
    with pytest.raises(ValueError, match="zero or positive"):
        status_log_interval({"CAMERA_STATUS_LOG_INTERVAL_SECONDS": "-1"})
