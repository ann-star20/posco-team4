from datetime import datetime, timezone

import numpy as np

from fab_virtual_lot.camera_buffer import CameraFrame, FrameRingBuffer


def frame(frame_id: int, timestamp_ns: int, value: int = 1) -> CameraFrame:
    return CameraFrame(
        frame_id=frame_id,
        camera_id="aoi-camera-1",
        captured_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        monotonic_ns=timestamp_ns,
        image=np.full((2, 2, 3), value, dtype=np.uint8),
    )


def test_ring_buffer_evicts_by_age():
    now = [0]
    buffer = FrameRingBuffer(max_age_seconds=2, max_bytes=128, clock_ns=lambda: now[0])
    buffer.put(frame(1, 0))
    now[0] = 2_000_000_000
    buffer.put(frame(2, now[0]))
    assert buffer.get_copy(1) is not None

    now[0] += 1
    buffer.put(frame(3, now[0]))

    assert buffer.get_copy(1) is None
    assert buffer.bounds().oldest_frame_id == 2
    assert buffer.bounds().latest_frame_id == 3


def test_ring_buffer_evicts_by_byte_limit():
    buffer = FrameRingBuffer(max_age_seconds=2, max_bytes=24, clock_ns=lambda: 0)
    buffer.put(frame(10, 0, 10))
    buffer.put(frame(11, 0, 11))
    buffer.put(frame(12, 0, 12))

    assert buffer.get_copy(10) is None
    assert buffer.get_copy(11) is not None
    assert buffer.get_copy(12) is not None
    assert buffer.stats().total_bytes == 24
    assert buffer.stats().frame_count == 2


def test_get_copy_is_not_mutated_by_capture_reuse():
    buffer = FrameRingBuffer(max_age_seconds=2, max_bytes=128, clock_ns=lambda: 0)
    source_image = np.full((2, 2, 3), 20, dtype=np.uint8)
    source = CameraFrame(
        frame_id=20,
        camera_id="aoi-camera-1",
        captured_at=datetime(2026, 10, 20, tzinfo=timezone.utc),
        monotonic_ns=0,
        image=source_image,
    )
    buffer.put(source)
    source_image[:] = 99
    selected = buffer.get_copy(20)
    assert selected is not None
    assert selected.image.tolist() == np.full((2, 2, 3), 20, dtype=np.uint8).tolist()

    selected.image.setflags(write=True)
    selected.image[:] = 77
    selected_again = buffer.get_copy(20)
    assert selected_again is not None
    assert selected_again.image.tolist() == np.full((2, 2, 3), 20, dtype=np.uint8).tolist()


def test_missing_frame_reports_available_bounds():
    buffer = FrameRingBuffer(max_age_seconds=2, max_bytes=128, clock_ns=lambda: 0)
    assert buffer.bounds().oldest_frame_id is None
    assert buffer.bounds().latest_frame_id is None
    buffer.put(frame(31, 0))
    buffer.put(frame(32, 0))

    assert buffer.get_copy(30) is None
    assert buffer.bounds().oldest_frame_id == 31
    assert buffer.bounds().latest_frame_id == 32
