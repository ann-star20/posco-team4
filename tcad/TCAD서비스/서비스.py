"""TCAD 검증 서비스: Gateway 가 호출하는 HTTP 서비스 (통신/TCAD_서비스_연결명세.md). 표준 라이브러리 + NumPy(Domain) 만 쓴다.
샘플 하나가 약 30분 걸리므로 접수 즉시 응답하고(202), 결과는 나중에 조회(폴링)한다.

  POST http://0.0.0.0:8400/api/v1/tcad/verify                검증 요청 접수
  GET  http://0.0.0.0:8400/api/v1/tcad/jobs/{request_id}      상태·결과 조회
  POST http://0.0.0.0:8400/api/v1/tcad/jobs/{request_id}/cancel  취소
  GET  http://0.0.0.0:8400/health/ready                      준비 점검

  python 서비스.py                              # 서버 시작 (0.0.0.0:8400, Gateway 가 접속하므로 127.0.0.1 전용이 아니다)
  python 서비스.py --port 8401 --token 비밀값       # 토큰을 쓰면 헤더 X-Fab-Token 이 같아야 한다 (환경변수 TCAD_SERVICE_TOKEN 도 가능)
  python 서비스.py --port 8401 --success false      # fake 모드에서 불량(규격 밖) 케이스를 돌려준다 (기본 true=정상)

환경변수: TCAD_WORKERS(동시 실행 수, 기본 3), TCAD_QUEUE_MAX(큐 최대 길이, 기본 50), TCAD_CALC(real 이면 실제 TCAD, 기본은 가짜 계산),
          DBASCII(실행 파일 경로, /health/ready 점검용), TCAD_STATE_FILE(작업 목록 저장 파일 경로)
"""
import argparse
import hmac
import importlib.util
import json
import logging
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import 계산 as calc

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
FINAL = ROOT / "최종ML"
DEFAULT_DBASCII = r"C:\sedatools\lib\deckbuild\5.0.10.R\x86_64-windows\dbascii.exe"
LOG = logging.getLogger("tcad-service")
SERVICE_VERSION = "1.0.0"
MAX_BODY = 1_000_000
TOP_FIELDS = {"request_id", "job_id", "run_id", "lot_id", "model_contract_version", "source",
              "process_parameters", "requested_outputs", "predicted_outputs", "options"}
PP_FIELDS = {"body_dose", "epi_doping", "oxide_thickness"}
OUTPUTS = ("vth", "gm", "id_on", "bv")


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class RequestError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


def load_domain():
    spec = importlib.util.spec_from_file_location("이단GP_영역", FINAL / "2단_GP.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    data = json.loads((FINAL / "모델" / "영역.json").read_text(encoding="utf-8"))
    return m.Domain(data)


def validate(req, domain):
    if not isinstance(req, dict):
        raise RequestError("INVALID_INPUT", "요청은 JSON 객체여야 한다")
    extra = set(req) - TOP_FIELDS
    if extra:
        raise RequestError("INVALID_INPUT", f"알 수 없는 필드: {sorted(extra)}")
    if not isinstance(req.get("request_id"), str) or not req["request_id"]:
        raise RequestError("INVALID_INPUT", "request_id 가 필요하다")
    pp = req.get("process_parameters")
    if not isinstance(pp, dict):
        raise RequestError("INVALID_INPUT", "process_parameters 가 필요하다")
    missing, extra_pp = PP_FIELDS - set(pp), set(pp) - PP_FIELDS
    if missing or extra_pp:
        raise RequestError("INVALID_INPUT", f"process_parameters 는 {sorted(PP_FIELDS)} 만 받는다 (누락 {sorted(missing)}, 알수없음 {sorted(extra_pp)})")
    for k in PP_FIELDS:
        v = pp[k]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            raise RequestError("INVALID_INPUT", f"{k} 는 양수여야 한다")
    wanted = req.get("requested_outputs", list(OUTPUTS))
    if not isinstance(wanted, list) or not wanted or set(wanted) - set(OUTPUTS):
        raise RequestError("INVALID_INPUT", f"requested_outputs 는 {sorted(OUTPUTS)} 의 부분집합이어야 한다")
    r = calc.ratios(pp)
    if not bool(domain([[r["dose"], r["epi"], r["tox"]]])[0]):
        raise RequestError("OUT_OF_RANGE", "공정값이 TCAD 검증 범위 밖이다")
    return wanted


# ---------------------------------------------------------------- 작업 저장소 (재시작해도 queued/running 을 잃지 않음)
class JobStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.jobs = {}
        self.futures = {}          # 메모리에만: request_id -> Future (취소용)
        self._load()

    def _load(self):
        if self.path.exists():
            self.jobs = json.loads(self.path.read_text(encoding="utf-8")).get("jobs", {})
            for job in self.jobs.values():
                if job["status"] == "running":                 # 5-3: 재시작 후 running 은 queued 로 되돌린다
                    job["status"], job["progress"] = "queued", None
            self._save()
        calc.set_number_floor(max((j.get("_number", 0) for j in self.jobs.values()), default=0))

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"jobs": self.jobs}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, rid):
        with self.lock:
            return self.jobs.get(rid)

    def put(self, job):
        with self.lock:
            self.jobs[job["request_id"]] = job
            self._save()

    def queued_and_running(self):
        with self.lock:
            return [j for j in self.jobs.values() if j["status"] in ("queued", "running")]

    def queue_position(self, rid):
        with self.lock:
            queued = sorted((j for j in self.jobs.values() if j["status"] == "queued"), key=lambda j: j["created_at"])
            for i, j in enumerate(queued, 1):
                if j["request_id"] == rid:
                    return i
            return None

    def set_future(self, rid, fut):
        with self.lock:
            self.futures[rid] = fut

    def pop_future(self, rid):
        with self.lock:
            return self.futures.pop(rid, None)


# ---------------------------------------------------------------- 서비스
class Service:
    def __init__(self, state_file=None, workers=None, queue_max=None, token=None):
        self.token = token
        self.workers = workers or int(os.environ.get("TCAD_WORKERS", "3"))
        self.queue_max = queue_max or int(os.environ.get("TCAD_QUEUE_MAX", "50"))
        self.domain = load_domain()
        self.store = JobStore(state_file or os.environ.get("TCAD_STATE_FILE") or (HERE / "상태" / "작업목록.json"))
        self.pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="tcad-worker")
        for job in sorted(self.store.queued_and_running(), key=lambda j: j["created_at"]):   # 재시작 시 대기 중이던 작업을 다시 큐에 올린다
            self._submit(job["request_id"])

    def _submit(self, rid):
        fut = self.pool.submit(self._run_job, rid)
        self.store.set_future(rid, fut)

    def ready(self):
        jobs = self.store.queued_and_running()
        return {"status": "ready", "service_version": SERVICE_VERSION, "domain_loaded": True,
                "dbascii_found": Path(os.environ.get("DBASCII", DEFAULT_DBASCII)).exists(),
                "calc_mode": os.environ.get("TCAD_CALC", "fake"),
                "queue": {"workers": self.workers, "queue_max": self.queue_max,
                          "queued": sum(j["status"] == "queued" for j in jobs), "running": sum(j["status"] == "running" for j in jobs)}}

    # -------------------------------------------------------- 접수
    def verify(self, req):
        try:
            wanted = validate(req, self.domain)
        except RequestError as e:
            code = {"INVALID_INPUT": 400, "OUT_OF_RANGE": 422}[e.code]
            return code, {"request_id": req.get("request_id") if isinstance(req, dict) else None, "status": "failed",
                           "error_code": e.code, "error_message": e.message, "result_payload": None}
        rid = req["request_id"]
        existing = self.store.get(rid)
        if existing is not None:
            return 200, self._view(existing)                   # 3번 시험: 같은 request_id 는 다시 계산하지 않는다
        if len(self.store.queued_and_running()) >= self.queue_max:
            return 429, {"request_id": rid, "status": "failed", "error_code": "QUEUE_FULL", "error_message": "대기열이 가득 찼다", "result_payload": None}
        options = {"priority": "normal", "timeout_seconds": 5400, **(req.get("options") or {})}
        job = {"request_id": rid, "job_id": req.get("job_id"), "run_id": req.get("run_id"), "lot_id": req.get("lot_id"),
               "process_parameters": req["process_parameters"], "requested_outputs": wanted, "predicted_outputs": req.get("predicted_outputs"),
               "options": options, "status": "queued", "created_at": now_iso(), "_number": calc.alloc_number(), "cancel_requested": False}
        self.store.put(job)
        view = self._view(dict(job))          # 워커가 바로 집어가 상태를 바꾸기 전에, 접수 시점 상태로 스냅샷을 떠 둔다
        self._submit(rid)
        return 202, view

    def job(self, rid):
        job = self.store.get(rid)
        return (200, self._view(job)) if job else (404, {"status": "failed", "error_code": "NOT_FOUND", "error_message": rid})

    def cancel(self, rid):
        job = self.store.get(rid)
        if job is None:
            return 404, {"status": "failed", "error_code": "NOT_FOUND", "error_message": rid}
        if job["status"] == "queued":
            fut = self.store.pop_future(rid)
            if fut is not None and fut.cancel():
                job.update(status="cancelled", cancelled_at=now_iso())
                self.store.put(job)
                return 200, self._view(job)
        if job["status"] == "running":                            # 실제 계산은 못 끊는다 (계산.real_calc 참고); 가짜 계산은 다음 단계에서 멈춘다
            job["cancel_requested"] = True
            self.store.put(job)
        return 200, self._view(job)

    def _view(self, job):
        rid, status = job["request_id"], job["status"]
        base = {"request_id": rid, "job_id": job.get("job_id")}
        if status == "queued":
            return {**base, "status": "queued", "queue_position": self.store.queue_position(rid),
                    "estimated_seconds": job["options"]["timeout_seconds"], "accepted_at": job["created_at"]}
        if status == "running":
            return {**base, "status": "running", "progress": job.get("progress"), "started_at": job.get("started_at")}
        if status == "succeeded":
            out = {**base, "status": "succeeded", "result_payload": job["result_payload"], "metadata": job["metadata"], "finished_at": job["finished_at"]}
            if job.get("prediction_error") is not None:
                out["prediction_error"] = job["prediction_error"]
            return out
        if status == "failed":
            return {**base, "status": "failed", "error_code": job["error_code"], "error_message": job["error_message"],
                    "result_payload": None, "metadata": job.get("metadata", {}), "finished_at": job.get("finished_at")}
        return {**base, "status": "cancelled", "cancelled_at": job.get("cancelled_at")}

    # -------------------------------------------------------- 실행 (워커 스레드)
    def _run_job(self, rid):
        job = self.store.get(rid)
        if job is None or job["status"] == "cancelled":
            return
        job["status"], job["started_at"] = "running", now_iso()
        job["progress"] = {"stage": "iv", "stages": [{"stage": "iv", "status": "running", "seconds": 0}]}
        self.store.put(job)

        def report_stage(stage, seconds):
            j = self.store.get(rid)
            if j is None or j["status"] != "running":
                return
            stages = j["progress"]["stages"]
            if stage == "bv":
                for s in stages:
                    if s["stage"] == "iv":
                        s["status"] = "succeeded"
                stages = stages + [{"stage": "bv", "status": "running", "seconds": seconds}]
            j["progress"] = {"stage": stage, "stages": stages}
            self.store.put(j)

        def is_cancelled():
            j = self.store.get(rid)
            return bool(j and j.get("cancel_requested"))

        row = calc.make_row(job["process_parameters"], job["requested_outputs"], job["_number"])
        try:
            r = calc.get_calc_fn()(row, report_stage, is_cancelled)
        except calc.Cancelled:
            job = self.store.get(rid)
            job.update(status="cancelled", cancelled_at=now_iso(), progress=None)
            self.store.put(job)
            return
        except Exception as e:
            code = "TCAD_LICENSE_UNAVAILABLE" if "license" in str(e).lower() else "INTERNAL"
            self._finish_failed(rid, code, f"{type(e).__name__}: {e}")
            return
        if r.get("status") != "ok":
            attempts = len(r.get("시도", [])) or 1
            self._finish_failed(rid, "TCAD_NO_CONVERGENCE", f"Vth 를 구하지 못했다 (재시도 {max(attempts - 1, 0)}회 후)",
                                 extra_meta={"attempts": attempts, "seconds_iv": r.get("seconds")})
            return
        job = self.store.get(rid)
        wanted = job["requested_outputs"]
        payload = calc.to_result_payload(r, wanted)
        job.update(status="succeeded", result_payload=payload, metadata=calc.to_metadata(r, wanted), finished_at=now_iso(), progress=None)
        pe = calc.prediction_error(payload, job.get("predicted_outputs"))
        if pe is not None:
            job["prediction_error"] = pe
        self.store.put(job)

    def _finish_failed(self, rid, code, message, extra_meta=None):
        job = self.store.get(rid)
        job.update(status="failed", error_code=code, error_message=message, result_payload=None,
                   metadata=extra_meta or {}, finished_at=now_iso(), progress=None)
        self.store.put(job)


def _err(code, message):
    return {"status": "failed", "error_code": code, "error_message": message}


JOB_RE = re.compile(r"^/api/v1/tcad/jobs/([^/]+)$")
CANCEL_RE = re.compile(r"^/api/v1/tcad/jobs/([^/]+)/cancel$")


def make_handler(service):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self):
            if not service.token:
                return True
            return hmac.compare_digest(self.headers.get("X-Fab-Token", "").encode("utf-8"), service.token.encode("utf-8"))

        def do_GET(self):
            if not self._authorized():
                return self._send(401, _err("UNAUTHORIZED", "X-Fab-Token 이 필요하다"))
            if self.path == "/health/ready":
                return self._send(200, service.ready())
            m = JOB_RE.match(self.path)
            if m:
                code, out = service.job(m.group(1))
                return self._send(code, out)
            self._send(404, _err("NOT_FOUND", self.path))

        def do_POST(self):
            try:
                self._post()
            except Exception as e:
                LOG.error("내부 오류: %s %s", type(e).__name__, e)
                try:
                    self._send(500, _err("INTERNAL", "내부 오류"))
                except Exception:
                    pass

        def _post(self):
            if not self._authorized():
                return self._send(401, _err("UNAUTHORIZED", "X-Fab-Token 이 필요하다"))
            m = CANCEL_RE.match(self.path)
            if m:
                code, out = service.cancel(m.group(1))
                return self._send(code, out)
            if self.path != "/api/v1/tcad/verify":
                return self._send(404, _err("NOT_FOUND", self.path))
            try:
                n = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                n = -1
            if n <= 0 or n > MAX_BODY:
                return self._send(413 if n > MAX_BODY else 400, _err("INVALID_INPUT", "본문 크기가 올바르지 않다 (1 바이트 ~ 1 MB)"))
            raw = self.rfile.read(n)
            try:
                def bad(c):
                    raise ValueError("NaN/Infinity 는 허용하지 않는다")
                req = json.loads(raw.decode("utf-8"), parse_constant=bad)
            except Exception:
                return self._send(400, _err("INVALID_INPUT", "JSON 으로 읽을 수 없다"))
            code, out = service.verify(req)
            self._send(code, out)

        def log_message(self, fmt, *args):
            LOG.info("%s %s", self.address_string(), fmt % args)
    return H


class _Server(ThreadingHTTPServer):
    allow_reuse_address = os.name != "nt"
    daemon_threads = True


def make_server(port, service, host="0.0.0.0"):
    return _Server((host, port), make_handler(service))


def setup_logging():
    LOG.setLevel(logging.INFO)
    LOG.handlers.clear()
    h = logging.StreamHandler()
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    LOG.addHandler(h)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8400)
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--token", default=os.environ.get("TCAD_SERVICE_TOKEN"))
    ap.add_argument("--success", choices=["true", "false"], help="fake 모드일 때 정상(true)/불량(false) 케이스를 돌려준다 (기본 true)")
    a = ap.parse_args()
    if a.success is not None:
        os.environ["TCAD_MOCK_SUCCESS"] = a.success
    setup_logging()
    svc = Service(token=a.token)
    srv = make_server(a.port, svc, a.host)
    LOG.info("TCAD 서비스 시작: http://%s:%s  동시실행 %s  계산모드 %s  인증 %s", a.host, a.port, svc.workers,
              os.environ.get("TCAD_CALC", "fake"), "사용" if svc.token else "없음")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        LOG.info("종료")
