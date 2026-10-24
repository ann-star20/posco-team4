"""모델 서비스: Jetson Worker 가 호출하는 HTTP 서비스 (계약 fab-ml-v1). 표준 라이브러리만 쓴다 (서로게이트가 NumPy 를 쓴다).
  POST http://127.0.0.1:8300/api/v1/predict   task_type "surrogate" (노브 -> 소자 특성) 또는 "diagnose"/"diagnosis" (측정값 -> 원인, 보정안)
  POST http://127.0.0.1:8300/api/v1/diagnose  진단 전용 경로 (task_type 생략 가능)
  GET  http://127.0.0.1:8300/health           서비스와 모델 상태
  GET  http://127.0.0.1:8300/health/ready     Gateway 준비 완료 점검용

  python 모델서비스.py                    # 서버 시작 (127.0.0.1:8300, 이 장치 안에서만 접속 가능)
  python 모델서비스.py --port 8301 --token 비밀값   # 토큰을 쓰면 요청 헤더 X-Fab-Token 이 같아야 한다 (환경변수 FAB_SERVICE_TOKEN 도 가능)

규칙
  - 형식이 잘못된 요청은 HTTP 400 + {"status": "failed", "error": {"code", "message"}}
  - surrogate: 학습 영역 밖 입력은 HTTP 200 + status "failed" + OUT_OF_DOMAIN (값을 내지 않는다. 단위를 잘못 보낸 경우도 여기서 걸린다)
  - diagnose: 측정값이 학습 영역의 어떤 상태와도 잘 맞지 않으면 warnings 에 POOR_FIT, decided false, tcad_proposal null
  - 같은 request_id 가 다시 오면 계산하지 않고 이전 응답을 그대로 돌려준다 (Worker 재시도 대응)
  - 요청 크기는 1 MB 까지, 127.0.0.1 에만 바인딩
"""
import argparse
import hashlib
import hmac
import importlib.util
import json
import logging
import os
import re
import sqlite3
import sys
import threading
import time
from collections import OrderedDict
from logging.handlers import RotatingFileHandler
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

import 변환기 as cv

HERE = Path(__file__).resolve().parent
FINAL = HERE.parent / "최종ML"
AGENT_FILE = HERE.parent / "진단에이전트" / "진단에이전트.py"
LOG = logging.getLogger("fabrx")
SERVICE_VERSION = "1.1.0"
MAX_BODY = 1_000_000
CACHE_SIZE = 1000
INSPECTION_DB = Path(os.environ.get("INSPECTION_DB", HERE / "검사결과.db"))       # 정상(no_action) 검사결과만 쌓는 로그. Gateway 쪽 운영 DB 가 따로 생기면 이 파일은 임시 기록용으로 쓴다
_inspection_lock = threading.Lock()


def _save_inspection(request_id, meas, n_wafers):
    """노브가 정상(스펙 안)일 때 원인분석·보정 없이 검사값만 남긴다.
    meas 는 agent 단위(raw, key 'id4v')라 계약 단위(uS/um, uA/um, key 'id_on')로 바꿔서 저장한다."""
    gm = meas.get("gm") * 1e6 if meas.get("gm") is not None else None
    id_on = meas.get("id4v") * 1e6 if meas.get("id4v") is not None else None
    with _inspection_lock, sqlite3.connect(INSPECTION_DB) as con:
        con.execute("CREATE TABLE IF NOT EXISTS inspections ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')), "
                    "request_id TEXT, n_wafers INTEGER, vth REAL, gm_us_per_um REAL, id_on_ua_per_um REAL, bv REAL)")
        con.execute("INSERT INTO inspections (request_id, n_wafers, vth, gm_us_per_um, id_on_ua_per_um, bv) VALUES (?,?,?,?,?,?)",
                    (request_id, n_wafers, meas.get("vth"), gm, id_on, meas.get("bv")))


def _load_module(path, name):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def load_surrogate():
    f = next(p for p in FINAL.glob("*.py") if re.search(r"^class Surrogate" + chr(92) + "b", p.read_text(encoding="utf-8"), re.M))
    return _load_module(f, "surrogate_runtime").Surrogate()


class Service:
    def __init__(self, surrogate=None, with_agent=True, token=None):
        t_load = time.perf_counter()
        self.sur = surrogate or load_surrogate()
        self.token = token
        self.model_version = "mosfet-gp-" + str(self.sur.info.get("만든날", "unknown"))
        self.cache, self.lock = OrderedDict(), threading.Lock()
        bv_in = self.sur.info.get("BV입력", "?")
        self.models = {"vth_gm": "gp-stage1-matern52-ard", "id_on": "gp-stage2-vth-input", "bv": f"gp-bv-{bv_in}-input"}
        self.agent, self.agent_mod, self.agent_error, self.pipe = None, None, None, None
        self.agent_lock = threading.Lock()
        if with_agent:
            try:
                self.agent_mod = _load_module(AGENT_FILE, "diagnosis_agent")
                self.agent = self.agent_mod.DiagnosisAgent(self.sur)           # 후보 격자 5만 개를 한 번 예측해 둔다 (시작할 때 수 초)
            except Exception as e:
                self.agent_error = f"{type(e).__name__}: {e}"
        self.tm = {}                                                       # 진단 한 건 안에서 에이전트 단계별 걸린 시간 (ms)
        if self.agent is not None:
            for name in ("diagnose", "recommend", "compensate", "final_check"):
                setattr(self.agent, name, self._timed(name, getattr(self.agent, name)))
        self.model_load_ms = round((time.perf_counter() - t_load) * 1000, 1)
        self.artifact_hash, self.training_data_version = self._artifact_info()

    def _timed(self, name, fn):
        def wrapper(*a, **k):
            t = time.perf_counter()
            try:
                return fn(*a, **k)
            finally:
                self.tm[name] = self.tm.get(name, 0.0) + (time.perf_counter() - t) * 1000
        return wrapper

    @staticmethod
    def _artifact_info():
        """서로게이트 모델 파일(gp.npz, 영역.json, 모델정보.json, 학습배열.npz)의 SHA-256 하나와 학습 데이터 식별자."""
        d = FINAL / "모델"
        h, train = hashlib.sha256(), None
        for name in ("gp.npz", "영역.json", "모델정보.json", "학습배열.npz"):
            f = d / name
            if f.exists():
                b = f.read_bytes()
                h.update(name.encode("utf-8") + hashlib.sha256(b).digest())
                if name == "학습배열.npz":
                    train = hashlib.sha256(b).hexdigest()[:12]
        return "sha256:" + h.hexdigest(), (f"tcad-train-{train}" if train else "unknown")

    def model_meta(self, kind="surrogate"):
        return {"name": "mosfet-gp-surrogate" if kind == "surrogate" else "mosfet-gp-diagnosis", "version": str(self.sur.info.get("만든날", "unknown")), "artifact_hash": self.artifact_hash,
                "training_data_version": self.training_data_version, "git_commit": None, "runtime": "python-%d.%d" % sys.version_info[:2], "device": "cpu", "precision": "float64"}

    def tasks(self):
        return ["surrogate"] + (["diagnose"] if self.agent is not None else [])

    def health(self):
        return {"status": "ok", "contract": cv.CONTRACT_VERSION, "model_version": self.model_version, "input_transform_version": cv.INPUT_TRANSFORM_VERSION,
                "tasks": self.tasks(), "spec": cv.spec_info(), "id_conditions": dict(cv.ID_CONDITIONS), "auth_required": bool(self.token)}

    def ready(self):
        """Gateway 준비 완료 점검용 (GET /health/ready)."""
        ok = self.sur is not None
        loaded = ([self.model_meta("surrogate")] if ok else []) + ([self.model_meta("diagnosis")] if self.agent is not None else [])
        return {"status": "ready" if ok else "not_ready", "result_origin": "prod", "service_version": SERVICE_VERSION, "model_version": self.model_version,
                "surrogate_ready": ok, "diagnosis_ready": self.agent is not None,
                "loaded_models": [{k: m[k] for k in ("name", "version", "artifact_hash", "device", "precision")} for m in loaded], "model_load_duration_ms": self.model_load_ms}

    def _base(self, req):
        d = req if isinstance(req, dict) else {}
        return {"request_id": d.get("request_id"), "job_id": d.get("job_id"), "model_contract_version": cv.CONTRACT_VERSION, "model_version": self.model_version}

    def error(self, req, code, message, status_code=400, extra=None, t0=None, stage=None, kind="surrogate"):
        out = self._base(req)
        dur = round((time.perf_counter() - t0) * 1000, 2) if t0 is not None else None
        meta = {"input_transform_version": cv.INPUT_TRANSFORM_VERSION, "model": self.model_meta(kind), "timing_ms": {"service_total": dur},
                "stages": [{"stage": stage or "request_validation", "status": "failed", "duration_ms": dur, "error_code": code}], **(extra or {})}
        out.update(result_origin=(req.get("surrogate_mode", "prod") if isinstance(req, dict) else "prod"), status="failed", anomaly_detected=None, result_payload=None,
                   error={"code": code, "message": message}, error_code=code, error_message=message,       # error_code/error_message: Gateway 계약이 요구하는 top-level 형태 (error 도 그대로 남긴다)
                   metadata=meta, tcad_proposal=None)
        return status_code, out

    # ---------------------------------------------------------------- 진입점 (재요청 캐시 포함)
    def predict(self, req):
        """(HTTP 상태, 응답 dict). request_id 가 같으면 이전 응답을 돌려준다."""
        rid = req.get("request_id") if isinstance(req, dict) else None
        if rid is not None:
            with self.lock:
                if rid in self.cache:
                    return self.cache[rid]
        t0 = time.perf_counter()
        tt = req.get("task_type", "surrogate") if isinstance(req, dict) else None
        if tt == "surrogate":
            res = self._surrogate(req, t0)
        elif tt in ("diagnose", "diagnosis"):                              # 계약 문서는 diagnosis, 처음 구현은 diagnose: 둘 다 받는다
            res = self._diagnose(req, t0)
        else:
            res = self.error(req, "UNSUPPORTED_TASK_TYPE" if isinstance(req, dict) else "INVALID_INPUT", f"task_type '{tt}' 는 지원하지 않는다 (지원: {self.tasks()} 와 diagnosis)" if isinstance(req, dict) else "요청은 JSON 객체여야 한다", t0=t0)
        if rid is not None:
            with self.lock:
                self.cache[rid] = res
                while len(self.cache) > CACHE_SIZE:
                    self.cache.popitem(last=False)
        return res

    # ---------------------------------------------------------------- surrogate
    def _surrogate(self, req, t0):
        ms_ = lambda t: round((time.perf_counter() - t) * 1000, 3)
        t = time.perf_counter()
        try:
            ratios, wanted = cv.parse_request(req)
        except cv.RequestError as e:
            return self.error(req, e.code, e.message, t0=t0)
        t_val = ms_(t)
        t = time.perf_counter()
        pred = self.sur.predict([ratios], strict=True)
        t_inf = ms_(t)
        t = time.perf_counter()
        values, sigma = cv.physical(pred)
        ratio_info = {k: round(r, 6) for k, r in zip(("dose", "epi", "tox"), ratios)}
        if values is None:
            return self.error(req, "OUT_OF_DOMAIN", "입력이 서로게이트 학습 영역 밖이다. 단위(도즈 cm^-2, 에피 cm^-3, 산화막 um)와 값을 확인하라.", 200, {"input_ratios": ratio_info, "in_domain": False}, t0=t0, stage="domain_check")
        out = self._base(req)
        t_post = ms_(t)
        total = round((time.perf_counter() - t0) * 1000, 2)
        out.update(result_origin=req.get("surrogate_mode", "prod"), status="succeeded", anomaly_detected=cv.is_anomaly(values), result_payload={k: values[k] for k in wanted},
                   metadata={"input_transform_version": cv.INPUT_TRANSFORM_VERSION, "input_ratios": ratio_info, "in_domain": True, "id_conditions": dict(cv.ID_CONDITIONS), "units": dict(cv.UNITS_OUT),
                             "models": dict(self.models), "sigma": {k: sigma[k] for k in wanted}, "spec": cv.spec_info(), "processing_ms": total,
                             "model": self.model_meta("surrogate"),
                             "timing_ms": {"request_validation": t_val, "inference_total": t_inf, "postprocessing": t_post, "service_total": total},       # 1단 GP, 2단 GP, BV 는 한 번의 호출이라 단계별로 나누어 재지 않는다
                             "stages": [{"stage": "request_validation", "status": "succeeded", "duration_ms": t_val}, {"stage": "inference", "status": "succeeded", "duration_ms": t_inf},
                                        {"stage": "postprocessing", "status": "succeeded", "duration_ms": t_post}]}, tcad_proposal=None)
        return 200, out

    # ---------------------------------------------------------------- diagnose
    def _ensure_pipe(self):
        """고정밀 확인이 요청됐을 때만 처음 한 번 불러온다 (torch, tabpfn 이 없으면 기본 모드로 대체됨)."""
        if self.pipe is None:
            try:
                self.pipe = self.agent_mod.load_class("TwoStagePipeline")(high_precision="auto")
            except Exception as e:
                self.pipe = False
                self.agent_error = f"고정밀 모드를 불러오지 못했다: {type(e).__name__}: {e}"
        return self.pipe or None

    @staticmethod
    def _fit(d):
        """가장 잘 맞는 후보의 χ². 크면 측정값이 학습 영역의 어떤 상태와도 잘 맞지 않는다는 뜻."""
        P, S, obs, n = d["_P"], d["_S"], d["_obs"], d["웨이퍼수"]
        chi = np.zeros(len(P))
        for j, (y, sn) in obs.items():
            chi += (y - P[:, j]) ** 2 / (sn ** 2 / n + S[:, j] ** 2)
        k = len(obs)
        thr = cv.POOR_FIT_FACTOR * k
        return {"chi2_min": float(chi.min()), "n_obs": k, "poor_fit_threshold": thr, "poor_fit": bool(chi.min() > thr)}

    def _diagnose(self, req, t0):
        ms_ = lambda t: round((time.perf_counter() - t) * 1000, 3)
        t = time.perf_counter()
        try:
            meas, n, refine = cv.parse_diagnose(req)
        except cv.RequestError as e:
            return self.error(req, e.code, e.message, t0=t0, kind="diagnosis")
        t_val = ms_(t)
        if self.agent is None:
            return self.error(req, "MODEL_NOT_READY" if self.agent_error else "UNSUPPORTED_TASK_TYPE", f"진단 에이전트를 사용할 수 없다: {self.agent_error}", 501, t0=t0, stage="model_load", kind="diagnosis")
        with self.agent_lock:                                              # 에이전트는 난수 상태를 가지므로 한 번에 하나씩 처리한다
            self.tm = {}
            t = time.perf_counter()
            self.agent.pipe = self._ensure_pipe() if refine else None
            r = self.agent.diagnose(meas, n_wafers=n)
            fit_early = self._fit(r)
            if r["판정됨"] and r["최다"] == "정상" and not fit_early["poor_fit"]:   # 노브 모두 정상: 다음측정 권고·보정탐색(비용이 큰 부분)을 생략한다
                rec, prop, fc, job = None, None, dict(실시=False, 사유="정상이라 생략"), []
            else:
                rec = self.agent.recommend(r)
                prop = self.agent.compensate(r)
                fc = self.agent.final_check(r, prop) if refine else dict(실시=False, 사유="생략")
                mean = np.array([k["평균"] for k in r["노브"]])
                job = [dict(이름="보정 후 (사후 평균 상태)", 도즈=float(mean[0] * prop["도즈배율"]), 에피=float(mean[1]), 산화막=float(mean[2] * prop["산화막배율"])),
                       dict(이름="보정 후 (가장 유력한 상태)", 도즈=float(r["MAP"][0] * prop["도즈배율"]), 에피=float(r["MAP"][1]), 산화막=float(r["MAP"][2] * prop["산화막배율"]))]
            res = dict(진단=r, 다음측정=rec, 보정안=prop, 고정밀확인=fc, TCAD확인요청=job)
            t_inf = ms_(t)
            tm = dict(self.tm)
        fc = res["고정밀확인"]
        refine_info = {"requested": refine, "performed": bool(fc.get("실시")), "model_mode": fc.get("모드"), "decision_changed": fc.get("판정바뀜"), "reason": None if fc.get("실시") else ((getattr(self.pipe, "hp_error", None) or self.agent_error) if refine else None) or fc.get("사유")}
        t = time.perf_counter()
        fit = self._fit(res["진단"])
        payload, proposal = cv.format_diagnosis(res, fit, refine_info)
        decided = payload["decision"]["decided"]
        if payload["compensation"]["route"] == "no_action":                # 노브 정상: 원인분석·보정 결과는 버리고 검사값만 남긴다
            _save_inspection(req.get("request_id") if isinstance(req, dict) else None, meas, n)
        if proposal is not None:
            proposal["cause_confirmed"] = bool(decided)
            for c in proposal["candidates"]:                                 # 후보 공정값에서 서로게이트가 예측한 특성 (TCAD 결과와 비교하는 용도)
                pr = c["process_parameters"]
                pred = self.sur.predict([[pr[k] / cv.BASE[k] for k in cv.KNOB_ORDER]], strict=True)
                vals, _ = cv.physical(pred)
                c["predicted_outputs"] = vals
        tp = payload["compensation"].get("target_process_parameters")
        if tp:                                                             # apply 든 tcad_verify 든 목표 공정값에서 서로게이트가 예측한 특성
            vals, _ = cv.physical(self.sur.predict([[tp[k] / cv.BASE[k] for k in cv.KNOB_ORDER]], strict=True))
            payload["compensation"]["target_predicted_outputs"] = vals
        t_post = ms_(t)
        warnings = ["POOR_FIT"] if fit["poor_fit"] else []
        total = round((time.perf_counter() - t0) * 1000, 1)
        r3 = lambda k: round(tm.get(k, 0.0), 3)
        timing = {"request_validation": t_val, "diagnosis": round(r3("diagnose") + r3("recommend"), 3), "compensation_search": r3("compensate"), "refine": r3("final_check"), "postprocessing": t_post, "inference_total": t_inf, "service_total": total}
        stages = [{"stage": "request_validation", "status": "succeeded", "duration_ms": t_val}, {"stage": "diagnosis", "status": "succeeded", "duration_ms": timing["diagnosis"]},
                  {"stage": "compensation_search", "status": "succeeded", "duration_ms": timing["compensation_search"]},
                  {"stage": "refine", "status": "succeeded" if refine_info["performed"] else "skipped", "duration_ms": timing["refine"]}, {"stage": "postprocessing", "status": "succeeded", "duration_ms": t_post}]
        out = self._base(req)
        out.update(result_origin=req.get("surrogate_mode", "prod"), status="succeeded", anomaly_detected=cv.violates_spec(meas.get("vth"), meas.get("bv")), result_payload=payload,
                   metadata={"input_transform_version": cv.INPUT_TRANSFORM_VERSION, "n_wafers": n, "bv_measured": meas.get("bv") is not None, "units": {**cv.UNITS_OUT}, "id_conditions": dict(cv.ID_CONDITIONS),
                             "models": dict(self.models), "warnings": warnings, "anomaly_basis": "measurements_vs_spec", "processing_ms": total,
                             "model": self.model_meta("diagnosis"), "timing_ms": timing, "stages": stages},
                   tcad_proposal=None if fit["poor_fit"] else proposal)
        return 200, out


def _err(code, message):
    return {"status": "failed", "error": {"code": code, "message": message}, "error_code": code, "error_message": message}


def make_handler(service):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self._send(200, service.health())
            elif self.path == "/health/ready":
                self._send(200, service.ready())
            else:
                self._send(404, _err("NOT_FOUND", self.path))

        def do_POST(self):
            try:
                self._post()
            except Exception as e:                                         # 처리 중 어떤 예외가 나도 연결을 그냥 끊지 않고 오류 응답을 보낸다
                LOG.error("내부 오류: %s %s", type(e).__name__, e)
                try:
                    self._send(500, _err("INFERENCE_FAILED", "내부 오류"))
                except Exception:
                    pass

        def _post(self):
            if self.path not in ("/api/v1/predict", "/api/v1/diagnose"):
                return self._send(404, _err("NOT_FOUND", self.path))
            if service.token and not hmac.compare_digest(self.headers.get("X-Fab-Token", "").encode("utf-8"), service.token.encode("utf-8")):      # 바이트로 비교 (비 ASCII 토큰도 안전)
                return self._send(401, _err("UNAUTHORIZED", "X-Fab-Token 이 필요하다"))
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
            if self.path == "/api/v1/diagnose" and isinstance(req, dict):
                req.setdefault("task_type", "diagnosis")                  # /api/v1/diagnose 로 오면 task_type 을 생략해도 된다 (다른 값이면 그대로 두어 거절)
            try:
                code, out = service.predict(req)
            except Exception as e:                                         # 예기치 못한 오류: 내부 내용을 밖으로 내보내지 않는다
                LOG.error("내부 오류: %s %s", type(e).__name__, e)
                code, out = service.error(req, "INFERENCE_FAILED", "내부 오류", 500)
            self._send(code, out)

        def log_message(self, fmt, *args):
            LOG.info("%s %s", self.address_string(), fmt % args)
    return H


def setup_logging(log_file=None):
    """화면(표준 출력)과, 지정하면 파일(5 MB 씩 3개까지 돌려 쓴다)에 기록한다."""
    LOG.setLevel(logging.INFO)
    LOG.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    h = logging.StreamHandler()
    h.setFormatter(fmt)
    LOG.addHandler(h)
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        LOG.addHandler(fh)


class _Server(ThreadingHTTPServer):
    allow_reuse_address = os.name != "nt"          # Windows 에서는 True 이면 같은 포트에 두 서버가 동시에 붙어 낡은 서버가 응답할 수 있다
    daemon_threads = True


def make_server(port=8300, service=None):
    return _Server(("127.0.0.1", port), make_handler(service or Service()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8300)
    ap.add_argument("--token", default=os.environ.get("FAB_SERVICE_TOKEN"))
    ap.add_argument("--no-agent", action="store_true", help="진단(diagnose) 기능을 끄고 surrogate 만 제공")
    ap.add_argument("--log-file", default=os.environ.get("FAB_SERVICE_LOG"), help="로그 파일 경로 (환경변수 FAB_SERVICE_LOG 도 가능)")
    a = ap.parse_args()
    setup_logging(a.log_file)
    if a.token and not a.token.isascii():
        ap.error("토큰은 ASCII(영문, 숫자, 기호)만 쓴다 (HTTP 헤더 값은 ASCII 여야 한다)")
    svc = Service(with_agent=not a.no_agent, token=a.token)
    srv = make_server(a.port, svc)
    LOG.info("모델 서비스 시작: http://127.0.0.1:%s  계약 %s  작업 %s  인증 %s", a.port, cv.CONTRACT_VERSION, svc.tasks(), "사용" if svc.token else "없음 (127.0.0.1 전용)")
    LOG.info("  Id 조건 %s  스펙 %s", cv.ID_CONDITIONS, cv.spec_info())
    if svc.agent_error:
        LOG.warning("  진단 기능 사용 불가: %s", svc.agent_error)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        LOG.info("종료")
