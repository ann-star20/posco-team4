"""Thread-safe, memory-bounded storage for recent camera frames."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from threading import RLock
import time
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class CameraFrame:
    frame_id: int
    camera_id: str
    captured_at: datetime
    monotonic_ns: int
    image: np.ndarray

    def __post_init__(self) -> None:
        if self.frame_id < 0:
            raise ValueError("frame_id must be non-negative")
        if not self.camera_id:
            raise ValueError("camera_id is required")
        if self.image.ndim != 3 or self.image.shape[2] != 3:
            raise ValueError("camera image must be a BGR image")
        owned = np.ascontiguousarray(self.image).copy()
        owned.setflags(write=False)
        object.__setattr__(self, "image", owned)

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    @property
    def byte_size(self) -> int:
        return int(self.image.nbytes)


@dataclass(frozen=True)
class FrameBounds:
    oldest_frame_id: int | None
    latest_frame_id: int | None


@dataclass(frozen=True)
class FrameBufferStats:
    frame_count: int
    total_bytes: int


class FrameRingBuffer:
    def __init__(
        self,
        max_age_seconds: float,
        max_bytes: int,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._max_age_ns = int(max_age_seconds * 1_000_000_000)
        self._max_bytes = max_bytes
        self._clock_ns = clock_ns
        self._frames: deque[CameraFrame] = deque()
        self._total_bytes = 0
        self._lock = RLock()

    def put(self, frame: CameraFrame) -> None:
        stored = CameraFrame(
            frame_id=frame.frame_id,
            camera_id=frame.camera_id,
            captured_at=frame.captured_at,
            monotonic_ns=frame.monotonic_ns,
            image=frame.image,
        )
        if stored.byte_size > self._max_bytes:
            raise ValueError("camera frame exceeds ring buffer byte limit")
        with self._lock:
            if self._frames and stored.frame_id <= self._frames[-1].frame_id:
                raise ValueError("frame_id must increase")
            self._frames.append(stored)
            self._total_bytes += stored.byte_size
            self._evict(self._clock_ns())

    def get_copy(self, frame_id: int) -> CameraFrame | None:
        with self._lock:
            self._evict(self._clock_ns())
            for frame in self._frames:
                if frame.frame_id == frame_id:
                    return CameraFrame(
                        frame_id=frame.frame_id,
                        camera_id=frame.camera_id,
                        captured_at=frame.captured_at,
                        monotonic_ns=frame.monotonic_ns,
                        image=frame.image,
                    )
        return None

    def bounds(self) -> FrameBounds:
        with self._lock:
            self._evict(self._clock_ns())
            if not self._frames:
                return FrameBounds(None, None)
            return FrameBounds(self._frames[0].frame_id, self._frames[-1].frame_id)

    def stats(self) -> FrameBufferStats:
        with self._lock:
            self._evict(self._clock_ns())
            return FrameBufferStats(len(self._frames), self._total_bytes)

    def _evict(self, now_ns: int) -> None:
        while self._frames and now_ns - self._frames[0].monotonic_ns > self._max_age_ns:
            self._discard_oldest()
        while self._frames and self._total_bytes > self._max_bytes:
            self._discard_oldest()

    def _discard_oldest(self) -> None:
        oldest = self._frames.popleft()
        self._total_bytes -= oldest.byte_size
