#!/usr/bin/env python3
"""Export and benchmark a YOLO segmentation model on a Jetson device.

The script never overwrites the source checkpoint.  Every export and result is
stored in a unique run directory with hashes and environment metadata.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import re
import shutil
import statistics
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
import yaml
from ultralytics import YOLO


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
RAM_RE = re.compile(r"RAM\s+(\d+)/(\d+)MB")
GPU_RE = re.compile(r"GR3D_FREQ\s+(\d+)%")
TEMP_RE = re.compile(r"(?:gpu|GPU)@([0-9.]+)C")
POWER_RE = re.compile(r"VDD_(?:GPU_SOC|IN)\s+(\d+)mW")


@dataclass
class Telemetry:
    samples: int = 0
    ram_used_mb_mean: float | None = None
    ram_used_mb_max: int | None = None
    gpu_util_pct_mean: float | None = None
    gpu_util_pct_max: int | None = None
    gpu_temp_c_max: float | None = None
    power_mw_mean: float | None = None
    power_mw_max: int | None = None


class TegrastatsSampler:
    def __init__(self, interval_ms: int = 100) -> None:
        self.interval_ms = interval_ms
        self.lines: list[str] = []
        self.process: subprocess.Popen[str] | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "TegrastatsSampler":
        executable = shutil.which("tegrastats")
        if not executable:
            return self
        self.process = subprocess.Popen(
            [executable, "--interval", str(self.interval_ms)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

        def read_lines() -> None:
            assert self.process and self.process.stdout
            for line in self.process.stdout:
                self.lines.append(line.strip())

        self.thread = threading.Thread(target=read_lines, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
        if self.thread is not None:
            self.thread.join(timeout=1)

    def summary(self) -> Telemetry:
        ram: list[int] = []
        gpu: list[int] = []
        temp: list[float] = []
        power: list[int] = []
        for line in self.lines:
            if match := RAM_RE.search(line):
                ram.append(int(match.group(1)))
            if match := GPU_RE.search(line):
                gpu.append(int(match.group(1)))
            if match := TEMP_RE.search(line):
                temp.append(float(match.group(1)))
            if match := POWER_RE.search(line):
                power.append(int(match.group(1)))
        return Telemetry(
            samples=len(self.lines),
            ram_used_mb_mean=round(statistics.fmean(ram), 2) if ram else None,
            ram_used_mb_max=max(ram) if ram else None,
            gpu_util_pct_mean=round(statistics.fmean(gpu), 2) if gpu else None,
            gpu_util_pct_max=max(gpu) if gpu else None,
            gpu_temp_c_max=max(temp) if temp else None,
            power_mw_mean=round(statistics.fmean(power), 2) if power else None,
            power_mw_max=max(power) if power else None,
        )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def stats(values: list[float]) -> dict[str, float]:
    return {
        "mean": round(statistics.fmean(values), 3),
        "std": round(statistics.pstdev(values), 3),
        "p50": round(percentile(values, 0.50), 3),
        "p95": round(percentile(values, 0.95), 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def resolve_validation_images(data_yaml: Path) -> list[Path]:
    config = yaml.safe_load(data_yaml.read_text(encoding="utf-8"))
    root = Path(config.get("path", data_yaml.parent))
    if not root.is_absolute():
        root = (data_yaml.parent / root).resolve()
    value = config["val"]
    entries = value if isinstance(value, list) else [value]
    images: list[Path] = []
    for entry in entries:
        path = Path(entry)
        if not path.is_absolute():
            path = root / path
        if path.is_dir():
            images.extend(item for item in path.rglob("*") if item.suffix.lower() in IMAGE_SUFFIXES)
        elif path.is_file() and path.suffix.lower() == ".txt":
            for line in path.read_text(encoding="utf-8").splitlines():
                candidate = Path(line.strip())
                if not candidate.is_absolute():
                    candidate = root / candidate
                images.append(candidate)
        elif path.is_file():
            images.append(path)
    images = sorted({item.resolve() for item in images if item.exists()})
    if not images:
        raise RuntimeError(f"no validation images resolved from {data_yaml}")
    return images


def synchronize(device: str | int) -> None:
    if device != "cpu" and torch.cuda.is_available():
        torch.cuda.synchronize()


def benchmark_latency(
    artifact: Path,
    images: list[Path],
    imgsz: int,
    warmup: int,
    iterations: int,
    device: str | int,
) -> dict[str, Any]:
    model = YOLO(str(artifact), task="segment")
    sources = [str(path) for path in images]
    for index in range(warmup):
        model.predict(source=sources[index % len(sources)], imgsz=imgsz, device=device, batch=1, verbose=False)
    synchronize(device)

    wall: list[float] = []
    inference: list[float] = []
    preprocess: list[float] = []
    postprocess: list[float] = []
    sampler = TegrastatsSampler()
    with sampler:
        for index in range(iterations):
            source = sources[index % len(sources)]
            synchronize(device)
            started = time.perf_counter_ns()
            results = model.predict(source=source, imgsz=imgsz, device=device, batch=1, verbose=False)
            synchronize(device)
            wall.append((time.perf_counter_ns() - started) / 1_000_000)
            for result in results:
                preprocess.append(float(result.speed["preprocess"]))
                inference.append(float(result.speed["inference"]))
                postprocess.append(float(result.speed["postprocess"]))
    wall_stats = stats(wall)
    return {
        "warmup_iterations": warmup,
        "measured_iterations": iterations,
        "sample_image_count": len(images),
        "wall_ms": wall_stats,
        "preprocess_ms": stats(preprocess),
        "inference_ms": stats(inference),
        "postprocess_ms": stats(postprocess),
        "throughput_fps": round(1000.0 / wall_stats["mean"], 3),
        "telemetry": asdict(sampler.summary()),
    }


def validate(artifact: Path, data_yaml: Path, imgsz: int, device: str | int) -> dict[str, float]:
    model = YOLO(str(artifact), task="segment")
    metrics = model.val(
        data=str(data_yaml),
        imgsz=imgsz,
        batch=1,
        device=device,
        plots=False,
        save_json=False,
        verbose=False,
    )
    result = {
        "box_precision": round(float(metrics.box.mp), 6),
        "box_recall": round(float(metrics.box.mr), 6),
        "box_map50": round(float(metrics.box.map50), 6),
        "box_map50_95": round(float(metrics.box.map), 6),
    }
    if getattr(metrics, "seg", None) is not None:
        result.update(
            {
                "mask_precision": round(float(metrics.seg.mp), 6),
                "mask_recall": round(float(metrics.seg.mr), 6),
                "mask_map50": round(float(metrics.seg.map50), 6),
                "mask_map50_95": round(float(metrics.seg.map), 6),
            }
        )
    return result


def export_artifacts(source: Path, output: Path, imgsz: int, workspace: float) -> dict[str, Path]:
    output.mkdir(parents=True, exist_ok=False)
    onnx_source = output / "onnx_source.pt"
    trt_source = output / "trt_fp16_source.pt"
    shutil.copy2(source, onnx_source)
    shutil.copy2(source, trt_source)

    onnx_result = Path(
        YOLO(str(onnx_source)).export(
            format="onnx", imgsz=imgsz, batch=1, dynamic=False, simplify=True, opset=17, device=0
        )
    )
    onnx_target = output / "model_fp32.onnx"
    onnx_result.replace(onnx_target)

    engine_result = Path(
        YOLO(str(trt_source)).export(
            format="engine",
            imgsz=imgsz,
            batch=1,
            dynamic=False,
            simplify=True,
            opset=17,
            device=0,
            half=True,
            workspace=workspace,
            verbose=False,
        )
    )
    engine_target = output / "model_fp16.engine"
    engine_result.replace(engine_target)
    onnx_source.unlink(missing_ok=True)
    trt_source.unlink(missing_ok=True)
    return {"pytorch_fp32": source, "onnx_fp32_cpu": onnx_target, "tensorrt_fp16": engine_target}


def environment() -> dict[str, Any]:
    import numpy
    import ultralytics

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "torch": torch.__version__,
        "ultralytics": ultralytics.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--imgsz", type=int, default=1024)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--workspace", type=float, default=2.0)
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%dT%H%M%S"))
    parser.add_argument("--skip-export", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_path = args.model.resolve()
    data_yaml = args.data.resolve()
    run_dir = (args.output_root / args.run_id).resolve()
    artifacts_dir = run_dir / "artifacts"
    run_dir.mkdir(parents=True, exist_ok=False)
    images = resolve_validation_images(data_yaml)

    if args.skip_export:
        raise SystemExit("--skip-export requires a future explicit artifact manifest and is intentionally disabled")
    artifacts = export_artifacts(model_path, artifacts_dir, args.imgsz, args.workspace)
    devices: dict[str, str | int] = {"pytorch_fp32": 0, "onnx_fp32_cpu": "cpu", "tensorrt_fp16": 0}

    rows: list[dict[str, Any]] = []
    for name, artifact in artifacts.items():
        print(f"[evaluate] {name}: {artifact}", flush=True)
        row = {
            "format": name,
            "artifact": str(artifact),
            "artifact_bytes": artifact.stat().st_size,
            "sha256": sha256(artifact),
            "accuracy": validate(artifact, data_yaml, args.imgsz, devices[name]),
            "performance": benchmark_latency(
                artifact, images, args.imgsz, args.warmup, args.iterations, devices[name]
            ),
        }
        rows.append(row)

    baseline = next(row for row in rows if row["format"] == "pytorch_fp32")
    optimized = next(row for row in rows if row["format"] == "tensorrt_fp16")
    latency_gain = 1.0 - optimized["performance"]["wall_ms"]["p95"] / baseline["performance"]["wall_ms"]["p95"]
    box_loss = baseline["accuracy"]["box_map50_95"] - optimized["accuracy"]["box_map50_95"]
    mask_loss = baseline["accuracy"]["mask_map50_95"] - optimized["accuracy"]["mask_map50_95"]
    gates = {
        "tensorrt_p95_reduction_target": 0.30,
        "tensorrt_p95_reduction_actual": round(latency_gain, 6),
        "max_absolute_map50_95_loss": 0.01,
        "box_map50_95_loss": round(box_loss, 6),
        "mask_map50_95_loss": round(mask_loss, 6),
        "latency_pass": latency_gain >= 0.30,
        "accuracy_pass": box_loss <= 0.01 and mask_loss <= 0.01,
    }
    gates["overall_pass"] = gates["latency_pass"] and gates["accuracy_pass"]
    result = {
        "schema_version": "1.0",
        "run_id": args.run_id,
        "source": {"path": str(model_path), "sha256": sha256(model_path)},
        "data": {"path": str(data_yaml), "validation_images": len(images)},
        "settings": {
            "imgsz": args.imgsz,
            "batch": 1,
            "warmup": args.warmup,
            "iterations": args.iterations,
            "workspace_gb": args.workspace,
        },
        "environment": environment(),
        "results": rows,
        "gates": gates,
    }
    json_path = run_dir / "benchmark.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    csv_path = run_dir / "benchmark.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "format",
                "artifact_bytes",
                "sha256",
                "box_map50_95",
                "mask_map50_95",
                "wall_mean_ms",
                "wall_p50_ms",
                "wall_p95_ms",
                "throughput_fps",
                "ram_used_mb_max",
                "gpu_util_pct_mean",
                "gpu_temp_c_max",
                "power_mw_mean",
            ],
        )
        writer.writeheader()
        for row in rows:
            performance = row["performance"]
            telemetry = performance["telemetry"]
            writer.writerow(
                {
                    "format": row["format"],
                    "artifact_bytes": row["artifact_bytes"],
                    "sha256": row["sha256"],
                    "box_map50_95": row["accuracy"]["box_map50_95"],
                    "mask_map50_95": row["accuracy"]["mask_map50_95"],
                    "wall_mean_ms": performance["wall_ms"]["mean"],
                    "wall_p50_ms": performance["wall_ms"]["p50"],
                    "wall_p95_ms": performance["wall_ms"]["p95"],
                    "throughput_fps": performance["throughput_fps"],
                    "ram_used_mb_max": telemetry["ram_used_mb_max"],
                    "gpu_util_pct_mean": telemetry["gpu_util_pct_mean"],
                    "gpu_temp_c_max": telemetry["gpu_temp_c_max"],
                    "power_mw_mean": telemetry["power_mw_mean"],
                }
            )
    print(json.dumps(gates, indent=2), flush=True)
    print(f"saved: {run_dir}", flush=True)


if __name__ == "__main__":
    main()
