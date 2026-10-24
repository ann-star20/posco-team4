"""TCAD 계산 어댑터: 요청의 process_parameters 를 대량실행.process() 가 받는 행(row)으로 바꾸고, 결과를 응답 단위로 환산한다.

  TCAD_CALC=real  이면 TCAD_배치실행/대량실행/대량실행.py 의 process(row) 로 실제 TCAD 를 돌린다 (샘플 하나 약 30분, 라이선스 필요).
  TCAD_CALC 미설정(기본)이면 실제 TCAD 를 부르지 않고 짧게 흐름만 흉내 낸 가짜 결과를 돌려준다 (시험용, 기본값을 안전하게 유지).
"""
import importlib.util
import itertools
import os
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BULK_RUN_PY = ROOT / "TCAD_배치실행" / "대량실행" / "대량실행.py"
BASE = {"body_dose": 7.7e12, "epi_doping": 1.7e16, "oxide_thickness": 0.06}      # 5-1 기준값
_NUMBER_START = 900001          # ponytail: 현재 배치(최대 182번)와 안 겹치게 멀찍이 떼어 둔 고정 오프셋. 배치가 더 커지면 올릴 것.
_real_mod, _real_lock = None, threading.Lock()


class Cancelled(Exception):
    """진행 중 작업이 취소 요청을 받았을 때 (가짜 계산만 실제로 끊을 수 있다)."""


def _load_real():
    global _real_mod
    with _real_lock:
        if _real_mod is None:
            spec = importlib.util.spec_from_file_location("대량실행_실제", BULK_RUN_PY)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
            _real_mod = m
    return _real_mod


def ratios(process_parameters):
    """공정값 -> 기준값 대비 비율 (dose, epi, tox 순서)."""
    return {"dose": process_parameters["body_dose"] / BASE["body_dose"],
            "epi": process_parameters["epi_doping"] / BASE["epi_doping"],
            "tox": process_parameters["oxide_thickness"] / BASE["oxide_thickness"]}


def make_row(process_parameters, requested_outputs, number):
    r = ratios(process_parameters)
    return {"번호": number, "층": "서비스", "확장축": "tcad_verify", "바디도즈비율": r["dose"], "에피도핑비율": r["epi"],
            "산화막비율": r["tox"], "스윕(V)": "4", "BV계산": "Y" if "bv" in requested_outputs else "N"}


def to_result_payload(r, requested_outputs):
    out = {}
    if "vth" in requested_outputs:
        out["vth"] = r.get("vth")
    if "gm" in requested_outputs:
        out["gm"] = r["gm"] * 1e6 if r.get("gm") is not None else None
    if "id_on" in requested_outputs:
        out["id_on"] = r["id4v"] * 1e6 if r.get("id4v") is not None else None
    if "bv" in requested_outputs:
        out["bv"] = (r.get("bvt_levels") or {}).get("1e-09")
    return out


def _warnings(r, requested_outputs):
    if "bv" not in requested_outputs:
        return ["BV_SKIPPED"]
    if r.get("bv_skipped"):
        return ["BV_SKIPPED", "B4_LEAKAGE"]
    return []


def to_metadata(r, requested_outputs):
    attempts = r.get("시도") or []
    return {"units": {"vth": "V", "gm": "uS/um", "id_on": "uA/um", "bv": "V"},
            "id_conditions": {"vgs_v": float(r.get("sweep", 4.0)), "vds_v": 0.1, "temperature_c": 26.85},
            "bv_criterion": "1e-9 A/um", "leakage_a_per_um": r.get("i_leak"),
            "seconds_iv": r.get("seconds"), "seconds_bv": r.get("bvt_seconds"),
            "attempts": len(attempts) or 1, "mesh_factor": (attempts[-1]["격자"] if attempts else 1.0),
            "sweep_v": float(r.get("sweep", 4.0)), "warnings": _warnings(r, requested_outputs)}


def prediction_error(result_payload, predicted_outputs):
    if not predicted_outputs:
        return None
    return {k: round(predicted_outputs[k] - v, 6) for k, v in result_payload.items() if k in predicted_outputs and v is not None}


# ---------------------------------------------------------------- 가짜 계산 (시험용)
def fake_calc(row, report_stage, is_cancelled):
    report_stage("iv", 0)
    time.sleep(0.3)
    if is_cancelled():
        raise Cancelled()
    jitter = (row["번호"] % 1000) / 1e6                                    # 결과를 약간씩 다르게 (실제 계산을 흉내만 냄, 값은 의미 없음)
    success = os.environ.get("TCAD_MOCK_SUCCESS", "true").lower() != "false"
    vth = (2.2583 if success else 1.2) + jitter                            # 불량: vth 규격(1.7~2.6V) 밖
    r = {"status": "ok", "vth": vth, "gm": 4.46e-6, "id4v": 5.15e-6, "i_leak": 5.1e-16,
         "seconds": 1, "sweep": float(row["스윕(V)"]), "시도": [{"스윕": float(row["스윕(V)"]), "격자": 1.0}]}
    if row["BV계산"] == "Y":
        report_stage("bv", 1)
        time.sleep(0.3)
        if is_cancelled():
            raise Cancelled()
        bv = (41.117 if success else 25.0) + jitter * 5                   # 불량: bv 규격(40V 이상) 밖
        r["bvt_levels"] = {"1e-09": bv}
        r["bvt_seconds"] = 1
    return r


# ---------------------------------------------------------------- 실제 계산
def real_calc(row, report_stage, is_cancelled):
    """process(row) 는 끊을 콜백이 없다 (대량실행.py 를 고치지 않기로 했다). IV 가 끝나는 시점을 모르므로 예상 시간(8분) 뒤에
    stage 를 bv 로 올린다 (근사치). is_cancelled 도 실제로는 확인만 하고 못 끊는다. ponytail: 실제 중단/정확한 진행률은 대량실행.py 쪽 콜백이 있어야 가능."""
    report_stage("iv", 0)
    timer = None
    if row["BV계산"] == "Y":
        timer = threading.Timer(480, report_stage, args=("bv", 480))
        timer.daemon = True
        timer.start()
    try:
        return _load_real().process(row)
    finally:
        if timer:
            timer.cancel()


def get_calc_fn():
    return real_calc if os.environ.get("TCAD_CALC") == "real" else fake_calc


_counter = itertools.count(_NUMBER_START)


def alloc_number():
    return next(_counter)


def set_number_floor(n):
    """저장된 작업 중 가장 큰 번호 + 1 부터 다시 번호를 매긴다 (재시작 후에도 안 겹치게)."""
    global _counter
    _counter = itertools.count(max(n + 1, _NUMBER_START))
