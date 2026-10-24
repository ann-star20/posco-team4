"""TCAD 서비스 시험 (명세 7번의 8개 시험 중 실제 TCAD 가 필요한 2, 8번은 제외/표시). 서버를 임시 포트로 띄우고 가짜 계산(TCAD_CALC 기본값)으로 흐름만 확인한다.
반드시 TCAD_CALC 를 real 로 두지 말 것: 지금 이 PC 에서 실제 TCAD 배치가 돌고 있으면 같은 라이선스/CPU 를 다투게 된다.
  python 시험.py
"""
import json
import os
import time
import urllib.error
import urllib.request

assert os.environ.get("TCAD_CALC") != "real", "이 시험은 가짜 계산으로만 돌린다 (TCAD_CALC=real 이면 실제 TCAD 를 호출한다)"

import 서비스 as svc

BASE_PP = {"body_dose": 7.7e12, "epi_doping": 1.7e16, "oxide_thickness": 0.06}


def call(port, path, body=None, method=None, headers=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method or ("POST" if data is not None else "GET"),
                                  headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def verify(pp=BASE_PP, rid="t-1", **extra):
    return {"request_id": rid, "job_id": "j1", "process_parameters": pp, **extra}


def poll(port, rid, timeout=5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        _, r = call(port, f"/api/v1/tcad/jobs/{rid}")
        if r["status"] in ("succeeded", "failed", "cancelled"):
            return r
        time.sleep(0.05)
    return r


def main():
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(("통과  " if cond else "실패  ") + name + (f"  ({detail})" if detail else ""))

    state = (svc.HERE / "상태" / "시험_작업목록.json")
    state.unlink(missing_ok=True)
    service = svc.Service(state_file=state, workers=1)
    srv = svc.make_server(0, service, host="127.0.0.1")
    port = srv.server_address[1]
    import threading
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    # 1. health/ready
    c, r = call(port, "/health/ready")
    check("1. health/ready", c == 200 and r["status"] == "ready")

    print("건너뜀  2. 기준값 전체 계산(IV+BV)이 기존 값과 같은지 -- 실제 TCAD 필요, 배치가 끝난 뒤 TCAD_CALC=real 로 따로 확인")

    # 3. 같은 request_id 재요청
    c1, r1 = call(port, "/api/v1/tcad/verify", verify(rid="t-idem"))
    c2, r2 = call(port, "/api/v1/tcad/verify", verify(rid="t-idem"))
    check("3. 같은 request_id 재요청은 200 이고 새 작업을 안 만든다", c1 == 202 and c2 == 200 and r1["request_id"] == r2["request_id"])
    poll(port, "t-idem")

    # 4. 범위 밖
    c, r = call(port, "/api/v1/tcad/verify", verify(pp={**BASE_PP, "body_dose": 3.2e13}, rid="t-oor"))
    _, nf = call(port, "/api/v1/tcad/jobs/t-oor")
    check("4. 범위 밖은 422 OUT_OF_RANGE 이고 큐에 안 들어간다", c == 422 and r["error_code"] == "OUT_OF_RANGE" and nf["error_code"] == "NOT_FOUND")

    # 5. 취소 (대기 중)
    call(port, "/api/v1/tcad/verify", verify(rid="t-busy"))                       # 워커 1개를 바쁘게 만든다
    c, r = call(port, "/api/v1/tcad/verify", verify(rid="t-cancel"))
    cc, cr = call(port, "/api/v1/tcad/jobs/t-cancel/cancel", {})
    check("5. 대기 중 작업 취소", c == 202 and r["status"] == "queued" and cc == 200 and cr["status"] == "cancelled")
    poll(port, "t-busy")

    # 6. 재시작 후 작업 목록 보존 (JobStore 수준에서 확인: running -> queued 로 되돌림)
    state2 = svc.JobStore(state)
    before = {rid: j["status"] for rid, j in service.store.jobs.items()}
    after = {rid: j["status"] for rid, j in state2.jobs.items()}
    check("6. 재시작해도 작업 목록이 보존된다 (running 은 queued 로)", before.keys() == after.keys() and all(v != "running" for v in after.values()))

    # 7. bv 빼고 요청
    c, r = call(port, "/api/v1/tcad/verify", verify(rid="t-nobv", requested_outputs=["vth", "gm", "id_on"]))
    res = poll(port, "t-nobv")
    check("7. bv 를 빼면 결과에 bv 가 없고 금방 끝난다", c == 202 and res["status"] == "succeeded" and "bv" not in res["result_payload"] and "BV_SKIPPED" in res["metadata"]["warnings"])

    print("건너뜀  8. 모델서비스 tcad_proposal 의 실제 후보로 요청 -- 모델 서비스를 같이 띄워야 하는 통합 시험, 여기서는 생략")

    print("전체 통과" if ok else "일부 실패")
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if main() else 1)
