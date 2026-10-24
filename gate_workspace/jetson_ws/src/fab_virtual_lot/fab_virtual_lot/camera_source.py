"""Camera input adapters with secret-safe HTTP(S) MJPEG authentication."""

from __future__ import annotations

from base64 import b64encode
from dataclasses import dataclass
import os
from pathlib import Path
import socket
import ssl
from typing import Callable, Mapping, Protocol
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import cv2
import numpy as np


class CameraSourceError(RuntimeError):
    """A camera failed without exposing transport credentials."""


class CameraSource(Protocol):
    def read(self) -> np.ndarray: ...

    def close(self) -> None: ...


def _boolean(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = env.get(key, "true" if default else "false").strip().lower()
    if raw not in {"true", "false"}:
        raise ValueError(f"{key} must be true or false")
    return raw == "true"


@dataclass(frozen=True)
class CameraSettings:
    mode: str
    camera_id: str
    source_url: str = ""
    auth_mode: str = "none"
    username: str = ""
    password: str = ""
    tls_verify: bool = True
    tls_ca_file: str = ""
    allow_http: bool = False
    connect_timeout_seconds: float = 5.0
    read_timeout_seconds: float = 5.0
    fixture_path: Path | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "CameraSettings":
        mode = env.get("CAMERA_MODE", "mock").strip().lower()
        if mode not in {"mock", "prod"}:
            raise ValueError("CAMERA_MODE must be mock or prod")
        camera_id = env.get("CAMERA_ID", "aoi-camera-1").strip()
        if not camera_id:
            raise ValueError("CAMERA_ID is required")
        if mode == "mock":
            value = env.get("CAMERA_FIXTURE_PATH", "").strip()
            if not value:
                raise ValueError("CAMERA_FIXTURE_PATH is required in mock mode")
            return cls(mode=mode, camera_id=camera_id, fixture_path=Path(value))

        source_url = env.get("CAMERA_SOURCE_URL", "").strip()
        scheme = urlsplit(source_url).scheme.lower()
        if scheme not in {"http", "https"}:
            raise ValueError("CAMERA_SOURCE_URL must use HTTP or HTTPS")
        allow_http = _boolean(env, "CAMERA_ALLOW_HTTP", False)
        if scheme == "http" and not allow_http:
            raise ValueError("HTTP camera source is disabled")
        auth_mode = env.get("CAMERA_AUTH_MODE", "basic").strip().lower()
        if auth_mode not in {"none", "basic"}:
            raise ValueError("CAMERA_AUTH_MODE must be none or basic")
        username = env.get("CAMERA_USERNAME", "")
        password = env.get("CAMERA_PASSWORD", "")
        if auth_mode == "basic" and (not username or not password):
            raise ValueError("camera basic-auth credentials are required")
        connect_timeout = float(env.get("CAMERA_CONNECT_TIMEOUT_SECONDS", "5"))
        read_timeout = float(env.get("CAMERA_READ_TIMEOUT_SECONDS", "5"))
        if connect_timeout <= 0 or read_timeout <= 0:
            raise ValueError("camera timeouts must be positive")
        return cls(
            mode=mode,
            camera_id=camera_id,
            source_url=source_url,
            auth_mode=auth_mode,
            username=username,
            password=password,
            tls_verify=_boolean(env, "CAMERA_TLS_VERIFY", True),
            tls_ca_file=env.get("CAMERA_TLS_CA_FILE", "").strip(),
            allow_http=allow_http,
            connect_timeout_seconds=connect_timeout,
            read_timeout_seconds=read_timeout,
        )


class FixtureCameraSource:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> np.ndarray:
        image = cv2.imread(str(self.path), cv2.IMREAD_COLOR)
        if image is None:
            raise CameraSourceError("camera fixture cannot be read")
        return image

    def close(self) -> None:
        return None


class MjpegHttpCameraSource:
    def __init__(
        self,
        settings: CameraSettings,
        opener: Callable[..., object] = urlopen,
        chunk_size: int = 64 * 1024,
        max_frame_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        if settings.mode != "prod":
            raise ValueError("MJPEG source requires prod camera settings")
        self.settings = settings
        self.opener = opener
        self.chunk_size = chunk_size
        self.max_frame_bytes = max_frame_bytes
        self._stream = None
        self._buffer = bytearray()

    def read(self) -> np.ndarray:
        try:
            if self._stream is None:
                self._stream = self._open()
            while True:
                start = self._buffer.find(b"\xff\xd8")
                if start >= 0:
                    end = self._buffer.find(b"\xff\xd9", start + 2)
                    if end >= 0:
                        payload = bytes(self._buffer[start:end + 2])
                        del self._buffer[:end + 2]
                        image = cv2.imdecode(
                            np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR
                        )
                        if image is None:
                            raise CameraSourceError("camera returned an invalid JPEG frame")
                        return image
                    if start:
                        del self._buffer[:start]
                chunk = self._stream.read(self.chunk_size)
                if not chunk:
                    raise CameraSourceError("camera stream ended")
                self._buffer.extend(chunk)
                if len(self._buffer) > self.max_frame_bytes:
                    raise CameraSourceError("camera frame exceeds configured safety limit")
        except (socket.timeout, TimeoutError):
            self._discard_stream()
            raise CameraSourceError("camera stream timed out") from None
        except CameraSourceError:
            self._discard_stream()
            raise
        except Exception:
            self._discard_stream()
            raise CameraSourceError("camera stream is unavailable") from None

    def close(self) -> None:
        self._discard_stream()
        self._buffer.clear()

    def _open(self):
        headers = {"User-Agent": "fab-virtual-lot-camera/1"}
        if self.settings.auth_mode == "basic":
            credentials = f"{self.settings.username}:{self.settings.password}".encode("utf-8")
            headers["Authorization"] = "Basic " + b64encode(credentials).decode("ascii")
        request = Request(self.settings.source_url, headers=headers)
        kwargs = {"timeout": self.settings.connect_timeout_seconds}
        if self.settings.source_url.startswith("https://"):
            if self.settings.tls_verify:
                context = ssl.create_default_context(
                    cafile=self.settings.tls_ca_file or None
                )
            else:
                context = ssl._create_unverified_context()
            kwargs["context"] = context
        return self.opener(request, **kwargs)

    def _discard_stream(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass


def make_camera_source(
    settings: CameraSettings,
    opener: Callable[..., object] = urlopen,
) -> CameraSource:
    if settings.mode == "mock":
        assert settings.fixture_path is not None
        return FixtureCameraSource(settings.fixture_path)
    return MjpegHttpCameraSource(settings, opener=opener)
