"""모델 서비스 계약(fab-ml-v1)의 JSON <-> 서로게이트·진단 에이전트 입출력 변환. 네트워크 코드는 없다 (모델서비스.py 가 이 파일을 쓴다).

단위와 조건은 아래 상수 한 곳에서만 정한다. 값이 바뀌면 여기만 고친다.
확인 근거 (TCAD 실행 기록 runs/001/실행기록.log 와 deck 에서 직접 확인한 것)
  - 온도: Atlas 로그에 "Temperature = 300 K" -> 26.85 °C
  - Id 조건: deck 의 `solve vdrain=0.1` (Vd 0.1 V 고정), `solve vgate=0.0 vstep=0.1 vfinal=4.0` -> Id(4V) 는 Vg 4 V 점 (단계시험.py parse_iv: 4.0 V 점의 전류)
  - 길이: Atlas 로그 "Dimensions in microns", deck `deposit oxide thick=0.06` -> 산화막 μm
  - 전류: Atlas 로그 전극 전류 단위 "Jn(A/um)" -> 폭 1 μm 당 A (gm 도 폭 1 μm 당 S)
  - 도즈 cm^-2, 에피 cm^-3: deck 에서 DOSE 는 `implant boron dose=$DOSE`, N_DRIFT 는 `init silicon c.phos=$N_DRIFT`. 사용자 PC 의 Silvaco 자료 "Process simulation - Silvaco" 20쪽(Implant dose in atm/cm2), 13쪽(Concentration in atom/cm3)로 단위 확인. 산화막은 같은 자료 16쪽 "thickness ... µm".
  - 이상 판정 스펙(Vth 1.7~2.6 V, BV 40 V 이상): AOI4184 데이터시트(VGS(th) 1.7~2.6 V, BVDSS 최소 40 V)와 같은 값. 응답 metadata.spec 에 값과 상태(datasheet_AOI4184)를 같이 실어 보낸다.
"""
import math

CONTRACT_VERSION = "fab-ml-v1"
INPUT_TRANSFORM_VERSION = "gp-transform-v1"
BASE = {"body_dose": 7.7e12, "epi_doping": 1.7e16, "oxide_thickness": 0.06}
UNITS_IN = {"body_dose": "cm^-2", "epi_doping": "cm^-3", "oxide_thickness": "um"}
UNITS_OUT = {"vth": "V", "gm": "uS/um", "id_on": "uA/um", "bv": "V"}
ID_CONDITIONS = {"vgs_v": 4.0, "vds_v": 0.1, "temperature_c": 26.85}
SPEC = {"vth": (1.7, 2.6), "bv_min": 40.0}
SPEC_STATUS = "datasheet_AOI4184"
OUTPUTS = ("vth", "gm", "id_on", "bv")
KNOB_ORDER = ("body_dose", "epi_doping", "oxide_thickness")           # 서로게이트 입력 순서: [도즈, 에피, 산화막]
KNOB_KO = {"도즈": "body_dose", "에피": "epi_doping", "산화막": "oxide_thickness"}
CATEGORY_CODE = {"정상": "normal", "도즈": "dose", "에피": "epi", "산화막": "oxide"}  # Gateway 계약: 분기값은 영문 코드, 한글은 표시명으로 별도 제공
SKIP_TCAD_WHEN_HIGH_CONFIDENCE = True                                    # True: 임계값(AUTO)을 모두 통과한 보정은 TCAD 없이 apply. False: 보정 후보는 전부 tcad_verify (팀 정책이 바뀌면 여기만 바꾼다)
AUTO = {"p_spec_after": 0.99, "p_cause": 0.90, "max_change": 0.15, "core": (0.70, 1.30), "max_p_epi": 0.05}  # 보정을 바로 적용해도 되는 조건 (임시 기준, 에이전트평가로 조정할 것)
POOR_FIT_FACTOR = 4.0                                                  # 가장 잘 맞는 후보의 χ² 가 관측 수 × 이 값을 넘으면 "어떤 상태와도 잘 맞지 않음" (임시 기준)


class RequestError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def _finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _check_common(req, task):
    if not isinstance(req, dict):
        raise RequestError("INVALID_INPUT", "요청은 JSON 객체여야 한다")
    if req.get("schema_version", 1) != 1:
        raise RequestError("INVALID_INPUT", f"schema_version {req.get('schema_version')} 는 지원하지 않는다 (지원: 1)")
    cv = req.get("model_contract_version", CONTRACT_VERSION)
    if cv != CONTRACT_VERSION:
        raise RequestError("UNSUPPORTED_CONTRACT_VERSION", f"model_contract_version '{cv}' 는 지원하지 않는다 (지원: {CONTRACT_VERSION})")
    payload = req.get("input_payload")
    if not isinstance(payload, dict):
        raise RequestError("INVALID_INPUT", "input_payload 가 필요하다")
    return payload


def parse_request(req):
    """surrogate 요청 JSON(dict)을 검증하고 (비율 [도즈, 에피, 산화막], 요청한 출력 목록)을 돌려준다. 잘못되면 RequestError."""
    payload = _check_common(req, "surrogate")
    if not isinstance(payload.get("process_parameters"), dict):
        raise RequestError("INVALID_INPUT", "input_payload.process_parameters 가 필요하다")
    pp = payload["process_parameters"]
    ratios = []
    for k in KNOB_ORDER:
        if k not in pp:
            raise RequestError("INVALID_INPUT", f"process_parameters.{k} 가 없다")
        v = pp[k]
        if not _finite(v) or v <= 0:
            raise RequestError("INVALID_INPUT", f"process_parameters.{k} 는 0 보다 큰 유한한 수여야 한다 ({UNITS_IN[k]})")
        ratios.append(v / BASE[k])
    extra = [k for k in pp if k not in BASE]
    if extra:
        raise RequestError("INVALID_INPUT", f"알 수 없는 공정 변수: {extra} (사용: {list(KNOB_ORDER)})")
    req_out = payload.get("requested_outputs", list(OUTPUTS))
    if not isinstance(req_out, list) or not req_out or any(o not in OUTPUTS for o in req_out):
        raise RequestError("INVALID_INPUT", f"requested_outputs 는 {list(OUTPUTS)} 중에서 골라야 한다")
    return ratios, list(dict.fromkeys(req_out))


def parse_diagnose(req):
    """diagnose 요청을 검증하고 (에이전트 단위의 측정값 dict, 웨이퍼 수, refine 여부)를 돌려준다.
    측정값 단위는 응답의 단위와 같다: vth V, gm uS/um, id_on uA/um, bv V (없으면 null 또는 생략)."""
    payload = _check_common(req, "diagnose")
    m = payload.get("measurements")
    if not isinstance(m, dict):
        raise RequestError("INVALID_INPUT", "input_payload.measurements 가 필요하다")
    extra = [k for k in m if k not in OUTPUTS]
    if extra:
        raise RequestError("INVALID_INPUT", f"알 수 없는 측정 항목: {extra} (사용: {list(OUTPUTS)})")
    meas = {}
    for k in OUTPUTS:
        v = m.get(k)
        if v is None:
            continue
        if not _finite(v) or v <= 0:
            raise RequestError("INVALID_INPUT", f"measurements.{k} 는 0 보다 큰 유한한 수여야 한다 ({UNITS_OUT[k]})")
        meas[k] = float(v) * (1e-6 if k in ("gm", "id_on") else 1.0)
    if not any(k in meas for k in ("vth", "gm", "id_on")):
        raise RequestError("INVALID_INPUT", "vth, gm, id_on 중 하나 이상이 필요하다")
    n = payload.get("n_wafers", 1)
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= 100000:
        raise RequestError("INVALID_INPUT", "n_wafers 는 1 이상 100000 이하의 정수여야 한다")
    refine = payload.get("refine", False)
    if not isinstance(refine, bool):
        raise RequestError("INVALID_INPUT", "refine 은 true 또는 false 여야 한다")
    agent_meas = {"vth": meas.get("vth"), "gm": meas.get("gm"), "id4v": meas.get("id_on"), "bv": meas.get("bv")}
    return agent_meas, n, refine


def physical(pred, i=0):
    """서로게이트 predict 결과(i번째 행)를 계약 단위의 값과 σ 로 바꾼다. 영역 밖(NaN)이면 None."""
    v = {"vth": float(pred["vth"][i]), "gm": float(pred["gm"][i]) * 1e6, "id_on": float(pred["id4v"][i]) * 1e6, "bv": float(pred["bv"][i])}
    if any(math.isnan(x) for x in v.values()):
        return None, None
    s = {"vth": float(pred["sigma_vth"][i]), "gm": v["gm"] * float(pred["sigma_gm"][i]), "id_on": v["id_on"] * float(pred["sigma_id4v"][i]), "bv": float(pred["sigma_bv"][i])}
    return v, s


def violates_spec(vth=None, bv=None):
    """스펙 밖인지 (None 은 판단에 쓰지 않는다)."""
    lo, hi = SPEC["vth"]
    return bool((vth is not None and (vth < lo or vth > hi)) or (bv is not None and bv < SPEC["bv_min"]))


def is_anomaly(v):
    return violates_spec(v["vth"], v["bv"])


def spec_info():
    return {"vth_min": SPEC["vth"][0], "vth_max": SPEC["vth"][1], "bv_min": SPEC["bv_min"], "status": SPEC_STATUS}


def to_physical_knobs(ratios3):
    return {k: float(r) * BASE[k] for k, r in zip(KNOB_ORDER, ratios3)}


def category_code(name_ko):
    """한글 범주 이름("도즈+산화막" 등)을 영문 코드("dose+oxide")로 바꾼다."""
    return "+".join(CATEGORY_CODE[part] for part in name_ko.split("+"))


def action_code(name, n):
    """에이전트의 측정 행동 이름을 영문 코드로 (BV 추가 측정, 웨이퍼 2배, 웨이퍼 4배)."""
    if name.startswith("BV"):
        return "measure_bv"
    return "more_wafers_2x" if f"→ {2 * n}장" in name else ("more_wafers_4x" if f"→ {4 * n}장" in name else "other")


def recommendation_code(rec, n):
    msg = rec["권고"]
    if msg.startswith("추가 측정 불필요"):
        return "none_needed"
    if msg.startswith("추가 측정으로 크게"):
        return "no_improvement"
    for a in rec["행동들"]:
        if a["행동"] in msg:
            return action_code(a["행동"], n)
    return "other"


def confidence_blockers(decision, knobs, comp):
    """보정값을 high_confidence 로 볼 수 없게 만드는 사유 목록 (빈 목록이면 high_confidence). 임계값은 AUTO (임시 기준)."""
    why = []
    if not decision["decided"] or decision["top_probability"] < AUTO["p_cause"]:
        why.append("CAUSE_NOT_CONFIDENT")
    if knobs["epi_doping"]["p_deviated"] > AUTO["max_p_epi"] or comp["warning"]:
        why.append("EPI_DEVIATED_NOT_CONTROLLABLE")
    if comp["p_vth_in_spec_after"] < AUTO["p_spec_after"] or comp["p_bv_in_spec"] < AUTO["p_spec_after"]:
        why.append("SPEC_NOT_ASSURED_AFTER")
    if max(abs(v) for v in comp["changes"].values()) > AUTO["max_change"]:
        why.append("CHANGE_TOO_LARGE")
    after = [knobs["body_dose"]["mean_ratio"] * comp["factors"]["body_dose"], knobs["epi_doping"]["mean_ratio"], knobs["oxide_thickness"]["mean_ratio"] * comp["factors"]["oxide_thickness"]]
    if any(not AUTO["core"][0] <= r <= AUTO["core"][1] for r in after):
        why.append("OUT_OF_CORE")
    return why


def route_compensation(decision, knobs, comp, fit):
    """보정 경로. 정상이면 no_action, 판단 불가(POOR_FIT)면 manual.
    보정 후보가 있으면: 임계값(AUTO) 5개를 모두 통과하면 apply (TCAD 검증을 건너뛰고 적용 후보), 하나라도 못 채우면 tcad_verify (TCAD 로 검증).
    SKIP_TCAD_WHEN_HIGH_CONFIDENCE 를 False 로 하면 보정 후보는 전부 tcad_verify. (경로, 임계값을 못 채운 사유 목록)"""
    if fit["poor_fit"]:
        return "manual", ["POOR_FIT"]
    if decision["decided"] and decision["top_category"] == "normal":     # top_category 는 영문 코드 (category_code 참고)
        return "no_action", []
    blockers = confidence_blockers(decision, knobs, comp)
    if not blockers and SKIP_TCAD_WHEN_HIGH_CONFIDENCE:
        return "apply", []
    return "tcad_verify", blockers


def format_diagnosis(res, fit, refine_info):
    """진단 에이전트 결과(run 의 반환값)를 계약의 result_payload 와 tcad_proposal 로 바꾼다."""
    d, rec, prop = res["진단"], res["다음측정"], res["보정안"]
    knobs = {}
    for k in d["노브"]:
        name = KNOB_KO[k["노브"]]
        b = BASE[name]
        knobs[name] = {"mean": k["평균"] * b, "ci90": [k["구간90"][0] * b, k["구간90"][1] * b], "mean_ratio": k["평균"], "ci90_ratio": list(k["구간90"]), "p_deviated": k["벗어날확률"], "unit": UNITS_IN[name]}
    decided = bool(d["판정됨"]) and not fit["poor_fit"]
    decision = {"decided": decided, "top_category": category_code(d["최다"]), "top_category_label": d["최다"], "top_probability": d["최다확률"],
                "candidates": [{"category": category_code(n), "category_label": n, "probability": p} for n, p in d["후보"]],
                "category_probabilities": {category_code(n): p for n, p in d["범주확률"].items()}, "deviation_threshold_ratio": 0.05, "decision_threshold_probability": 0.70}
    if fit["poor_fit"]:
        decision["reason"] = "POOR_FIT: 측정값이 학습 영역의 어떤 상태와도 잘 맞지 않는다 (학습하지 않은 유형의 이상일 수 있다). 사람이 판단해야 한다."
    nw = d["웨이퍼수"]
    if prop is None:                                                      # 노브 정상(판정됨=정상, poor_fit 아님): 다음측정 권고·보정탐색을 돌리지 않았다
        payload = {"decision": decision, "knobs": knobs, "next_measurement": None,
                   "compensation": {"route": "no_action", "requires_human_approval": False, "epi_doping": "not_controllable", "high_confidence": False, "confidence_blockers": [], "confidence": None},
                   "fit": fit, "refine": refine_info, "spec": spec_info()}
        return payload, None
    nxt = {"recommendation": rec["권고"], "recommendation_code": recommendation_code(rec, nw), "recommendation_label": rec["권고"],
           "actions": [{"action": a["행동"], "action_code": action_code(a["행동"], nw), "action_label": a["행동"], "decidable_fraction": a["판정가능비율"], "expected_top_probability": a["기대최다확률"]} for a in rec["행동들"]]}
    comp = {"changes": {"body_dose": prop["도즈배율"] - 1.0, "oxide_thickness": prop["산화막배율"] - 1.0}, "factors": {"body_dose": prop["도즈배율"], "oxide_thickness": prop["산화막배율"]},
            "epi_doping": "not_controllable", "p_vth_in_spec_before": prop["Vth규격확률_보정전"], "p_vth_in_spec_after": prop["Vth규격확률_보정후"], "p_bv_in_spec": prop["BV규격확률"],
            "p_epi_deviated": prop["에피벗어날확률"], "warning": prop["경고"], "limit_ratio": list(prop["적용범위"]), "based_on": "surrogate"}
    comp["route"], blockers = route_compensation(decision, knobs, comp, fit)
    comp["high_confidence"] = comp["route"] in ("apply", "tcad_verify") and not blockers   # 임계값 5개를 모두 통과
    comp["confidence_blockers"] = blockers
    comp["confidence"] = min(comp["p_vth_in_spec_after"], comp["p_bv_in_spec"], decision["top_probability"]) if comp["route"] in ("apply", "tcad_verify") else None
    comp["threshold_evidence"] = {"p_after_in_spec": min(comp["p_vth_in_spec_after"], comp["p_bv_in_spec"]), "cause_probability": decision["top_probability"], "max_abs_change_ratio": max(abs(v) for v in comp["changes"].values()), "p_epi_deviated": comp["p_epi_deviated"]}
    comp["thresholds"] = {"p_spec_after": AUTO["p_spec_after"], "p_cause": AUTO["p_cause"], "max_change": AUTO["max_change"], "core": list(AUTO["core"]), "max_p_epi": AUTO["max_p_epi"], "status": "provisional"}
    comp["requires_human_approval"] = True                                # 프로젝트 정책: apply 라도 관리자 승인 전에는 자동 변경하지 않는다 (Gateway 계약)
    payload = {"decision": decision, "knobs": knobs, "next_measurement": nxt, "compensation": comp, "fit": fit, "refine": refine_info, "spec": spec_info()}
    cands = []
    for c in res["TCAD확인요청"]:
        cands.append({"name": c["이름"], "process_parameters": to_physical_knobs([c["도즈"], c["에피"], c["산화막"]])})
    if comp["route"] in ("apply", "tcad_verify"):
        comp["target_process_parameters"] = dict(cands[0]["process_parameters"])         # 보정 후 목표 공정값 (사후 평균 상태). apply 면 이 값을 적용한다
    if comp["route"] != "tcad_verify":
        return payload, None
    proposal = {"status": "proposed", "requires_human_approval": True, "verified_by_tcad": False, "high_confidence": comp["high_confidence"], "units": dict(UNITS_IN), "candidates": cands}
    return payload, proposal
