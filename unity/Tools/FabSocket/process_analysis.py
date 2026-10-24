"""Display-only process-analysis contract. No approvals or equipment commands."""
import math
import time

CAUSES = {"정상", "도즈", "에피", "도즈+에피", "산화막", "도즈+산화막", "에피+산화막", "도즈+에피+산화막"}

UNITS = dict(vth="V", gm="A/V/um", id4v="A/um", bv="V")

def identity(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid identifier")

def validate_request(p, fresh=True):
    if not isinstance(p, dict):
        raise ValueError("Request object required")
    for key in ("request_id", "lot_id", "baseline_version"):
        identity(p.get(key))
    if p.get("data_source") != "synthetic" or p.get("units") != UNITS:
        raise ValueError("Explicit synthetic electrical inputs and physical units required")
    if type(p.get("n_wafers")) is not int or not 1 <= p["n_wafers"] <= 10000:
        raise ValueError("Invalid wafer count")
    m = p.get("measurement")
    if not isinstance(m, dict) or set(m) != set(UNITS):
        raise ValueError("Four metrics required; missing BV must be null")
    number(m["vth"], -100, 100)
    for key in ("gm", "id4v"):
        number(m[key], 1e-15, 1)
    if m["bv"] is not None:
        number(m["bv"], .001, 10000)
    if type(p.get("sent_at_ms")) is not int or p["sent_at_ms"] <= 0 or (fresh and abs(int(time.time()*1000)-p["sent_at_ms"]) > 120000):
        raise ValueError("Expired request")

def validate_status(p):
    if p.get("state") not in {"ready", "running", "failed"}:
        raise ValueError("Invalid worker state")
    if p["state"] != "ready":
        identity(p.get("request_id")); identity(p.get("lot_id"))
    if not isinstance(p.get("detail"), str) or len(p["detail"]) > 300 or any(ord(c)<32 for c in p["detail"]):
        raise ValueError("Invalid status text")


def number(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("Invalid analysis numeric value")


def validate_analysis(payload):
    for key in ("lot_id", "run_id", "proposal_id", "baseline_version", "model_version"):
        value = payload.get(key)
        if not isinstance(value, str) or not 1 <= len(value) <= 128 or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid analysis identifier")
    if payload.get("data_source") != "synthetic" or payload.get("delivery") not in {"replay", "computed"}:
        raise ValueError("Labelled synthetic inputs required")
    if payload["delivery"] == "computed":
        identity(payload.get("request_id"))
        validate_request(payload.get("input", {}), fresh=False)
        if any(payload["input"][k] != payload[k] for k in ("request_id", "lot_id", "baseline_version")):
            raise ValueError("Input/result identity mismatch")
    if payload.get("mode") not in {"gp_tabpfn", "gp_only"} or payload.get("tcad_status") != "not_run" or payload.get("applied") is not False:
        raise ValueError("Analysis cannot claim TCAD verification or recipe application")
    probability = payload.get("top_probability")
    number(probability, 0, 1)
    cause = payload.get("top_cause")
    if cause not in CAUSES or type(payload.get("decided")) is not bool:
        raise ValueError("Invalid diagnostic decision")
    if payload["decided"] != (probability >= 0.70):
        raise ValueError("Decision inconsistent with the configured 70 percent threshold")
    expected = "ambiguous" if not payload["decided"] else "normal" if cause == "정상" else "diagnosed"
    if payload.get("decision") != expected:
        raise ValueError("Invalid decision status")
    for key in ("dose_factor", "oxide_factor"):
        number(payload.get(key), 0.85 - 1e-9, 1.15 + 1e-9)
    for key in ("estimated_dose", "estimated_epi", "estimated_oxide"):
        number(payload.get(key), 0.01, 10)
    number(payload.get("duration_seconds"), 0, 3600)
    candidates = payload.get("basic_candidates")
    if not isinstance(candidates, list) or len(candidates) != 8:
        raise ValueError("Eight basic-mode cause probabilities required")
    if not all(isinstance(item, dict) for item in candidates) or {item.get("name") for item in candidates} != CAUSES:
        raise ValueError("Unknown or duplicate cause")
    for item in candidates:
        number(item.get("probability"), 0, 1)
    if abs(sum(item["probability"] for item in candidates) - 1) > 1e-5:
        raise ValueError("Basic-mode probabilities must sum to one")
    for key in ("recommendation", "warning"):
        value = payload.get(key)
        if not isinstance(value, str) or len(value) > 500 or any(ord(c) < 32 for c in value):
            raise ValueError("Invalid analysis text")
    sent = payload.get("sent_at_ms")
    generated = payload.get("generated_at_ms")
    if type(sent) is not int or abs(int(time.time() * 1000) - sent) > 120000:
        raise ValueError("Analysis transport timestamp invalid")
    if type(generated) is not int or not 0 < generated <= sent + 120000:
        raise ValueError("Analysis generation timestamp invalid")


def from_result(result, basic, run_id, baseline_version, model_version, generated_at_ms):
    hp = result["high_precision"]
    if not hp["실시"] or hp["모드"] != "고정밀(GP+TabPFN)":
        raise ValueError("Actual high-precision result required")
    cause, probability = hp["판정_후"], hp["최다확률_후"]
    decided = hp["판정됨_후"]
    point = result["tcad_requests"][0]
    payload = dict(lot_id="JETSON-TEST-" + result["name"], run_id=run_id,
                   proposal_id=run_id + "-" + result["name"], baseline_version=baseline_version,
                   model_version=model_version, data_source="synthetic", delivery="replay", mode="gp_tabpfn",
                   decision="ambiguous" if not decided else "normal" if cause == "정상" else "diagnosed",
                   decided=decided, top_cause=cause, top_probability=probability,
                   dose_factor=result["dose_factor"], oxide_factor=result["oxide_factor"],
                   estimated_dose=point["도즈"] / result["dose_factor"], estimated_epi=point["에피"],
                   estimated_oxide=point["산화막"] / result["oxide_factor"],
                   basic_candidates=[dict(name=name, probability=p) for name, p in sorted(basic["probabilities"].items(), key=lambda pair: -pair[1])],
                   recommendation=result["recommendation"], warning=result["proposal_warning"] or "",
                   duration_seconds=result["total_seconds"], tcad_status="not_run", applied=False,
                   generated_at_ms=generated_at_ms, sent_at_ms=int(time.time() * 1000))
    validate_analysis(payload)
    return payload
