"""Long-lived camera capture lifecycle and frame fan-out."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Event, Lock, Thread
import time
from typing import Callable

from .camera_buffer import CameraFrame, FrameRingBuffer
from .camera_source import CameraSource


@dataclass(frozen=True)
class CameraCaptureStatus:
    running: bool
    connected: bool
    latest_frame_id: int | None
    reconnect_count: int
    captured_frames: int


class CameraCaptureService:
    def __init__(
        self,
        source_factory: Callable[[], CameraSource],
        buffer: FrameRingBuffer,
        camera_id: str,
        capture_fps: float = 10,
        reconnect_interval_seconds: float = 3,
        clock_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if capture_fps <= 0 or reconnect_interval_seconds < 0:
            raise ValueError("capture timing values are invalid")
        self.source_factory = source_factory
        self.buffer = buffer
        self.camera_id = camera_id
        self.capture_fps = capture_fps
        self.reconnect_interval_seconds = reconnect_interval_seconds
        self.clock_ns = clock_ns
        self._stop = Event()
        self._thread: Thread | None = None
        self._source: CameraSource | None = None
        self._listeners: list[Callable[[CameraFrame], None]] = []
        self._lock = Lock()
        self._connected = False
        self._latest_frame_id: int | None = None
        self._reconnect_count = 0
        self._captured_frames = 0

    def subscribe(self, listener: Callable[[CameraFrame], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = Thread(target=self._run, name="camera-capture", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=3)
        self._close_source()
        with self._lock:
            self._thread = None
            self._connected = False

    def status(self) -> CameraCaptureStatus:
        with self._lock:
            return CameraCaptureStatus(
                running=self._thread is not None and self._thread.is_alive(),
                connected=self._connected,
                latest_frame_id=self._latest_frame_id,
                reconnect_count=self._reconnect_count,
                captured_frames=self._captured_frames,
            )

    def _run(self) -> None:
        interval = 1.0 / self.capture_fps
        frame_id = 0
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                if self._source is None:
                    self._source = self.source_factory()
                image = self._source.read()
                frame_id += 1
                frame = CameraFrame(
                    frame_id=frame_id,
                    camera_id=self.camera_id,
                    captured_at=datetime.now(timezone.utc),
                    monotonic_ns=self.clock_ns(),
                    image=image,
                )
                self.buffer.put(frame)
                with self._lock:
                    self._connected = True
                    self._latest_frame_id = frame_id
                    self._captured_frames += 1
                    listeners = tuple(self._listeners)
                for listener in listeners:
                    try:
                        listener(frame)
                    except Exception:
                        continue
                remaining = interval - (time.monotonic() - started)
                if remaining > 0:
                    self._stop.wait(remaining)
            except Exception:
                self._close_source()
                with self._lock:
                    self._connected = False
                    self._reconnect_count += 1
                self._stop.wait(self.reconnect_interval_seconds)
        self._close_source()

    def _close_source(self) -> None:
        source, self._source = self._source, None
        if source is not None:
            try:
                source.close()
            except Exception:
                pass

