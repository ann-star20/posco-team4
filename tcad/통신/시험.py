"""모델 서비스 시험: 서버를 임시 포트로 띄우고 계약대로 응답하는지 확인한다 (Worker, Unity 없이 실행 가능).
  python 시험.py
확인 항목: surrogate (기준값, 계약 예시, 단위 실수, 잘못된 요청, 출력 선택, 이상 판정, 재요청), diagnose (판정, 구분 불가와 BV 권고, 맞지 않는 측정, 잘못된 요청, 고정밀 요청), 토큰, 상태 확인
"""
import json
import threading
import urllib.error
import urllib.request

import 모델서비스 as ms

BASE = {"body_dose": 7.7e12, "epi_doping": 1.7e16, "oxide_thickness": 0.06}


def call(port, path, body=None, raw=None, method=None, headers=None):
    data = raw if raw is not None else (json.dumps(body).encode("utf-8") if body is not None else None)
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method or ("POST" if data is not None else "GET"), headers=h)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def request(pp, rid="r1", **kw):
    d = {"schema_version": 1, "task_type": "surrogate", "request_id": rid, "job_id": "j1", "run_id": "run1", "lot_id": "LOT-001", "attempt": 1, "model_contract_version": "fab-ml-v1",
         "surrogate_mode": "prod", "input_payload": {"process_parameters": pp, "requested_outputs": ["vth", "gm", "id_on", "bv"]}}
    d.update(kw)
    return d


def diag(measurements, rid, n=5, **extra):
    return {"schema_version": 1, "task_type": "diagnose", "request_id": rid, "job_id": "j2", "run_id": "run1", "lot_id": "LOT-001", "attempt": 1, "model_contract_version": "fab-ml-v1", "surrogate_mode": "prod",
            "input_payload": {"measurements": measurements, "n_wafers": n, **extra}}


def measured(sur, ratios, bv=True):
    """서로게이트가 노브 비율에서 낸 값을 계약 단위의 측정값으로 (잡음 없음)."""
    y = sur.predict([ratios])
    return {"vth": float(y["vth"][0]), "gm": float(y["gm"][0]) * 1e6, "id_on": float(y["id4v"][0]) * 1e6, "bv": float(y["bv"][0]) if bv else None}


def main():
    svc = ms.Service()
    srv = ms.make_server(0, svc)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(("통과  " if cond else "실패  ") + name + (f"  ({detail})" if detail else ""))

    # ---------------- surrogate
    c, r = call(port, "/api/v1/predict", request(BASE, "base-1"))
    p = r["result_payload"]
    check("기준값 요청이 성공하고 값이 TCAD 기준값 근처", c == 200 and r["status"] == "succeeded" and abs(p["vth"] - 2.258) < 0.05 and abs(p["gm"] - 4.57) < 0.3 and abs(p["id_on"] - 5.21) < 0.3 and abs(p["bv"] - 41.1) < 1.0, str({k: round(v, 3) for k, v in p.items()}))
    check("ID 가 그대로 돌아온다", r["request_id"] == "base-1" and r["job_id"] == "j1" and r["model_contract_version"] == "fab-ml-v1" and r["result_origin"] == "prod")
    m = r["metadata"]
    check("id_conditions 가 TCAD 조건 (Vgs 4 V, Vds 0.1 V, 300 K)", m["id_conditions"] == {"vgs_v": 4.0, "vds_v": 0.1, "temperature_c": 26.85}, str(m["id_conditions"]))
    check("메타데이터: 변환 버전, 모델, σ, 처리 시간, 영역, 스펙 상태", m["input_transform_version"] == "gp-transform-v1" and set(m["models"]) == {"vth_gm", "id_on", "bv"} and set(m["sigma"]) == set(p) and m["in_domain"] is True and m["processing_ms"] >= 0 and m["spec"]["status"] == "datasheet_AOI4184")
    check("모델 버전 형식과 tcad_proposal null", r["model_version"].startswith("mosfet-gp-") and r["tcad_proposal"] is None and r["anomaly_detected"] is False)
    c, r = call(port, "/api/v1/predict", request({"body_dose": 1.2e13, "epi_doping": 2.5e15, "oxide_thickness": 5.2}, "ex-1"))
    check("계약 문서의 예시 숫자는 OUT_OF_DOMAIN 으로 막힌다 (값을 내지 않음)", c == 200 and r["status"] == "failed" and r["error"]["code"] == "OUT_OF_DOMAIN" and r["result_payload"] is None)
    c, r = call(port, "/api/v1/predict", request({**BASE, "oxide_thickness": 60}, "unit-1"))
    check("산화막을 nm(60) 로 보내면 OUT_OF_DOMAIN", r["status"] == "failed" and r["error"]["code"] == "OUT_OF_DOMAIN")
    c, r = call(port, "/api/v1/predict", raw=b"{not json")
    check("JSON 이 아니면 400 INVALID_INPUT", c == 400 and r["error"]["code"] == "INVALID_INPUT")
    c, r = call(port, "/api/v1/predict", raw=b'{"input_payload": {"process_parameters": {"body_dose": NaN, "epi_doping": 1.7e16, "oxide_thickness": 0.06}}}')
    check("NaN 은 거부", c == 400)
    c, r = call(port, "/api/v1/predict", request({"body_dose": 7.7e12, "epi_doping": 1.7e16}, "bad-1"))
    check("필드 누락은 400 INVALID_INPUT", c == 400 and r["error"]["code"] == "INVALID_INPUT" and "oxide_thickness" in r["error"]["message"] and r["request_id"] == "bad-1")
    c, r = call(port, "/api/v1/predict", request({**BASE, "body_dose": -1.0}, "bad-2"))
    check("음수는 400", c == 400 and r["error"]["code"] == "INVALID_INPUT")
    c, r = call(port, "/api/v1/predict", request(BASE, "bad-3", task_type="unknown"))
    check("모르는 task_type 은 UNSUPPORTED_TASK_TYPE", c == 400 and r["error"]["code"] == "UNSUPPORTED_TASK_TYPE")
    c, r = call(port, "/api/v1/predict", request(BASE, "bad-4", model_contract_version="fab-ml-v9"))
    check("다른 계약 버전은 UNSUPPORTED_CONTRACT_VERSION", c == 400 and r["error"]["code"] == "UNSUPPORTED_CONTRACT_VERSION")
    c, r = call(port, "/nowhere", {"a": 1})
    check("없는 경로는 404", c == 404)
    c, r = call(port, "/api/v1/predict", request(BASE, "sel-1", input_payload={"process_parameters": BASE, "requested_outputs": ["vth", "bv"]}))
    check("requested_outputs 만 돌려준다", set(r["result_payload"]) == {"vth", "bv"} and set(r["metadata"]["sigma"]) == {"vth", "bv"})
    c, r = call(port, "/api/v1/predict", request(BASE, "sel-2", input_payload={"process_parameters": BASE, "requested_outputs": ["vth", "foo"]}))
    check("알 수 없는 출력 이름은 400", c == 400)
    c, r = call(port, "/api/v1/predict", request({**BASE, "oxide_thickness": 0.06 * 1.25}, "an-1"))
    check("산화막 +25 % 는 anomaly_detected true", r["status"] == "succeeded" and r["anomaly_detected"] is True, f"vth {r['result_payload']['vth']:.2f}")
    c1, r1 = call(port, "/api/v1/predict", request({**BASE, "oxide_thickness": 0.066}, "same-1"))
    c2, r2 = call(port, "/api/v1/predict", request({**BASE, "oxide_thickness": 0.054}, "same-1"))
    check("같은 request_id 는 이전 응답을 그대로 돌려준다", r1 == r2)

    # ---------------- diagnose
    check("진단 기능이 켜져 있다", svc.agent is not None, str(svc.agent_error))
    if svc.agent is not None:
        truth = [1.0, 1.0, 1.15]
        c, r = call(port, "/api/v1/predict", diag(measured(svc.sur, truth), "d-1", n=25))
        pl = r["result_payload"]
        tox = pl["knobs"]["oxide_thickness"]
        check("진단: 산화막 +15 % (BV 측정, 25장)가 성공하고 산화막 추정이 맞다", c == 200 and r["status"] == "succeeded" and 0.06 * 1.05 < tox["mean"] < 0.06 * 1.25 and tox["p_deviated"] > 0.8,
              f"산화막 평균 {tox['mean']:.4f} um (진짜 {0.06 * 1.15:.4f}), 판정 {pl['decision']['top_category']} {pl['decision']['top_probability']:.2f}")
        c, rv = call(port, "/api/v1/predict", diag(measured(svc.sur, [1.0, 1.0, 1.25]), "route-v", n=25))
        plv = rv["result_payload"]
        check("진단: 이상 판정, 보정안은 산화막을 줄이는 방향, tcad_proposal 이 채워진다", rv["anomaly_detected"] is True and plv["compensation"]["changes"]["oxide_thickness"] < 0 and rv["tcad_proposal"] is not None
              and rv["tcad_proposal"]["requires_human_approval"] is True and rv["tcad_proposal"]["verified_by_tcad"] is False and len(rv["tcad_proposal"]["candidates"]) >= 1, str(plv["compensation"]["changes"]))
        check("진단: 후보 TCAD 입력이 물리 단위(기준값과 같은 크기)", 1e12 < rv["tcad_proposal"]["candidates"][0]["process_parameters"]["body_dose"] < 1e14 and 1e15 < rv["tcad_proposal"]["candidates"][0]["process_parameters"]["epi_doping"] < 1e17
              and 0.01 < rv["tcad_proposal"]["candidates"][0]["process_parameters"]["oxide_thickness"] < 0.2)
        check("진단: 산화막 +15 % (25장)는 임계값을 모두 통과해 apply (TCAD 건너뜀), tcad_proposal 없음, 목표 공정값과 예측 특성 포함", pl["compensation"]["route"] == "apply" and pl["compensation"]["high_confidence"] is True and pl["compensation"]["confidence_blockers"] == [] and 0.9 < pl["compensation"]["confidence"] <= 1 and r["tcad_proposal"] is None and set(pl["compensation"]["target_process_parameters"]) == {"body_dose", "epi_doping", "oxide_thickness"} and set(pl["compensation"]["target_predicted_outputs"]) == {"vth", "gm", "id_on", "bv"}, str(pl["compensation"]["confidence_blockers"]))
        check("진단: 산화막 +25 % 는 보정량이 한도를 넘어 임계값을 못 채우므로 tcad_verify + tcad_proposal", plv["compensation"]["route"] == "tcad_verify" and plv["compensation"]["high_confidence"] is False and "CHANGE_TOO_LARGE" in plv["compensation"]["confidence_blockers"] and rv["tcad_proposal"]["high_confidence"] is False, str(plv["compensation"]["confidence_blockers"]))
        c, r8 = call(port, "/api/v1/predict", diag(measured(svc.sur, [1.0, 1.0, 1.08]), "route-8", n=100))
        c8 = r8["result_payload"]["compensation"]
        check("진단: 산화막 +8 % (100장)는 apply, requires_human_approval, thresholds·threshold_evidence", c8["route"] == "apply" and c8["high_confidence"] is True and c8["requires_human_approval"] is True and r8["tcad_proposal"] is None and c8["thresholds"]["p_spec_after"] == 0.99 and c8["threshold_evidence"]["max_abs_change_ratio"] <= 0.15, f"{c8['route']} {c8['confidence_blockers']} 판정 {r8['result_payload']['decision']['top_category']} {r8['result_payload']['decision']['top_probability']:.2f}")
        c, r0 = call(port, "/api/v1/predict", diag(measured(svc.sur, [1.0, 1.0, 1.0]), "route-0", n=100))
        check("진단: 기준값 측정은 보정이 필요 없다(no_action), tcad_proposal 없음", r0["result_payload"]["compensation"]["route"] == "no_action" and r0["tcad_proposal"] is None, f"{r0['result_payload']['compensation']['route']} {r0['result_payload']['decision']['top_category']}")
        check("진단: 응답 구조 (결정, 후보, 다음 측정, fit, spec, 처리 시간)", all(k in pl for k in ("decision", "knobs", "next_measurement", "compensation", "fit", "refine", "spec")) and pl["fit"]["poor_fit"] is False and r["metadata"]["processing_ms"] > 0, f"{r['metadata']['processing_ms']} ms")
        c, r = call(port, "/api/v1/predict", diag(measured(svc.sur, [1.0, 0.6, 1.0], bv=False), "d-2", n=5))
        pl = r["result_payload"]
        check("진단: 에피만 벗어났는데 BV 를 안 재면 구분 불가이고 BV 측정을 권한다", r["status"] == "succeeded" and pl["decision"]["decided"] is False and "BV" in pl["next_measurement"]["recommendation"], pl["next_measurement"]["recommendation"][:40])
        c, r = call(port, "/api/v1/predict", diag({"vth": 0.5, "gm": 11.0, "id_on": 40.0, "bv": None}, "d-3", n=5))
        check("진단: 어떤 상태와도 맞지 않는 측정은 POOR_FIT, 판정 안 함, tcad_proposal 없음", r["status"] == "succeeded" and "POOR_FIT" in r["metadata"]["warnings"] and r["result_payload"]["decision"]["decided"] is False and r["tcad_proposal"] is None,
              f"χ² {r['result_payload']['fit']['chi2_min']:.0f}")
        for name, body in (("측정값 없음", diag({}, "d-4")), ("알 수 없는 측정 항목", diag({"vth": 2.2, "foo": 1.0}, "d-5")), ("BV 만 있음", diag({"bv": 40.0}, "d-6")), ("n_wafers 0", diag({"vth": 2.2}, "d-7", n=0)),
                           ("음수 측정값", diag({"vth": -1.0}, "d-8")), ("refine 이 불리언이 아님", diag({"vth": 2.2}, "d-9", refine="yes"))):
            c, r = call(port, "/api/v1/predict", body)
            check(f"진단 잘못된 요청 ({name})은 400", c == 400 and r["error"]["code"] == "INVALID_INPUT", r["error"]["message"][:30])
        c1, r1 = call(port, "/api/v1/predict", diag(measured(svc.sur, truth), "d-same", n=5))
        c2, r2 = call(port, "/api/v1/predict", diag(measured(svc.sur, [1.0, 1.0, 1.3]), "d-same", n=5))
        check("진단도 같은 request_id 는 이전 응답을 그대로", r1 == r2)
        c, r = call(port, "/api/v1/predict", diag(measured(svc.sur, truth), "d-ref", n=5, refine=True))
        ri = r["result_payload"]["refine"]
        check("진단: 고정밀 확인을 요청해도 응답이 오고 (쓸 수 없으면 사유 표시) 정보가 채워진다", r["status"] == "succeeded" and ri["requested"] is True and ri["performed"] in (True, False) and (ri["performed"] or ri["reason"]), f"실시 {ri['performed']} 모드 {ri['model_mode']} 사유 {str(ri['reason'])[:40]}")
    # ---------------- Gateway 요청서(계약 확장): /api/v1/diagnose, diagnosis, 메타데이터, 오류 코드
    c, r = call(port, "/health/ready")
    check("/health/ready: ready, 모델 목록(이름·버전·해시·장치·정밀도), 로딩 시간", c == 200 and r["status"] == "ready" and r["surrogate_ready"] is True and r["diagnosis_ready"] is True and r["service_version"]
          and len(r["loaded_models"]) == 2 and all(set(m) == {"name", "version", "artifact_hash", "device", "precision"} for m in r["loaded_models"]) and r["loaded_models"][0]["artifact_hash"].startswith("sha256:") and r["model_load_duration_ms"] > 0)
    c, r = call(port, "/api/v1/predict", request(BASE, "meta-1"))
    m = r["metadata"]
    check("surrogate 응답에 model·timing_ms·stages", c == 200 and m["model"]["name"] == "mosfet-gp-surrogate" and m["model"]["precision"] == "float64" and m["model"]["training_data_version"].startswith("tcad-train-")
          and {"request_validation", "inference_total", "service_total"} <= set(m["timing_ms"]) and [x["stage"] for x in m["stages"]] == ["request_validation", "inference", "postprocessing"] and all(x["status"] == "succeeded" for x in m["stages"]))
    c, r = call(port, "/api/v1/predict", request({**BASE, "body_dose": 3.2e13, "epi_doping": 1.0e16, "oxide_thickness": 0.05}, "meta-2"))
    check("영역 밖 실패 응답: error_code·error_message·model·timing_ms·stages(domain_check 실패)", r["status"] == "failed" and r["error_code"] == "OUT_OF_DOMAIN" and r["error_message"] and r["result_payload"] is None and r["tcad_proposal"] is None
          and r["metadata"]["model"]["artifact_hash"].startswith("sha256:") and r["metadata"]["timing_ms"]["service_total"] >= 0 and r["metadata"]["stages"][0] == {"stage": "domain_check", "status": "failed", "duration_ms": r["metadata"]["stages"][0]["duration_ms"], "error_code": "OUT_OF_DOMAIN"})
    c, r = call(port, "/api/v1/predict", request({"body_dose": 1.0}, "meta-3"))
    check("입력 오류는 400 INVALID_INPUT, 최상위 error_code 도 같다", c == 400 and r["error_code"] == "INVALID_INPUT" and r["error"]["code"] == "INVALID_INPUT")
    if svc.agent is not None:
        dreq = diag(measured(svc.sur, [1.0, 1.0, 1.25]), "gw-1", n=25)
        dreq["task_type"] = "diagnosis"
        c, r = call(port, "/api/v1/diagnose", dreq)
        pl, m = r["result_payload"], r["metadata"]
        check("/api/v1/diagnose + task_type diagnosis 가 동작하고 영문 분류 코드·label", c == 200 and r["status"] == "succeeded" and pl["decision"]["top_category"] == "oxide" and pl["decision"]["top_category_label"] == "산화막" and "oxide" in pl["decision"]["category_probabilities"]
              and pl["decision"]["candidates"][0]["category"] == "oxide" and pl["decision"]["candidates"][0]["category_label"] == "산화막")
        check("진단: recommendation_code, action_code, requires_human_approval", pl["next_measurement"]["recommendation_code"] in ("none_needed", "no_improvement", "measure_bv", "more_wafers_2x", "more_wafers_4x") and all(a["action_code"] in ("measure_bv", "more_wafers_2x", "more_wafers_4x") for a in pl["next_measurement"]["actions"])
              and pl["compensation"]["requires_human_approval"] is True and pl["compensation"]["route"] in ("apply", "tcad_verify", "no_action", "manual"))
        check("진단: model(mosfet-gp-diagnosis)·timing_ms(diagnosis, compensation_search, refine)·stages", m["model"]["name"] == "mosfet-gp-diagnosis" and {"request_validation", "diagnosis", "compensation_search", "refine", "postprocessing", "inference_total", "service_total"} <= set(m["timing_ms"])
              and m["timing_ms"]["diagnosis"] > 0 and m["timing_ms"]["compensation_search"] > 0 and [x["stage"] for x in m["stages"]] == ["request_validation", "diagnosis", "compensation_search", "refine", "postprocessing"], str(m["timing_ms"]))
        dreq2 = diag({"vth": 2.3}, "gw-2")
        c, r = call(port, "/api/v1/diagnose", dreq2)
        check("/api/v1/diagnose 는 task_type 을 생략해도 된다", c == 200 and r["status"] == "succeeded")
        dreq3 = diag({"vth": -1.0}, "gw-3")
        dreq3["task_type"] = "diagnosis"
        c, r = call(port, "/api/v1/predict", dreq3)
        check("진단 입력 오류도 400 INVALID_INPUT + 진단 model 메타", c == 400 and r["error_code"] == "INVALID_INPUT" and r["metadata"]["model"]["name"] == "mosfet-gp-diagnosis")
    # ---------------- 토큰
    srv2 = ms.make_server(0, ms.Service(surrogate=svc.sur, with_agent=False, token="secret"))
    port2 = srv2.server_address[1]
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    c, r = call(port2, "/api/v1/predict", request(BASE, "t-1"))
    check("토큰을 켜면 헤더 없이는 401", c == 401 and r["error"]["code"] == "UNAUTHORIZED")
    c, r = call(port2, "/api/v1/predict", request(BASE, "t-2"), headers={"X-Fab-Token": "wrong"})
    check("틀린 토큰은 401", c == 401)
    c, r = call(port2, "/api/v1/predict", request(BASE, "t-3"), headers={"X-Fab-Token": "secret"})
    check("맞는 토큰은 성공", c == 200 and r["status"] == "succeeded")
    c, r = call(port2, "/api/v1/predict", diag({"vth": 2.2}, "t-4"), headers={"X-Fab-Token": "secret"})
    check("진단을 끈 서비스는 diagnose 를 UNSUPPORTED_TASK_TYPE 으로 거절", c in (400, 501) and r["error"]["code"] == "UNSUPPORTED_TASK_TYPE")
    c, r = call(port2, "/health")
    check("/health 는 토큰 없이 열리고 auth_required 를 알린다", c == 200 and r["auth_required"] is True and r["tasks"] == ["surrogate"])
    c, r = call(port, "/health")
    check("/health", c == 200 and r["status"] == "ok" and r["contract"] == "fab-ml-v1" and "surrogate" in r["tasks"] and r["spec"]["status"] == "datasheet_AOI4184")
    srv.shutdown()
    srv2.shutdown()
    print("== 전체 판정:", "모두 통과" if ok else "실패 항목 있음")
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
