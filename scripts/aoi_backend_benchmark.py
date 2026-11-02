#!/usr/bin/env python3
"""Benchmark AOI part/defect inference speed across pt/onnx/engine backends.

Run this ON THE JETSON (TensorRT .engine export is GPU/arch-specific and only
works on the device it will run on). Requires the fab_virtual_lot package on
PYTHONPATH, same as the live aoi_worker:

    PYTHONPATH=jetson_ws/src/fab_virtual_lot python3 scripts/aoi_backend_benchmark.py \
        --image /path/to/sample.jpg --device 0 --precision fp16 --runs 30

Exports best.pt -> onnx/engine next to the source weight the first time (skips
export if the target file already exists), then times UltralyticsModel.predict
per backend with an untimed warmup pass. Uses the exact same model class the
live AOI worker uses (aoi_pipeline.UltralyticsModel), so results reflect what
Unity-triggered inspections would actually see.
"""

import argparse
import statistics
import time
from pathlib import Path

import cv2

from fab_virtual_lot.aoi_pipeline import UltralyticsModel

DEFAULT_PART = Path("/home/jetson/project/smart_factory/aoi/models/mosfet_part_v5-26/weights/best.pt")
DEFAULT_DEFECT = Path("/home/jetson/project/smart_factory/aoi/models/mosfet_defect_v5-26/weights/best.pt")


def export_if_missing(pt_path: Path, fmt: str) -> Path:
    target = pt_path.with_suffix(".engine" if fmt == "engine" else f".{fmt}")
    if target.exists():
        return target
    from ultralytics import YOLO

    exported = Path(YOLO(str(pt_path)).export(format=fmt))
    if exported != target and exported.exists():
        exported.rename(target)
    return target


def time_backend(weight: Path, image, conf: float, iou: float, device: str, precision: str, runs: int):
    model = UltralyticsModel(weight, device, precision)
    model.predict(image, conf, iou)  # warmup, excluded from stats
    model.synchronize()
    samples = []
    for _ in range(runs):
        started = time.perf_counter()
        model.predict(image, conf, iou)
        model.synchronize()
        samples.append((time.perf_counter() - started) * 1000)
    return samples


def report(label: str, samples: list[float], baseline: float | None) -> float:
    mean = statistics.mean(samples)
    median = statistics.median(samples)
    speedup = f", {baseline / mean:.2f}x vs pt" if baseline else ""
    print(f"  {label:10s} mean={mean:7.2f}ms  median={median:7.2f}ms  min={min(samples):7.2f}ms{speedup}")
    return mean


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--part", type=Path, default=DEFAULT_PART)
    parser.add_argument("--defect", type=Path, default=DEFAULT_DEFECT)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--device", default="0")
    parser.add_argument("--precision", default="fp16", choices=["fp32", "fp16"])
    parser.add_argument("--conf", type=float, default=0.35)
    parser.add_argument("--iou", type=float, default=0.45)
    parser.add_argument("--runs", type=int, default=30)
    parser.add_argument("--formats", nargs="+", default=["pt", "onnx", "engine"])
    args = parser.parse_args()

    image = cv2.imread(str(args.image), cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"cannot read image: {args.image}")

    for label, pt_weight in (("part", args.part), ("defect", args.defect)):
        print(f"\n== {label} model ({pt_weight.name}) ==")
        baseline = None
        for fmt in args.formats:
            weight = pt_weight if fmt == "pt" else export_if_missing(pt_weight, fmt)
            samples = time_backend(weight, image, args.conf, args.iou, args.device, args.precision, args.runs)
            mean = report(fmt, samples, baseline)
            if fmt == "pt":
                baseline = mean


if __name__ == "__main__":
    main()
