from pathlib import Path
import time
from uuid import uuid4

import cv2
import numpy as np
import pytest

from fab_virtual_lot.aoi_pipeline import (
    AoiConfig,
    MockModel,
    RelativeMockModel,
    UltralyticsModel,
    annotation_style,
    inspect_image,
    model_paths,
)


class FakeBox:
    def __init__(self, cls, conf, xyxy):
        self.cls = cls
        self.conf = conf
        self.xyxy = xyxy


class FakeModel:
    def __init__(self, boxes):
        self.boxes = boxes
        self.calls = []

    def predict(self, image, conf, iou):
        self.calls.append((image.copy(), conf, iou))
        return self.boxes


def test_annotation_style_scales_for_camera_resolution():
    assert annotation_style(640, 480) == (.5, 1, 2)
    font_scale, text_thickness, box_thickness = annotation_style(3024, 4032)
    assert font_scale >= 1.5
    assert text_thickness >= 3
    assert box_thickness >= 4


def test_relative_mock_box_scales_to_source_image_instead_of_top_left_pixels():
    image = np.zeros((4032, 3024, 3), dtype=np.uint8)
    model = RelativeMockModel(0, .97, (.38, .42, .64, .66))

    detections = model.predict(image, conf=.35, iou=.45)

    assert detections == [{
        "cls": 0,
        "conf": .97,
        "xyxy": pytest.approx((1149.12, 1693.44, 1935.36, 2661.12)),
    }]


def test_aoi_uses_same_original_and_saves_jpegs(tmp_path):
    image = np.full((24, 32, 3), 170, dtype=np.uint8)
    part = FakeModel([FakeBox(0, .97, (3, 4, 20, 18))])
    defect = FakeModel([FakeBox(1, .92, (5, 6, 15, 19))])
    job_id = uuid4()
    config = AoiConfig(tmp_path, .35, .20, .45, .35, "mock", "jetson-wsl")
    result = inspect_image(image, job_id, 1, config, part, defect)
    assert part.calls[0][1:] == (.35, .45)
    assert defect.calls[0][1:] == (.20, .35)
    assert np.array_equal(part.calls[0][0], defect.calls[0][0])
    assert result["verdict"] == "fail"
    assert [d["class_name"] for d in result["detections"]] == ["body", "bend"]
    for role in ("original", "annotated"):
        image_meta = result["images"][role]
        path = Path(image_meta["local_directory"]) / image_meta["file_name"]
        assert path.is_file() and cv2.imread(str(path)) is not None
        assert len(image_meta["sha256"]) == 64
    annotated_directory = Path(result["images"]["annotated"]["local_directory"])
    assert annotated_directory.parts[-2:] == (str(job_id), "1")
    assert inspect_image(image, job_id, 1, config, part, defect) == result
    assert len(part.calls) == len(defect.calls) == 1


def test_empty_part_is_review_not_pass(tmp_path):
    image = np.zeros((16, 16, 3), dtype=np.uint8)
    config = AoiConfig(tmp_path, .35, .20, .45, .35, "mock", "jetson-wsl")
    result = inspect_image(image, uuid4(), 1, config, FakeModel([]), FakeModel([]))
    assert result["verdict"] == "review"


def test_model_paths_use_env_and_fail_closed(tmp_path):
    part = tmp_path / "part.pt"
    defect = tmp_path / "defect.pt"
    part.write_bytes(b"part")
    defect.write_bytes(b"defect")
    assert model_paths({"AOI_PART_MODEL_FILE": str(part), "AOI_DEFECT_MODEL_FILE": str(defect)}) == (part, defect)
    part.unlink()
    with pytest.raises(FileNotFoundError):
        model_paths({"AOI_PART_MODEL_FILE": str(part), "AOI_DEFECT_MODEL_FILE": str(defect)})


def test_segmentation_mask_is_tinted_in_result_jpg(tmp_path):
    image = np.full((80, 80, 3), 100, dtype=np.uint8)
    mask = np.zeros((80, 80), dtype=bool)
    mask[30:50, 30:50] = True
    defect = FakeModel([{"cls": 1, "conf": .9, "xyxy": (10, 10, 70, 70), "_mask": mask}])
    config = AoiConfig(tmp_path, .35, .20, .45, .35, "mock", "jetson-wsl")
    result = inspect_image(image, uuid4(), 1, config, FakeModel([]), defect)
    path = Path(result["images"]["annotated"]["local_directory"]) / "annotated.jpg"
    pixel = cv2.imread(str(path))[40, 40]
    assert int(pixel[2]) > int(pixel[0]) + 30


def test_inspection_records_per_model_and_total_processing_time(tmp_path):
    image = np.zeros((16, 16, 3), dtype=np.uint8)
    config = AoiConfig(tmp_path, .35, .20, .45, .35, "mock", "jetson-wsl")

    class SlowMockModel(MockModel):
        def predict(self, image, conf, iou):
            time.sleep(.01)
            return super().predict(image, conf, iou)

    part = SlowMockModel(0, .97, (1, 1, 10, 10))
    defect = SlowMockModel(1, 0, (2, 2, 8, 8))

    result = inspect_image(image, uuid4(), 1, config, part, defect)

    assert result["timings"]["part_inference_ms"] >= 8
    assert result["timings"]["defect_inference_ms"] >= 8
    assert result["timings"]["total_processing_ms"] >= (
        result["timings"]["part_inference_ms"]
        + result["timings"]["defect_inference_ms"]
    )
    assert result["processing_ms"] == result["timings"]["total_processing_ms"]
    assert result["models"] == {
        "part": {"backend": "mock", "precision": "synthetic", "device": "cpu"},
        "defect": {"backend": "mock", "precision": "synthetic", "device": "cpu"},
    }


def test_ultralytics_model_identifies_exact_weight_file(tmp_path, monkeypatch):
    weight = tmp_path / "best.pt"
    weight.write_bytes(b"exact model weights")

    class FakeYolo:
        def __init__(self, path):
            self.path = path

    monkeypatch.setattr("ultralytics.YOLO", FakeYolo)

    model = UltralyticsModel(weight, "cuda:0", precision="fp16")

    assert model.metadata == {
        "file_name": "best.pt",
        "sha256": "354c0d1e5c423dbf95ae041d2d43b4385c7b2a851165833aca049239ad59cd42",
        "backend": "ultralytics-pytorch",
        "precision": "fp16",
        "device": "cuda:0",
    }
