"""fake 서버(8401)의 작업목록.json을 폴링해서 접수/완료를 stdout에 한 줄씩 찍는다."""
import json
import time
from pathlib import Path

STATE = Path(__file__).resolve().parent / "상태" / "작업목록.json"


def load():
    try:
        return json.loads(STATE.read_text(encoding="utf-8")).get("jobs", {})
    except Exception:
        return {}


def fmt_payload(payload):
    if not payload:
        return ""
    parts = []
    for k, v in payload.items():
        parts.append(f"{k}={v:.4g}" if isinstance(v, (int, float)) else f"{k}={v}")
    return ", ".join(parts)


seen = {rid: j.get("status") for rid, j in load().items()}

while True:
    time.sleep(2)
    for rid, j in load().items():
        st = j.get("status")
        prev = seen.get(rid)
        if prev == st:
            continue
        if prev is None and st in ("queued", "running"):
            print(f"[접수] {rid} 요청 들어옴 (status={st})", flush=True)
        elif st == "succeeded":
            print(f"[완료] {rid} 성공: {fmt_payload(j.get('result_payload'))}", flush=True)
        elif st == "failed":
            print(f"[완료] {rid} 실패: {j.get('error_code')} {j.get('error_message')}", flush=True)
        elif st == "cancelled":
            print(f"[완료] {rid} 취소됨", flush=True)
        seen[rid] = st
