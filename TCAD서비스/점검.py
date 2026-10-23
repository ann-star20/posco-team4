"""TCAD 서비스 점검: 떠 있는지, 막힌 작업이 있는지, 실제로 계산이 되는지 확인한다.
  python 점검.py          # 빠른 점검만: health, 큐에 멈춰있거나 너무 오래 걸리는 작업, Silvaco 프로세스 생존 여부
  python 점검.py --full   # 기준값으로 새 검증 요청을 넣고 끝까지 지켜본다 (실제 계산, 약 20~30분)

환경변수: TCAD_URL(기본 http://127.0.0.1:8400), TCAD_SERVICE_TOKEN(토큰을 쓰면 필요), WARN_MINUTES(경고 기준, 기본 40)
"""
import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
URL = os.environ.get("TCAD_URL", "http://127.0.0.1:8400")
TOKEN = os.environ.get("TCAD_SERVICE_TOKEN")
STATE_FILE = Path(os.environ.get("TCAD_STATE_FILE", HERE / "상태" / "작업목록.json"))
WARN_MINUTES = float(os.environ.get("WARN_MINUTES", 40))                   # 기준값 real 계산 실측 약 20.5분보다 넉넉히 둔 경고선
BASE = {"body_dose": 7.7e12, "epi_doping": 1.7e16, "oxide_thickness": 0.06}
EXPECTED = {"vth": 2.25829, "gm": 4.573, "id_on": 5.207, "bv": 41.117}      # 2026-10-22 real 모드로 확인된 기준값 결과
TOL = {"vth": 0.02, "gm": 0.2, "id_on": 0.2, "bv": 0.5}                     # 허용 오차 (절대값)


def _headers(extra=None):
    h = {"X-Fab-Token": TOKEN} if TOKEN else {}
    h.update(extra or {})
    return h


def _get(path):
    with urllib.request.urlopen(urllib.request.Request(URL + path, headers=_headers()), timeout=10) as r:
        return r.status, json.load(r)


def _post(path, body):
    req = urllib.request.Request(URL + path, data=json.dumps(body).encode("utf-8"), headers=_headers({"Content-Type": "application/json"}), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def check_health():
    try:
        _, h = _get("/health/ready")
    except Exception as e:
        print(f"[실패] /health/ready 접속 안 됨: {e}")
        return False
    ok = h.get("status") == "ready" and h.get("calc_mode") == "real" and h.get("dbascii_found")
    print(f"[{'통과' if ok else '실패'}] health/ready: {h}")
    return bool(ok)


def check_stuck_jobs():
    if not STATE_FILE.exists():
        print("[정보] 작업목록 파일이 없다 (아직 요청이 없었다)")
        return True
    jobs = json.loads(STATE_FILE.read_text(encoding="utf-8")).get("jobs", {})
    now = datetime.now().astimezone()
    running = [j for j in jobs.values() if j.get("status") in ("queued", "running")]
    if not running:
        print("[통과] 멈춰있거나 실행 중인 작업 없음")
        return True
    ok = True
    for j in running:
        started = datetime.fromisoformat(j.get("started_at") or j["created_at"])
        mins = (now - started).total_seconds() / 60
        flag = mins > WARN_MINUTES
        ok = ok and not flag
        stage = (j.get("progress") or {}).get("stage")
        print(f"[{'경고' if flag else '정보'}] {j['request_id']} 상태={j['status']} stage={stage} {mins:.1f}분 경과 (경고선 {WARN_MINUTES:.0f}분, 기준값 실측 약 20.5분)")
    return ok


def check_processes():
    try:
        out = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=10).stdout
    except Exception as e:
        print(f"[정보] 프로세스 목록을 못 읽었다: {e}")
        return True
    names = [n for n in ("atlas.exe", "atlas2.exe", "dbascii.exe") if n in out]
    print(f"[정보] 실행 중인 Silvaco 프로세스: {names or '없음'}")
    return True


def submit_and_watch(poll_seconds=30, max_minutes=40):
    rid = f"selfcheck-{uuid.uuid4()}"
    status, r = _post("/api/v1/tcad/verify", {"request_id": rid, "process_parameters": BASE, "requested_outputs": list(EXPECTED), "predicted_outputs": EXPECTED})
    print(f"[정보] 접수 {status}: {r}")
    if status not in (200, 202):
        print("[실패] 접수 자체가 안 됨")
        return False
    t0 = time.time()
    while True:
        elapsed_min = (time.time() - t0) / 60
        _, r = _get(f"/api/v1/tcad/jobs/{rid}")
        st = r.get("status")
        print(f"[정보] {elapsed_min:.1f}분 경과, 상태={st}, progress={r.get('progress')}")
        if st == "succeeded":
            break
        if st in ("failed", "cancelled"):
            print(f"[실패] 작업이 {st} 로 끝났다: {r.get('error_code')} {r.get('error_message')}")
            return False
        if elapsed_min > max_minutes:
            print(f"[실패] {max_minutes}분 지나도 안 끝났다 (기준값 실측 약 20.5분이어야 한다)")
            return False
        time.sleep(poll_seconds)
    out = r["result_payload"]
    bad = [k for k, v in EXPECTED.items() if abs(out[k] - v) > TOL[k]]
    ok = not bad
    print(f"[{'통과' if ok else '실패'}] 결과 {out} (기대 {EXPECTED}, 오차 기준 {TOL})" + (f", 벗어난 값: {bad}" if bad else ""))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="기준값으로 실제 검증 요청을 새로 넣고 끝까지 지켜본다 (약 20~30분)")
    a = ap.parse_args()
    results = [check_health(), check_stuck_jobs(), check_processes()]
    if a.full:
        results.append(submit_and_watch())
    print("== 전체 판정:", "모두 통과" if all(results) else "실패 항목 있음")


if __name__ == "__main__":
    main()
