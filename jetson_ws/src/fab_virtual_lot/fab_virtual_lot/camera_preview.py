"""Latest-frame-only JPEG Preview WebSocket service for Unity."""

from __future__ import annotations

from dataclasses import dataclass
import json
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
from time import monotonic, sleep
from typing import Callable

import cv2

from .camera_buffer import CameraFrame


@dataclass(frozen=True)
class PreviewSettings:
    camera_id: str
    token: str
    width: int = 1280
    height: int = 720
    fps: int = 5
    jpeg_quality: int = 75
    max_clients: int = 2


@dataclass(frozen=True)
class PreviewStats:
    subscriber_count: int
    dropped_frames: int
    encoded_frames: int


@dataclass
class _Client:
    outgoing: Queue


class CameraPreviewService:
    def __init__(
        self,
        settings: PreviewSettings,
        encoder: Callable[[CameraFrame, PreviewSettings], tuple[dict, bytes] | None] | None = None,
    ) -> None:
        self.settings = settings
        self.encoder = encoder or self._encode
        self._incoming: Queue = Queue(maxsize=1)
        self._clients: dict[int, _Client] = {}
        self._lock = Lock()
        self._closed = Event()
        self._worker: Thread | None = None
        self._next_client_id = 0
        self._dropped_frames = 0
        self._encoded_frames = 0

    def start(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._closed.clear()
            self._worker = Thread(target=self._encode_loop, name="camera-preview", daemon=True)
            self._worker.start()

    def publish(self, frame: CameraFrame) -> None:
        with self._lock:
            if not self._clients or self._closed.is_set():
                return
        try:
            self._incoming.put_nowait(frame)
        except Full:
            try:
                self._incoming.get_nowait()
            except Empty:
                pass
            self._incoming.put_nowait(frame)
            with self._lock:
                self._dropped_frames += 1

    def handle(self, websocket) -> None:
        client_id = None
        try:
            request = self._validate_subscription(websocket.recv())
            with self._lock:
                if len(self._clients) >= self.settings.max_clients:
                    self._send_error(websocket, "max_clients")
                    return
                self._next_client_id += 1
                client_id = self._next_client_id
                client = _Client(Queue(maxsize=1))
                self._clients[client_id] = client
            websocket.send(json.dumps({
                "type": "camera.preview.subscribed",
                "schema_version": 1,
                "camera_id": self.settings.camera_id,
                "width": min(int(request.get("preferred_width", self.settings.width)),
                             self.settings.width),
                "height": min(int(request.get("preferred_height", self.settings.height)),
                              self.settings.height),
                "fps": min(int(request.get("preferred_fps", self.settings.fps)),
                           self.settings.fps),
                "encoding": "jpeg",
            }, separators=(",", ":")))
            while not self._closed.is_set():
                try:
                    item = client.outgoing.get(timeout=.1)
                except Empty:
                    continue
                if item is None:
                    break
                metadata, image = item
                websocket.send(json.dumps(metadata, separators=(",", ":")))
                websocket.send(image)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            self._send_error(websocket, "unauthorized")
        except Exception:
            pass
        finally:
            if client_id is not None:
                with self._lock:
                    self._clients.pop(client_id, None)

    def stats(self) -> PreviewStats:
        with self._lock:
            return PreviewStats(len(self._clients), self._dropped_frames,
                                self._encoded_frames)

    def close(self) -> None:
        self._closed.set()
        with self._lock:
            clients = tuple(self._clients.values())
        for client in clients:
            self._replace_latest(client.outgoing, None)
        try:
            self._incoming.put_nowait(None)
        except Full:
            try:
                self._incoming.get_nowait()
            except Empty:
                pass
            self._incoming.put_nowait(None)
        worker = self._worker
        if worker is not None:
            worker.join(timeout=3)
        with self._lock:
            self._worker = None

    def _validate_subscription(self, raw: str) -> dict:
        if not isinstance(raw, str):
            raise ValueError("subscription must be JSON")
        request = json.loads(raw)
        if (request.get("type") != "camera.preview.subscribe"
                or request.get("schema_version") != 1
                or request.get("camera_id") != self.settings.camera_id
                or request.get("api_token") != self.settings.token):
            raise ValueError("invalid preview subscription")
        return request

    def _encode_loop(self) -> None:
        next_encode_at = 0.0
        while not self._closed.is_set():
            try:
                frame = self._incoming.get(timeout=.1)
            except Empty:
                continue
            if frame is None:
                break
            delay = next_encode_at - monotonic()
            if delay > 0:
                sleep(delay)
                while True:
                    try:
                        newer = self._incoming.get_nowait()
                    except Empty:
                        break
                    if newer is None:
                        return
                    frame = newer
            with self._lock:
                clients = tuple(self._clients.values())
            if not clients:
                continue
            encoded = self.encoder(frame, self.settings)
            if encoded is None:
                continue
            with self._lock:
                self._encoded_frames += 1
            next_encode_at = monotonic() + (1.0 / self.settings.fps)
            for client in clients:
                if client.outgoing.full():
                    with self._lock:
                        self._dropped_frames += 1
                self._replace_latest(client.outgoing, encoded)

    @staticmethod
    def _replace_latest(queue: Queue, item) -> None:
        try:
            queue.put_nowait(item)
            return
        except Full:
            pass
        try:
            queue.get_nowait()
        except Empty:
            pass
        queue.put_nowait(item)

    @staticmethod
    def _encode(frame: CameraFrame, settings: PreviewSettings) -> tuple[dict, bytes]:
        image = cv2.resize(frame.image, (settings.width, settings.height),
                           interpolation=cv2.INTER_AREA)
        okay, encoded = cv2.imencode(
            ".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality]
        )
        if not okay:
            raise ValueError("preview JPEG encoding failed")
        payload = encoded.tobytes()
        metadata = {
            "type": "camera.preview.frame",
            "schema_version": 1,
            "camera_id": frame.camera_id,
            "frame_id": frame.frame_id,
            "captured_at": frame.captured_at.isoformat(),
            "width": settings.width,
            "height": settings.height,
            "mime_type": "image/jpeg",
            "byte_length": len(payload),
            "binary_frame_follows": True,
        }
        return metadata, payload

    @staticmethod
    def _send_error(websocket, code: str) -> None:
        websocket.send(json.dumps({
            "type": "camera.preview.rejected",
            "schema_version": 1,
            "error_code": code,
        }, separators=(",", ":")))
