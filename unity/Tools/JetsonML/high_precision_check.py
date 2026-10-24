"""Inspect existing dependencies, then check twelve GP+TabPFN reference points."""
import csv
import importlib.metadata
import importlib.util
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(filename):
    spec = importlib.util.spec_from_file_location(filename.stem, filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worker():
    import numpy as np
    import torch

    model_root = ROOT / "최종ML"
    load(model_root / "고정밀.py").selftest_combine()
    started = time.perf_counter()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    pipeline = load(model_root / "ml_파이프라인.py").TwoStagePipeline(high_precision=True, device=device)
    initialization = time.perf_counter() - started
    with (model_root / "테스트" / "jetson_테스트입력.csv").open(encoding="utf-8-sig") as handle:
        rows = [row for row in csv.DictReader(handle) if row["PC_고정밀_bv"]]
    if len(rows) != 12:
        raise AssertionError("Expected twelve reference inputs")
    inputs = np.array([[float(row[key]) for key in ("도즈", "에피", "산화막")] for row in rows], dtype=np.float64)
    started = time.perf_counter()
    result = pipeline.refine(inputs)
    prediction_seconds = time.perf_counter() - started
    if result["mode"] != "고정밀(GP+TabPFN)":
        raise AssertionError("GP fallback is not a high-precision pass")
    for key in ("vth", "gm", "id4v", "bv", "sigma_vth", "sigma_gm", "sigma_id4v", "sigma_bv"):
        if not np.all(np.isfinite(result[key])):
            raise AssertionError("Non-finite output: " + key)
        if key.startswith("sigma_") and not np.all(result[key] > 0):
            raise AssertionError("Nonpositive uncertainty: " + key)
    if not np.all(result["in_domain"]):
        raise AssertionError("Reference points outside model domain")
    vth_error = float(np.max(np.abs(result["vth"] - [float(row["PC_고정밀_vth"]) for row in rows])) * 1000)
    bv_error = float(np.max(np.abs(result["bv"] - [float(row["PC_고정밀_bv"]) for row in rows])))
    report = {"status": "passed" if vth_error < 5 and bv_error < 0.3 else "failed",
              "count": len(rows), "cuda_available": torch.cuda.is_available(), "requested_device": device,
              "torch_version": torch.__version__, "initialization_seconds": initialization,
              "prediction_seconds": prediction_seconds, "within_suggested_60_seconds": prediction_seconds <= 60,
              "max_vth_difference_mV": vth_error, "max_bv_difference_V": bv_error,
              "scope": "ML reference agreement only; not TCAD verification or full diagnostic-agent test"}
    print("HP_WORKER_RESULT " + json.dumps(report, ensure_ascii=False), flush=True)


def main():
    report = {"status": "checking", "machine": platform.machine(), "python": platform.python_version(), "packages": {}}
    for name in ("numpy", "torch", "tabpfn"):
        try:
            report["packages"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            report["packages"][name] = None
    for label, path in (("jetson_release", "/etc/nv_tegra_release"), ("memory", "/proc/meminfo")):
        if Path(path).is_file():
            report[label] = Path(path).read_text().splitlines()[0]
    missing = [name for name in ("numpy", "torch", "tabpfn") if importlib.util.find_spec(name) is None]
    weights = ROOT / "최종ML" / "모델" / "tabpfn" / "tabpfn-v2-regressor.ckpt"
    report["local_weights_present"] = weights.is_file()
    if missing or not weights.is_file():
        report.update(status="blocked", reason="Missing local dependencies or weights", missing_packages=missing)
    else:
        try:
            completed = subprocess.run([sys.executable, "-u", str(Path(__file__).resolve()), "--worker"],
                                       capture_output=True, text=True, encoding="utf-8", timeout=240)
            print(completed.stdout, flush=True)
            marker = next((line for line in completed.stdout.splitlines() if line.startswith("HP_WORKER_RESULT ")), None)
            if completed.returncode or marker is None:
                report.update(status="failed", reason="High-precision worker failed", error_tail=completed.stderr.splitlines()[-12:])
            else:
                report.update(json.loads(marker.removeprefix("HP_WORKER_RESULT ")))
        except subprocess.TimeoutExpired:
            report.update(status="timeout", reason="Worker stopped after 240 seconds")
    (ROOT / "high_precision_result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print("JETSON_HP_STATUS " + json.dumps(report, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == "__main__":
    if "--worker" in sys.argv:
        worker()
    else:
        main()
