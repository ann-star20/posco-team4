"""Compare basic-GP diagnosis on identical simulated inputs and a fixed RNG seed."""
import argparse
import hashlib
import importlib.util
import json
import platform
import time
from pathlib import Path

import numpy as np


def fingerprint(root):
    names = ["진단에이전트/진단에이전트.py", "최종ML/2단_GP.py", "최종ML/ml_파이프라인.py",
             "최종ML/모델/gp.npz", "최종ML/모델/영역.json", "최종ML/모델/모델정보.json"]
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--reference", type=Path, default=Path(__file__).with_name("agent_reference.json"))
    parser.add_argument("--make-reference", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    reference = None if args.make_reference else json.loads(args.reference.read_text(encoding="utf-8"))
    hashes = fingerprint(root)
    if reference is not None and hashes != reference["hashes"]:
        raise RuntimeError("PC and Jetson source/model hashes differ")
    spec = importlib.util.spec_from_file_location("diagnostic_check_target", root / "진단에이전트" / "진단에이전트.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    started = time.perf_counter()
    agent, pipe = module.build_agent(high_precision=False)
    initialization_seconds = time.perf_counter() - started
    if pipe.high_precision_available:
        raise AssertionError("High precision must remain disabled in this check")
    if reference is None:
        cases = []
        for name, knobs, count, with_bv in [
            ("normal", [1.0, 1.0, 1.0], 100, True),
            ("oxide_plus15", [1.0, 1.0, 1.15], 5, False),
            ("epi_minus40_without_bv", [1.0, 0.6, 1.0], 5, False),
            ("epi_minus40_with_bv", [1.0, 0.6, 1.0], 5, True),
        ]:
            prediction = agent.sur.predict([knobs])
            measurement = {key: float(prediction[key][0]) for key in ("vth", "gm", "id4v", "bv")}
            if not with_bv:
                measurement["bv"] = None
            cases.append({"name": name, "truth_ratios": knobs, "n_wafers": count, "measurement": measurement})
    else:
        cases = reference["cases"]
    results = []
    for case in cases:
        print("START_CASE", case["name"], flush=True)
        agent.rng = np.random.default_rng(0)
        started = time.perf_counter()
        output = agent.run(case["measurement"], n_wafers=case["n_wafers"], check=False)
        seconds = time.perf_counter() - started
        diagnosis, proposal = output["진단"], output["보정안"]
        probabilities = diagnosis["범주확률"]
        if not np.isclose(sum(probabilities.values()), 1.0, atol=1e-8):
            raise AssertionError("Posterior probabilities do not sum to one")
        if not all(np.isfinite(value) and 0 <= value <= 1 for value in probabilities.values()):
            raise AssertionError("Invalid posterior probabilities")
        for key in ("도즈배율", "산화막배율"):
            if not 0.85 <= proposal[key] <= 1.15:
                raise AssertionError("Correction factor outside configured bounds")
        if output["고정밀확인"]["실시"]:
            raise AssertionError("Unexpected high precision execution")
        if case["name"] == "normal" and not (diagnosis["최다"] == "정상" and diagnosis["최다확률"] > 0.5):
            raise AssertionError("Normal case self-check failed")
        if case["name"] == "epi_minus40_without_bv" and (diagnosis["판정됨"] or "BV" not in output["다음측정"]["권고"]):
            raise AssertionError("Ambiguous case must abstain and recommend BV")
        if case["name"] == "epi_minus40_with_bv" and not (diagnosis["노브"][1]["벗어날확률"] > 0.9 and proposal["경고"]):
            raise AssertionError("Epi case must report high epi probability and warning")
        summary = {"name": case["name"], "decision": diagnosis["판정"], "top": diagnosis["최다"],
                   "decided": diagnosis["판정됨"], "top_probability": diagnosis["최다확률"],
                   "probabilities": probabilities, "knob_means": [item["평균"] for item in diagnosis["노브"]],
                   "dose_factor": proposal["도즈배율"], "oxide_factor": proposal["산화막배율"],
                   "recommendation": output["다음측정"]["권고"], "seconds": seconds}
        if reference is not None:
            expected = next(item for item in reference["results"] if item["name"] == case["name"])
            errors = [abs(probabilities[key] - expected["probabilities"][key]) for key in probabilities]
            errors += [abs(a - b) for a, b in zip(summary["knob_means"], expected["knob_means"])]
            errors += [abs(summary[key] - expected[key]) for key in ("dose_factor", "oxide_factor")]
            summary["max_pc_absolute_difference"] = max(errors)
            if max(errors) > 1e-4 or summary["decision"] != expected["decision"]:
                raise AssertionError("PC comparison failed: " + json.dumps(summary, ensure_ascii=False))
        print(output["요약문"], flush=True)
        print("CASE_SECONDS", case["name"], round(seconds, 3), flush=True)
        results.append(summary)
    report = {"status": "passed", "scope": "basic GP diagnostic smoke test; synthetic inputs, not TCAD verification",
              "machine": platform.machine(), "python": platform.python_version(), "numpy": np.__version__,
              "initialization_seconds": initialization_seconds, "hashes": hashes, "cases": cases, "results": results}
    destination = args.reference if args.make_reference else root / "agent_result.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print("JETSON_AGENT_STATUS", json.dumps(report, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
