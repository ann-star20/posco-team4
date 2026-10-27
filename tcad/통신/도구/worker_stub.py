"""Worker 대역: Worker 없이 계약대로 서비스를 호출해 본다 (재시도, 제한 시간, 오류 구분 포함). 표준 라이브러리만 쓴다.
  python3 worker_stub.py [--url http://127.0.0.1:8300] [--token 영문토큰] [--timeout 90] [--retries 3] [--skip-diagnose]
Worker 를 만드는 쪽은 이 파일의 call() 을 그대로 참고하면 된다.
종료 코드 0 = 모든 시험이 기대대로.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid

BASE = {"body_dose": 7.7e12, "epi_doping": 1.7e16, "oxide_thickness": 0.06}


def call(url, body, token=None, timeout=90, retries=3):
    """계약대로 호출한다. 같은 request_id 로 재시도하므로 서비스가 같은 응답을 돌려준다.
    반환: (HTTP 상태, 응답 dict, 걸린 초, 시도 횟수). 네트워크 오류와 5xx 만 재시도하고, 400 대(요청 오류)와 200+failed(영역 밖 등)는 재시도하지 않는다."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Fab-Token"] = token
    data = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(1, retries + 1):
        t0 = time.time()
        try:
            req = urllib.request.Request(url + "/api/v1/predict", data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode("utf-8")), time.time() - t0, attempt
        except urllib.error.HTTPError as e:
            out = json.loads(e.read().decode("utf-8"))
            if e.code < 500:
                return e.code, out, time.time() - t0, attempt
            last = (e.code, out, time.time() - t0, attempt)
        except Exception as e:                                             # 연결 거부, 시간 초과 등
            last = (0, {"status": "failed", "error": {"code": "NETWORK", "message": f"{type(e).__name__}: {e}"}}, time.time() - t0, attempt)
        time.sleep(min(2 ** attempt, 10))
    return last


def surrogate(pp, **kw):
    return {"schema_version": 1, "task_type": "surrogate", "request_id": str(uuid.uuid4()), "job_id": str(uuid.uuid4()), "run_id": str(uuid.uuid4()), "lot_id": "LOT-STUB", "attempt": 1,
            "model_contract_version": "fab-ml-v1", "surrogate_mode": "prod", "input_payload": {"process_parameters": pp, "requested_outputs": ["vth", "gm", "id_on", "bv"]}, **kw}


def diagnose(meas, n_wafers, **extra):
    return {"schema_version": 1, "task_type": "diagnose", "request_id": str(uuid.uuid4()), "job_id": str(uuid.uuid4()), "run_id": str(uuid.uuid4()), "lot_id": "LOT-STUB", "attempt": 1,
            "model_contract_version": "fab-ml-v1", "surrogate_mode": "prod", "input_payload": {"measurements": meas, "n_wafers": n_wafers, **extra}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8300")
    ap.add_argument("--token", default=None)
    ap.add_argument("--timeout", type=float, default=90)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--skip-diagnose", action="store_true")
    a = ap.parse_args()
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(("통과  " if cond else "실패  ") + name + (f"  ({detail})" if detail else ""))

    try:
        with urllib.request.urlopen(a.url + "/health", timeout=10) as r:
            h = json.loads(r.read().decode("utf-8"))
        check("/health", h.get("status") == "ok", f"모델 {h.get('model_version')}, 작업 {h.get('tasks')}, 인증 {'필요' if h.get('auth_required') else '불필요'}")
    except Exception as e:
        print(f"실패  /health  ({type(e).__name__}: {e})\n      → 서비스가 켜져 있는지 확인: python3 run_service.py")
        return 1
    c, r, s, n = call(a.url, surrogate(BASE), a.token, a.timeout, a.retries)
    check("surrogate 기준값", c == 200 and r.get("status") == "succeeded", f"{s * 1000:.0f} ms, 값 { {k: round(v, 3) for k, v in (r.get('result_payload') or {}).items()} }")
    if c == 200 and r.get("status") == "succeeded":
        check("id_conditions 가 TCAD 조건 (Vgs 4 V, Vds 0.1 V)", r["metadata"]["id_conditions"]["vds_v"] == 0.1 and r["metadata"]["id_conditions"]["vgs_v"] == 4.0)
        check("요청 ID 가 그대로 돌아온다", r["request_id"] and r["job_id"])
    c, r, s, n = call(a.url, surrogate({"body_dose": 1.2e13, "epi_doping": 2.5e15, "oxide_thickness": 5.2}), a.token, a.timeout, a.retries)
    check("영역 밖 입력은 200 + failed + OUT_OF_DOMAIN (재시도하지 않음)", c == 200 and r.get("status") == "failed" and r["error"]["code"] == "OUT_OF_DOMAIN" and n == 1)
    c, r, s, n = call(a.url, surrogate({"body_dose": -1, "epi_doping": 1.7e16, "oxide_thickness": 0.06}), a.token, a.timeout, a.retries)
    check("잘못된 요청은 400 (재시도하지 않음)", c == 400 and n == 1)
    body = surrogate(BASE)
    c1, r1, _, _ = call(a.url, body, a.token, a.timeout, a.retries)
    c2, r2, _, _ = call(a.url, body, a.token, a.timeout, a.retries)
    check("같은 request_id 재호출은 같은 응답", r1 == r2)
    if not a.skip_diagnose and "diagnose" in (h.get("tasks") or []):
        meas = {"vth": 2.874, "gm": 3.767, "id_on": 3.468, "bv": 44.186}            # 산화막이 25 % 두꺼워진 가상 로트의 측정값 (서로게이트로 만든 일관된 값). 보정량이 커서 TCAD 확인(tcad_verify)으로 가는 예
        c, r, s, n = call(a.url, diagnose(meas, 25), a.token, a.timeout, a.retries)
        pl = (r.get("result_payload") or {})
        d = pl.get("decision", {})
        check("diagnose 응답", c == 200 and r.get("status") == "succeeded", f"{s:.1f}초, 판정 {d.get('top_category')} {d.get('top_probability', 0):.2f}, decided {d.get('decided')}, 경고 {r.get('metadata', {}).get('warnings')}")
        route = (pl.get("compensation") or {}).get("route")
        check("diagnose 가 보정 경로를 알린다: tcad_verify 면 tcad_proposal 이 있고, 아니면 없다 (POOR_FIT 아님)", route in ("apply", "tcad_verify", "no_action", "manual") and (r.get("tcad_proposal") is not None) == (route == "tcad_verify") and "POOR_FIT" not in r.get("metadata", {}).get("warnings", []), f"route {route}, 사유 {(pl.get('compensation') or {}).get('confidence_blockers')}")
        check(f"diagnose 가 제한 시간({a.timeout:.0f}초) 안에 끝난다", s < a.timeout, f"{s:.1f}초 (이 값을 Worker 제한 시간 정하는 데 쓰라)")
    print("== 전체 판정:", "모두 통과" if ok else "실패 항목 있음")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
