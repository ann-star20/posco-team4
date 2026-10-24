"""Smoke-test the complete diagnostic flow; never execute or approve recipes."""
import importlib.util
import json
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def validate_high_precision(check):
    if not check.get("실시") or check.get("모드") != "고정밀(GP+TabPFN)":
        raise AssertionError("High-precision check was skipped or fell back to GP")
    for key in ("최다확률_전", "최다확률_후", "보정후_Vth규격확률_고정밀"):
        if not 0 <= check[key] <= 1:
            raise AssertionError("Invalid probability: " + key)


def worker():
    import numpy as np
    import torch
    from agent_check import fingerprint

    reference = json.loads((ROOT / "agent_reference.json").read_text(encoding="utf-8"))
    if fingerprint(ROOT) != reference["hashes"]:
        raise RuntimeError("Source/model hashes differ from the verified basic deployment")
    spec = importlib.util.spec_from_file_location("hp_agent_target", ROOT / "진단에이전트" / "진단에이전트.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    started = time.perf_counter()
    agent, pipe = module.build_agent(high_precision=True)
    initialization_seconds = time.perf_counter() - started
    if not pipe.high_precision_available:
        raise RuntimeError("High precision unavailable: " + str(pipe.hp_error))
    results = []
    for case in reference["cases"]:
        print("START_HP_AGENT_CASE", case["name"], flush=True)
        agent.rng = np.random.default_rng(0)
        started = time.perf_counter()
        output = agent.run(case["measurement"], n_wafers=case["n_wafers"], check=True)
        seconds = time.perf_counter() - started
        diagnosis, proposal, hp = output["진단"], output["보정안"], output["고정밀확인"]
        validate_high_precision(hp)
        probabilities = diagnosis["범주확률"]
        if not np.isclose(sum(probabilities.values()), 1.0, atol=1e-8):
            raise AssertionError("Invalid base posterior")
        if not all(np.isfinite(value) and 0 <= value <= 1 for value in probabilities.values()):
            raise AssertionError("Non-finite base probability")
        if not all(0.85 <= proposal[key] <= 1.15 for key in ("도즈배율", "산화막배율")):
            raise AssertionError("Proposal outside configured factor bounds")
        jobs = output["TCAD확인요청"]
        if len(jobs) != 2:
            raise AssertionError("Expected two TCAD request candidates")
        job_points = np.array([[job[key] for key in ("도즈", "에피", "산화막")] for job in jobs])
        if not np.all(np.isfinite(job_points)):
            raise AssertionError("Invalid TCAD request values")
        domain = agent.sur.domain(job_points).tolist()
        expected = next(item for item in reference["results"] if item["name"] == case["name"])
        base_delta = max(abs(probabilities[key] - expected["probabilities"][key]) for key in probabilities)
        if base_delta > 1e-4 or diagnosis["판정"] != expected["decision"]:
            raise AssertionError("Base diagnostic result changed unexpectedly in the HP environment")
        review_needed = bool(hp["판정바뀜"] or not hp["판정됨_후"] or not all(domain))
        summary = {"name": case["name"], "basic_decision": diagnosis["판정"], "high_precision": hp,
                   "dose_factor": proposal["도즈배율"], "oxide_factor": proposal["산화막배율"],
                   "recommendation": output["다음측정"]["권고"], "proposal_warning": proposal["경고"],
                   "tcad_requests": jobs, "tcad_requests_in_domain": domain, "tcad_verified": False,
                   "requires_review": review_needed, "max_basic_pc_probability_difference": base_delta,
                   "total_seconds": seconds}
        print(output["요약문"], flush=True)
        print("CASE_RESULT", json.dumps(summary, ensure_ascii=False, allow_nan=False), flush=True)
        results.append(summary)
    report = {"status": "passed", "scope": "four synthetic full-flow checks; not diagnostic accuracy or TCAD validation",
              "numpy": np.__version__, "torch": torch.__version__, "cuda_available": torch.cuda.is_available(),
              "initialization_seconds": initialization_seconds, "results": results,
              "review_required_cases": [item["name"] for item in results if item["requires_review"]],
              "approval_or_recipe_application_executed": False}
    print("HP_AGENT_WORKER_RESULT " + json.dumps(report, ensure_ascii=False, allow_nan=False), flush=True)


def main():
    try:
        completed = subprocess.run([sys.executable, "-u", str(Path(__file__).resolve()), "--worker"],
                                   capture_output=True, text=True, encoding="utf-8", timeout=300)
        print(completed.stdout, flush=True)
        (ROOT / "agent_high_precision_worker_stderr.log").write_text(completed.stderr, encoding="utf-8")
        marker = next((line for line in completed.stdout.splitlines() if line.startswith("HP_AGENT_WORKER_RESULT ")), None)
        if completed.returncode or marker is None:
            report = {"status": "failed", "error_tail": completed.stderr.splitlines()[-16:]}
        else:
            report = json.loads(marker.removeprefix("HP_AGENT_WORKER_RESULT "))
    except subprocess.TimeoutExpired:
        report = {"status": "timeout", "reason": "Full-flow worker exceeded 300 seconds"}
    except Exception as exc:
        traceback.print_exc()
        report = {"status": "failed", "error": type(exc).__name__ + ": " + str(exc)}
    (ROOT / "agent_high_precision_result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print("JETSON_HP_AGENT_STATUS " + json.dumps(report, ensure_ascii=False, allow_nan=False), flush=True)


if __name__ == "__main__":
    if "--worker" in sys.argv:
        worker()
    else:
        main()
