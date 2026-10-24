"""보정 경로 평가: 불량 TCAD 샘플에 에이전트 보정을 적용하고, 보정 후 공정값에 가장 가까운 기존 TCAD 샘플의 규격 여부로 "high_confidence(옛 apply, TCAD 생략 후보)" 판정의 오판율을 잰다.
  python 보정경로평가.py   # 결과/보정경로평가.md, 결과/보정경로평가.json (수십 분)
"""
import re
import importlib.util
import json
import shutil
import sys
import tempfile
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = HERE / "결과"
OUT.mkdir(exist_ok=True)
FINAL = HERE.parent / "최종ML"
spec = importlib.util.spec_from_file_location("agent", HERE / "진단에이전트.py")
AG = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AG)


def load_file(pred, name):
    f = next(p for p in FINAL.glob("*.py") if pred(p.read_text(encoding="utf-8")))
    s = importlib.util.spec_from_file_location(name, f)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


B = load_file(lambda t: re.search(r"^def fit_all\b", t, re.M), "builder")
SUR = load_file(lambda t: re.search(r"^class Surrogate\b", t, re.M), "sur")
sys.path.insert(0, str(HERE.parent / "고칠것6" / "구분가능성"))
import 노이즈가정 as ng

assert ng.NOISE["vth"][1] == AG.NOISE["vth"] and ng.NOISE["gm"][1] == AG.NOISE["gm"] and ng.NOISE["id_4v"][1] == AG.NOISE["id4v"] and ng.NOISE["bv"][1] == AG.NOISE["bv"], "에이전트의 잡음 가정이 노이즈가정.py 와 다르다"

X, Y, kind, rows = B.load(FINAL / "데이터" / "학습데이터_최종.csv")
cfg = dict(bv_input=json.loads((FINAL / "모델" / "모델정보.json").read_text(encoding="utf-8"))["BV입력"], bv_log=False)
base_sur = SUR.Surrogate()
inside = base_sur.domain(X)
ev_idx = np.where(inside)[0]                               # 시험 후보: 영역 안의 모든 샘플 (대량 실행 + 영역 안 단일 노브)
always = np.where(~inside)[0]                              # 영역 밖 단일 노브(IV 만 사용)는 항상 학습에 포함
DELTA = 0.05
mask_of = lambda x: int(((np.abs(np.asarray(x) - 1) > DELTA) @ np.array([1, 2, 4])))
NS = (1, 5, 25)
rng = np.random.default_rng(2026)


def fold_surrogate(train_idx):
    m = B.fit_all(X[train_idx], Y[train_idx], cfg)
    tmp = Path(tempfile.mkdtemp())
    np.savez(tmp / "gp.npz", **{f"{k}__{kk}": np.asarray(vv, np.float64) for k in ("vth", "log_gm", "log_id4v", "bv") for kk, vv in B.export_gp(m[k]).items()})
    shutil.copy(FINAL / "모델" / "영역.json", tmp / "영역.json")
    shutil.copy(FINAL / "모델" / "모델정보.json", tmp / "모델정보.json")
    return SUR.Surrogate(tmp)


def measure(i, n):
    y = dict(vth=np.array([Y[i, 0]]), gm=np.array([np.exp(Y[i, 1])]), id_4v=np.array([np.exp(Y[i, 2])]), bv=np.array([Y[i, 3]]))
    z = ng.add_noise(y, scale=1.0, n_avg=n, rng=rng)
    return dict(vth=float(z["vth"][0]), gm=float(z["gm"][0]), id4v=float(z["id_4v"][0]), bv=float(z["bv"][0]))



sys.path.insert(0, str(HERE.parent / "통신"))
import 변환기 as cv
import 모델서비스 as ms
from sklearn.model_selection import KFold

SPEC_V = AG.SPEC["vth"]
BV_MIN = AG.SPEC["bv_min"]
NS2 = (25, 100)
TOLS = (0.04, 0.06, 0.08, 0.10)
tcad_ok = lambda j: bool(SPEC_V[0] <= Y[j, 0] <= SPEC_V[1] and (np.isnan(Y[j, 3]) or Y[j, 3] >= BV_MIN))
defective = lambda i: not tcad_ok(i)
recs = []
t0 = time.time()
for fold, (tr, te) in enumerate(KFold(5, shuffle=True, random_state=0).split(ev_idx)):
    sur = fold_surrogate(np.r_[ev_idx[tr], always])
    agent = AG.DiagnosisAgent(sur, seed=fold)
    for i in ev_idx[te]:
        if not defective(i):
            continue
        xt = X[i]
        has_bv = not np.isnan(Y[i, 3])
        for n in NS2:
            m = measure(i, n)
            if not has_bv:
                m["bv"] = None
            res = agent.run(m, n_wafers=n, check=False)
            fit = ms.Service._fit(res["진단"])
            payload, _ = cv.format_diagnosis(res, fit, {})
            comp = payload["compensation"]
            xa = xt * np.array([comp["factors"]["body_dose"], 1.0, comp["factors"]["oxide_thickness"]])
            d = np.max(np.abs(X[:, :] - xa), axis=1)
            d[i] = np.inf
            j = int(np.argmin(d))
            recs.append(dict(i=int(i), n=n, bv=has_bv, truth_cat=mask_of(xt), route=("high_confidence" if comp["high_confidence"] else comp["route"]), reasons=comp["confidence_blockers"], decision=payload["decision"], knobs=payload["knobs"], comp=comp, fit=fit,
                             nn_dist=float(d[j]), nn_ok=tcad_ok(j), nn_vth=float(Y[j, 0]), nn_bv=None if np.isnan(Y[j, 3]) else float(Y[j, 3]), sur_ok=bool(sur.domain(xa[None])[0] and SPEC_V[0] <= sur.raw_calibrated(xa[None])[0][0, 0] <= SPEC_V[1])))
    print(f"접힘 {fold} 끝 ({time.time() - t0:.0f}초, 기록 {len(recs)}건)", flush=True)
    json.dump(recs, open(OUT / "보정경로평가.json", "w", encoding="utf-8"), ensure_ascii=False, default=float)


def rate(s, ok_key="nn_ok"):
    return (np.mean([r[ok_key] for r in s]), len(s)) if s else (float("nan"), 0)


def reroute(r, **over):
    saved = dict(cv.AUTO)
    cv.AUTO.update(over)
    try:
        return "high_confidence" if (not r["fit"]["poor_fit"] and r["decision"]["top_category"] != "normal" and not cv.confidence_blockers(r["decision"], r["knobs"], r["comp"])) else "other"
    finally:
        cv.AUTO.clear()
        cv.AUTO.update(saved)


L = ["# 보정 경로 평가: 에이전트 보정을 TCAD 없이 바로 적용해도 되는가", "",
     f"- 시험 문제: 학습 데이터 중 규격 밖(Vth {SPEC_V[0]}~{SPEC_V[1]} V 밖, 또는 BV < {BV_MIN:g} V)인 TCAD 샘플 {len({r['i'] for r in recs})}개. 5-겹 교차검증, 시험 샘플은 그 접힘의 서로게이트 학습에 쓰지 않았다. 측정 = TCAD 출력 + 가정 잡음(웨이퍼 N장 평균), BV는 있는 샘플만 측정.",
     "- 에이전트가 낸 도즈·산화막 배율을 진짜 공정값에 곱해 \"보정 후 공정값\"을 만들고, **그 점에서 가장 가까운(최대 비율 차이) 기존 TCAD 샘플**(자기 자신 제외)의 TCAD 결과가 규격 안이면 \"보정 성공\"으로 본다. 보정 후 지점을 TCAD로 새로 돌린 것이 아니라 **근사**다.",
     "- 이웃이 멀면 정답이 부정확하므로 이웃 거리 기준(최대 비율 차이)별로 따로 센다. 이웃 샘플의 BV 값이 없으면 Vth만 본다.", "",
     "## 1. 현재 기준(AUTO)에서 경로별 결과", "", f"현재 기준: {cv.AUTO}", "",
     "| 웨이퍼 N | 경로 | 건수 | 비율 | " + " | ".join(f"이웃 ≤{t} 건수 / 규격 안" for t in TOLS) + " |", "|---|---|---|---|" + "---|" * len(TOLS)]
for n in NS2:
    s_n = [r for r in recs if r["n"] == n]
    for route in ("high_confidence", "tcad_verify", "manual", "no_action"):
        s = [r for r in s_n if r["route"] == route]
        if not s:
            continue
        cells = []
        for t in TOLS:
            ss = [r for r in s if r["nn_dist"] <= t]
            cells.append(f"{len(ss)} / " + (f"{100 * np.mean([r['nn_ok'] for r in ss]):.0f} %" if ss else "-"))
        L.append(f"| {n} | {route} | {len(s)} | {100 * len(s) / len(s_n):.0f} % | " + " | ".join(cells) + " |")
L += ["", "읽는 법: apply 줄의 \"규격 안\" 비율이 낮으면 TCAD 없이 쓰면 안 되는 보정을 바로 적용한 것(오판)이다. tcad_verify 줄의 \"규격 안\" 비율이 높으면 쓸 수 있었는데 TCAD로 보낸 것(낭비)이다.", ""]
L += ["## 2. 기준을 바꿨을 때 (이웃 거리 ≤ 0.08인 건만 오판을 센다)", "", "| 보정 후 규격확률 ≥ | 원인확률 ≥ | 웨이퍼 N | TCAD 생략률(apply 비율) | apply 중 이웃 확인 가능 | 오판율(apply인데 이웃이 규격 밖) |", "|---|---|---|---|---|---|"]
for ps in (0.90, 0.95, 0.99, 0.999):
    for pc in (0.70, 0.80, 0.90, 0.95):
        for n in NS2:
            s_n = [r for r in recs if r["n"] == n]
            ap = [r for r in s_n if reroute(r, p_spec_after=ps, p_cause=pc) == "high_confidence"]
            chk = [r for r in ap if r["nn_dist"] <= 0.08]
            L.append(f"| {ps} | {pc} | {n} | {100 * len(ap) / len(s_n):.0f} % | {len(chk)}/{len(ap)} | " + (f"{100 * (1 - np.mean([r['nn_ok'] for r in chk])):.0f} % ({sum(not r['nn_ok'] for r in chk)}건)" if chk else "-") + " |")
L += ["", "## 3. 서로게이트 자체 판단과의 비교", ""]
for n in NS2:
    ap = [r for r in recs if r["n"] == n and r["route"] == "high_confidence"]
    if ap:
        L.append(f"- N={n}, apply {len(ap)}건: 같은 서로게이트가 \"보정 후 규격 안\"이라 본 비율 {100 * np.mean([r['sur_ok'] for r in ap]):.0f} % (순환 논리라 참고용), 이웃 TCAD 기준 {100 * np.mean([r['nn_ok'] for r in ap]):.0f} % (이웃 거리 평균 {np.mean([r['nn_dist'] for r in ap]):.3f}).")
L += ["", "## 4. 한계", "", "- 보정 후 공정값을 TCAD로 직접 돌린 것이 아니라 가장 가까운 기존 샘플로 근사했다. 샘플이 듬성듬성하면(거리가 멀면) 규격 경계 근처에서 틀릴 수 있다.",
      "- 측정 잡음은 가정값, 데이터는 합성 TCAD다. 실제 공정의 오판율은 이와 다를 수 있다.", "- 건수가 적은 칸의 비율은 불안정하다. 건수를 같이 보라."]
(OUT / "보정경로평가.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
print(f"총 {time.time() - t0:.0f}초")
