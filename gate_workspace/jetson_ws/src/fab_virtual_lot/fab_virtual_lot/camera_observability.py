"""Periodic, credential-free camera and Preview status logging."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from threading import Event, Thread


def status_log_interval(env: Mapping[str, str]) -> float:
    value = float(env.get("CAMERA_STATUS_LOG_INTERVAL_SECONDS", "5"))
    if value < 0:
        raise ValueError("CAMERA_STATUS_LOG_INTERVAL_SECONDS must be zero or positive")
    return value


class CameraStatusReporter:
    def __init__(self, camera, preview, interval_seconds: float = 5,
                 write: Callable[[str], None] | None = None) -> None:
        if interval_seconds < 0:
            raise ValueError("status interval must be zero or positive")
        self.camera = camera
        self.preview = preview
        self.interval_seconds = interval_seconds
        self.write = write or (lambda message: print(message, flush=True))
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        if self.interval_seconds == 0:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name="camera-status", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=min(self.interval_seconds + 0.1, 1.0))
        self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            camera = self.camera.status()
            preview = self.preview.stats()
            latest = "none" if camera.latest_frame_id is None else str(camera.latest_frame_id)
            self.write(
                "Camera status: "
                f"running={str(camera.running).lower()} "
                f"connected={str(camera.connected).lower()} "
                f"captured={camera.captured_frames} latest_frame={latest} "
                f"reconnects={camera.reconnect_count} | Preview status: "
                f"subscribers={preview.subscriber_count} "
                f"encoded={preview.encoded_frames} dropped={preview.dropped_frames}"
            )
