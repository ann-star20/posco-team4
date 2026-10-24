import cv2
import numpy as np
import pytest

from fab_virtual_lot.aoi_worker import load_fixture


def test_fixture_selected_within_configured_image_directory(tmp_path, monkeypatch):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    cv2.imwrite(str(image_dir / "first.png"), np.full((8, 8, 3), 41, np.uint8))
    cv2.imwrite(str(image_dir / "second.png"), np.full((8, 8, 3), 92, np.uint8))
    monkeypatch.setenv("AOI_IMAGE_DIR", str(image_dir))
    monkeypatch.setenv("CAMERA_FIXTURE_PATH", str(image_dir / "first.png"))
    assert int(load_fixture({"fixture_name": "second.png"})[0, 0, 0]) == 92
    assert int(load_fixture({})[0, 0, 0]) == 41


@pytest.mark.parametrize("name", ["../secret.png", "nested/file.png", "/tmp/file.png", "..\\secret.png"])
def test_fixture_rejects_paths_outside_image_directory(tmp_path, monkeypatch, name):
    monkeypatch.setenv("AOI_IMAGE_DIR", str(tmp_path))
    with pytest.raises(ValueError):
        load_fixture({"fixture_name": name})
