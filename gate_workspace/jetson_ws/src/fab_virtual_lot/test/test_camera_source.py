import socket

import cv2
import numpy as np
import pytest

from fab_virtual_lot.camera_source import (
    CameraSettings,
    CameraSourceError,
    MjpegHttpCameraSource,
    make_camera_source,
)


class FakeStream:
    def __init__(self, chunks):
        self.chunks = iter(chunks)
        self.closed = False

    def read(self, _size):
        value = next(self.chunks)
        if isinstance(value, BaseException):
            raise value
        return value

    def close(self):
        self.closed = True


def prod_env(**overrides):
    env = {
        "CAMERA_MODE": "prod",
        "CAMERA_ID": "aoi-camera-1",
        "CAMERA_SOURCE_URL": "https://192.168.10.111:8080",
        "CAMERA_AUTH_MODE": "basic",
        "CAMERA_USERNAME": "camera-user",
        "CAMERA_PASSWORD": "camera-password",
        "CAMERA_TLS_VERIFY": "true",
        "CAMERA_ALLOW_HTTP": "false",
        "CAMERA_CONNECT_TIMEOUT_SECONDS": "5",
        "CAMERA_READ_TIMEOUT_SECONDS": "5",
    }
    env.update(overrides)
    return env


def test_mock_source_loads_fixture(tmp_path):
    path = tmp_path / "fixture.jpg"
    expected = np.full((12, 16, 3), 123, dtype=np.uint8)
    assert cv2.imwrite(str(path), expected)
    settings = CameraSettings.from_env({
        "CAMERA_MODE": "mock",
        "CAMERA_ID": "aoi-camera-1",
        "CAMERA_FIXTURE_PATH": str(path),
    })

    source = make_camera_source(settings)
    actual = source.read()
    source.close()
    source.close()

    assert actual.shape == expected.shape
    assert abs(float(actual.mean()) - 123) < 2


def test_https_is_accepted_and_http_requires_explicit_opt_in():
    assert CameraSettings.from_env(prod_env()).source_url.startswith("https://")
    with pytest.raises(ValueError, match="HTTP camera source is disabled"):
        CameraSettings.from_env(prod_env(CAMERA_SOURCE_URL="http://192.168.10.111:8080"))

    settings = CameraSettings.from_env(prod_env(
        CAMERA_SOURCE_URL="http://192.168.10.111:8080",
        CAMERA_ALLOW_HTTP="true",
    ))
    assert settings.source_url.startswith("http://")


@pytest.mark.parametrize("url", ["rtsp://camera/live", "file:///tmp/video", "camera"])
def test_unsupported_source_scheme_is_rejected(url):
    with pytest.raises(ValueError, match="HTTP or HTTPS"):
        CameraSettings.from_env(prod_env(CAMERA_SOURCE_URL=url))


def test_basic_auth_requires_non_empty_credentials():
    with pytest.raises(ValueError, match="credentials"):
        CameraSettings.from_env(prod_env(CAMERA_PASSWORD=""))


def test_mjpeg_source_decodes_jpeg_split_across_chunks():
    expected = np.full((10, 14, 3), (10, 80, 180), dtype=np.uint8)
    okay, encoded = cv2.imencode(".jpg", expected)
    assert okay
    payload = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + encoded.tobytes() + b"\r\n"
    stream = FakeStream([payload[:31], payload[31:63], payload[63:]])
    opened = []

    def opener(request, **kwargs):
        opened.append((request, kwargs))
        return stream

    source = MjpegHttpCameraSource(CameraSettings.from_env(prod_env()), opener=opener)
    actual = source.read()
    source.close()

    assert actual.shape == expected.shape
    assert np.mean(np.abs(actual.astype(int) - expected.astype(int))) < 3
    assert opened[0][0].full_url == "https://192.168.10.111:8080"
    assert opened[0][1]["timeout"] == 5
    assert stream.closed


def test_stream_timeout_is_reported_without_transport_exception():
    stream = FakeStream([socket.timeout("network detail")])
    source = MjpegHttpCameraSource(
        CameraSettings.from_env(prod_env()), opener=lambda *_args, **_kwargs: stream
    )
    with pytest.raises(CameraSourceError, match="timed out"):
        source.read()
    source.close()
    source.close()


def test_password_is_redacted_from_exception_and_logs(caplog):
    secret = "SENTINEL-SECRET-PASSWORD"

    def fail_open(*_args, **_kwargs):
        raise OSError(f"connection rejected for {secret}")

    source = MjpegHttpCameraSource(
        CameraSettings.from_env(prod_env(CAMERA_PASSWORD=secret)), opener=fail_open
    )
    with pytest.raises(CameraSourceError) as caught:
        source.read()

    assert secret not in str(caught.value)
    assert secret not in repr(caught.value)
    assert secret not in caplog.text
