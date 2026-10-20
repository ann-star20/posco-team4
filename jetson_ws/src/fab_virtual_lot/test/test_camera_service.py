from datetime import datetime, timezone
from threading import Event
import time

import numpy as np

from fab_virtual_lot.camera_buffer import FrameRingBuffer
from fab_virtual_lot.camera_service import CameraCaptureService
from fab_virtual_lot.camera_source import CameraSourceError


class SequenceSource:
    def __init__(self, values):
        self.values = iter(values)
        self.closed = False

    def read(self):
        value = next(self.values)
        if isinstance(value, BaseException):
            raise value
        return np.full((2, 3, 3), value, dtype=np.uint8)

    def close(self):
        self.closed = True


def wait_until(predicate, timeout=1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("condition was not reached")


def test_capture_assigns_monotonic_frame_ids_and_stops_idempotently():
    source = SequenceSource([10, 20, 30, CameraSourceError("done")])
    buffer = FrameRingBuffer(10, 1024)
    service = CameraCaptureService(lambda: source, buffer, "camera-1", capture_fps=1000,
                                   reconnect_interval_seconds=.01)
    service.start()
    wait_until(lambda: buffer.bounds().latest_frame_id == 3)
    service.stop()
    service.stop()

    assert buffer.bounds().oldest_frame_id == 1
    assert buffer.get_copy(3).image[0, 0].tolist() == [30, 30, 30]
    assert source.closed
    assert service.status().running is False


def test_capture_reconnects_after_source_failure():
    first = SequenceSource([CameraSourceError("offline")])
    second = SequenceSource([42, CameraSourceError("done")])
    sources = iter([first, second])
    buffer = FrameRingBuffer(10, 1024)
    service = CameraCaptureService(lambda: next(sources), buffer, "camera-1",
                                   capture_fps=1000, reconnect_interval_seconds=.01)
    service.start()
    wait_until(lambda: buffer.stats().frame_count == 1)
    service.stop()

    assert first.closed
    assert second.closed
    assert buffer.get_copy(1).image[0, 0].tolist() == [42, 42, 42]
    assert service.status().reconnect_count >= 1


def test_capture_notifies_listener_without_exposing_mutable_buffer_frame():
    delivered = []
    got_frame = Event()
    source = SequenceSource([7, CameraSourceError("done")])
    buffer = FrameRingBuffer(10, 1024)
    service = CameraCaptureService(lambda: source, buffer, "camera-1",
                                   capture_fps=1000, reconnect_interval_seconds=.01)
    service.subscribe(lambda frame: (delivered.append(frame), got_frame.set()))
    service.start()
    assert got_frame.wait(1)
    service.stop()

    assert delivered[0].captured_at.tzinfo == timezone.utc
    assert delivered[0].image.flags.writeable is False

