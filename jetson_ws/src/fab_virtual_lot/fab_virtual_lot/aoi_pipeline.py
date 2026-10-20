"""Headless AOI inference and durable local JPG results for Jetson or WSL."""

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Mapping
from uuid import UUID, uuid4

import cv2
import numpy as np


PART_CLASSES = {0: "body", 1: "lead", 2: "tab"}
DEFECT_CLASSES = {0: "crash", 1: "bend"}


def annotation_style(width: int, height: int) -> tuple[float, int, int]:
    scale = max(.5, min(2.0, .5 * min(width, height) / 640))
    return scale, max(1, round(scale * 2)), max(2, round(scale * 2))


@dataclass(frozen=True)
class AoiConfig:
    result_dir: Path
    part_conf: float
    defect_conf: float
    part_iou: float
    defect_iou: float
    mode: str
    device_id: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> "AoiConfig":
        project = Path(env.get("JETSON_PROJECT_PATH", ".")).resolve()
        result_dir = Path(env.get("AOI_RESULT_DIR", str(project / "result" / "aoi"))).resolve()
        config = cls(result_dir, float(env.get("AOI_PART_CONF_THRESHOLD", ".35")),
                     float(env.get("AOI_DEFECT_CONF_THRESHOLD", ".20")),
                     float(env.get("AOI_PART_IOU_THRESHOLD", ".45")),
                     float(env.get("AOI_DEFECT_IOU_THRESHOLD", ".35")),
                     env.get("AOI_MODE", "mock"), env.get("AOI_DEVICE_ID", "jetson-1"))
        if any(not 0 < x <= 1 for x in (config.part_conf, config.defect_conf,
                                        config.part_iou, config.defect_iou)):
            raise ValueError("AOI thresholds must be in (0,1]")
        if config.mode not in {"mock", "prod"} or not config.device_id.strip():
            raise ValueError("invalid AOI mode or device ID")
        return config


def model_paths(env: Mapping[str, str] = os.environ) -> tuple[Path, Path]:
    paths = (Path(env["AOI_PART_MODEL_FILE"]), Path(env["AOI_DEFECT_MODEL_FILE"]))
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    return paths


class UltralyticsModel:
    def __init__(self, weight: Path, device: str = "cpu") -> None:
        from ultralytics import YOLO
        self.model = YOLO(str(weight))
        self.device = device

    def predict(self, image: np.ndarray, conf: float, iou: float) -> list[dict]:
        result = self.model.predict(source=image, conf=conf, iou=iou,
                                    device=self.device, verbose=False)[0]
        found = []
        masks = result.masks.data.cpu().numpy() if result.masks is not None else None
        for index, box in enumerate(result.boxes):
            detection = {"cls": int(box.cls[0].item()),
                         "conf": float(box.conf[0].item()),
                         "xyxy": [float(x) for x in box.xyxy[0].cpu().tolist()]}
            if masks is not None and index < len(masks):
                detection["_mask"] = masks[index]
            found.append(detection)
        return found


class MockModel:
    def __init__(self, label: int, confidence: float, box: tuple[int, int, int, int]):
        self.label, self.confidence, self.box = label, confidence, box

    def predict(self, image: np.ndarray, conf: float, iou: float) -> list[dict]:
        return ([{"cls": self.label, "conf": self.confidence, "xyxy": self.box}]
                if self.confidence >= conf else [])


class RelativeMockModel(MockModel):
    """Synthetic detection whose box is expressed as image-relative ratios."""

    def predict(self, image: np.ndarray, conf: float, iou: float) -> list[dict]:
        if self.confidence < conf:
            return []
        height, width = image.shape[:2]
        x1, y1, x2, y2 = self.box
        return [{"cls": self.label, "conf": self.confidence,
                 "xyxy": (x1 * width, y1 * height, x2 * width, y2 * height)}]


def _fields(box):
    if isinstance(box, dict):
        return (int(box["cls"]), float(box["conf"]),
                [float(x) for x in box["xyxy"]], box.get("_mask"))
    return int(box.cls), float(box.conf), [float(x) for x in box.xyxy], None


def _write_jpg(path: Path, image: np.ndarray) -> dict:
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    if not ok:
        raise OSError("JPG encoding failed")
    data = encoded.tobytes()
    temp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    try:
        with temp.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return {"artifact_id": str(uuid4()), "local_directory": str(path.parent),
            "file_name": path.name, "sha256": sha256(data).hexdigest(),
            "byte_size": len(data), "width": int(image.shape[1]),
            "height": int(image.shape[0])}


def inspect_image(image: np.ndarray, job_id: UUID, attempt: int, config: AoiConfig,
                  part_model, defect_model) -> dict:
    if attempt < 1 or image is None or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("invalid AOI image or attempt")
    directory = config.result_dir / str(job_id) / str(attempt)
    manifest = directory / "result.json"
    if manifest.exists():
        return json.loads(manifest.read_text(encoding="utf-8"))
    directory.mkdir(parents=True, exist_ok=True)
    source = image.copy()
    detections = []
    annotated = source.copy()
    font_scale, text_thickness, box_thickness = annotation_style(
        annotated.shape[1], annotated.shape[0])
    for model_name, model, threshold, iou, class_names, color in (
        ("part", part_model, config.part_conf, config.part_iou, PART_CLASSES, (255, 128, 0)),
        ("defect", defect_model, config.defect_conf, config.defect_iou, DEFECT_CLASSES, (0, 0, 255)),
    ):
        for box in model.predict(source.copy(), conf=threshold, iou=iou):
            cls, confidence, coords, mask = _fields(box)
            detection = {"model_stage": model_name, "class_id": cls,
                         "class_name": class_names.get(cls, f"cls_{cls}"),
                         "confidence": confidence, "bbox_xyxy": coords}
            detections.append(detection)
            if mask is not None:
                resized = cv2.resize(np.asarray(mask, dtype=np.float32),
                                     (annotated.shape[1], annotated.shape[0])) > .5
                blended = cv2.addWeighted(annotated, .65,
                                          np.full_like(annotated, color), .35, 0)
                annotated[resized] = blended[resized]
            x1, y1, x2, y2 = [int(x) for x in coords]
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, box_thickness)
            label = f"{detection['class_name']} {confidence:.2f}"
            (text_width, text_height), baseline = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_thickness)
            label_bottom = max(text_height + baseline + 6, y1)
            label_top = max(0, label_bottom - text_height - baseline - 6)
            cv2.rectangle(annotated, (x1, label_top),
                          (min(annotated.shape[1] - 1, x1 + text_width + 8), label_bottom),
                          color, cv2.FILLED)
            cv2.putText(annotated, label, (x1 + 4, label_bottom - baseline - 3),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255),
                        text_thickness, cv2.LINE_AA)
    part_found = any(d["model_stage"] == "part" for d in detections)
    verdict = ("fail" if any(d["model_stage"] == "defect" for d in detections)
               else "pass" if part_found else "review")
    images = {"original": _write_jpg(directory / "original.jpg", source),
              "annotated": _write_jpg(directory / "annotated.jpg", annotated)}
    result = {"job_id": str(job_id), "attempt": attempt, "verdict": verdict,
              "device_id": config.device_id, "result_origin": config.mode,
              "thresholds": {"part_conf": config.part_conf, "defect_conf": config.defect_conf,
                             "part_iou": config.part_iou, "defect_iou": config.defect_iou},
              "detections": detections, "images": images}
    temp = manifest.with_name("result." + uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, manifest)
    finally:
        temp.unlink(missing_ok=True)
    return result
