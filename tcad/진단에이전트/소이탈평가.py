"""소이탈 평가: 기준값 근처 작은 이탈 TCAD 샘플(번호 147~182, 대량작업2/샘플링계획/소이탈계획_N182.md)로 high_confidence 의 오판율을 잰다.
  - 서로게이트는 기존 학습 데이터(1~146 + 단일 노브)로만 학습한다. 새 샘플은 학습에 쓰지 않고 시험 문제로만 쓴다.
  - 새 샘플 중 TCAD 가 규격 밖(Vth 1.7~2.6 V 밖 또는 BV < 40 V)으로 확인한 것마다, 잡음 낀 측정값(웨이퍼 N장 평균)으로 에이전트 보정을 받고,
    보정 후 공정값에 가장 가까운 TCAD 샘플(기존 + 새 샘플, 자기 자신 제외)의 규격 여부로 근사 판정한다.
  - 보정 후 공정값(진짜 공정값 x 배율)은 결과/소이탈평가_보정후공정값.csv 에 저장한다: TCAD 로 직접 돌려 근사 없이 확인하는 2단계 용도.
  python 소이탈평가.py   # 결과/소이탈평가.md, 결과/소이탈평가.json
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

SPEC_V, BV_MIN = AG.SPEC["vth"], AG.SPEC["bv_min"]
RUNS = HERE.parent / "대량작업2" / "대량실행" / "runs"
NS2 = (25, 100)
TOLS = (0.03, 0.05, 0.08)

new = []                                                         # 번호 147~182 의 TCAD 결과
for no in range(147, 183):
    f = RUNS / f"{no:03d}" / "결과.json"
    if not f.exists():
        continue
    j = json.loads(f.read_text(encoding="utf-8"))
    if j.get("status") != "ok" or "ratios" not in j:
        continue
    bv = (j.get("bvt_levels") or {}).get("1e-09")
    new.append(dict(no=no, x=np.array([j["ratios"]["dose"], j["ratios"]["epi"], j["ratios"]["tox"]]), vth=j["vth"], gm=j["gm"], id4v=j["id4v"], bv=bv, arm=j.get("확장축", "")))
print(f"새 샘플 {len(new)}개 읽음")
ok_of = lambda vth, bv: bool(SPEC_V[0] <= vth <= SPEC_V[1] and (bv is None or bv >= BV_MIN))
for r in new:
    r["ok"] = ok_of(r["vth"], r["bv"])
bad_new = [r for r in new if not r["ok"]]
print(f"그중 TCAD 규격 밖 {len(bad_new)}개, 규격 안 {len(new) - len(bad_new)}개")

pool_x = np.vstack([X] + [r["x"][None] for r in new])           # 이웃 후보: 기존 모든 샘플 + 새 샘플
pool_ok = [ok_of(Y[i, 0], None if np.isnan(Y[i, 3]) else Y[i, 3]) for i in range(len(X))] + [r["ok"] for r in new]
sur = fold_surrogate(np.arange(len(X)))                          # 기존 데이터 전체로 학습 (새 샘플 미포함)
agent = AG.DiagnosisAgent(sur, seed=7)
recs = []
t0 = time.time()
for r in bad_new:
    for n in NS2:
        y = dict(vth=np.array([r["vth"]]), gm=np.array([r["gm"]]), id_4v=np.array([r["id4v"]]), bv=np.array([r["bv"] if r["bv"] is not None else np.nan]))
        z = ng.add_noise(y, scale=1.0, n_avg=n, rng=rng)
        m = dict(vth=float(z["vth"][0]), gm=float(z["gm"][0]), id4v=float(z["id_4v"][0]), bv=(float(z["bv"][0]) if r["bv"] is not None else None))
        res = agent.run(m, n_wafers=n, check=False)
        fit = ms.Service._fit(res["진단"])
        payload, _ = cv.format_diagnosis(res, fit, {})
        comp = payload["compensation"]
        xa = r["x"] * np.array([comp["factors"]["body_dose"], 1.0, comp["factors"]["oxide_thickness"]])
        d = np.max(np.abs(pool_x - xa), axis=1)
        for k, q in enumerate(new):
            if q["no"] == r["no"]:
                d[len(X) + k] = np.inf                           # 자기 자신 제외
        j = int(np.argmin(d))
        recs.append(dict(no=r["no"], arm=r["arm"], n=n, x=r["x"].tolist(), xa=xa.tolist(), route=comp["route"], hc=bool(comp["high_confidence"]), blockers=comp["confidence_blockers"], conf=comp["confidence"],
                         decision=payload["decision"], knobs=payload["knobs"], comp=comp, fit=fit, nn_dist=float(d[j]), nn_ok=bool(pool_ok[j]), top=payload["decision"]["top_category"]))
    print(f"번호 {r['no']} 끝 ({time.time() - t0:.0f}초)", flush=True)
json.dump(recs, open(OUT / "소이탈평가.json", "w", encoding="utf-8"), ensure_ascii=False, default=float)
import csv
with open(OUT / "소이탈평가_보정후공정값.csv", "w", newline="", encoding="utf-8-sig") as fh:
    w = csv.writer(fh)
    w.writerow(["번호", "웨이퍼N", "high_confidence", "도즈비율", "에피비율", "산화막비율"])
    for r in recs:
        w.writerow([r["no"], r["n"], r["hc"], *[f"{v:.4f}" for v in r["xa"]]])

L = ["# 소이탈 평가: 작은 이탈 샘플에서 high_confidence 가 믿을 만한가", "",
     f"- 새 TCAD 샘플 {len(new)}개 (번호 147~182) 중 규격 밖 {len(bad_new)}개를 시험 문제로 썼다. 서로게이트는 기존 데이터로만 학습했다 (새 샘플은 학습에 쓰지 않음).",
     "- 측정 = TCAD 출력 + 가정 잡음(웨이퍼 N장 평균), 보정은 에이전트 기본 모드. 보정 후 공정값에 가장 가까운(최대 비율 차이) TCAD 샘플(자기 자신 제외)의 규격 여부로 \"보정 성공\"을 근사했다.",
     f"- 현재 기준: {cv.AUTO}", ""]
L += ["## 1. 샘플 구성 (TCAD 결과 기준)", "", "| 군 | 전체 | 규격 안 | Vth 만 밖 | BV 만 밖 | 둘 다 밖 |", "|---|---|---|---|---|---|"]
for g in ("G1", "G2", "G3", "G4", "G5"):
    s = [r for r in new if r["arm"] == g]
    if s:
        vo = lambda r: not (SPEC_V[0] <= r["vth"] <= SPEC_V[1])
        bo = lambda r: r["bv"] is not None and r["bv"] < BV_MIN
        L.append(f"| {g} | {len(s)} | {sum(r['ok'] for r in s)} | {sum(vo(r) and not bo(r) for r in s)} | {sum(bo(r) and not vo(r) for r in s)} | {sum(vo(r) and bo(r) for r in s)} |")
L += ["", "군은 서로게이트 예측으로 나눈 것이라 TCAD 결과와 다를 수 있다 (규격 안이 나온 샘플은 시험 문제에서 뺐다).", ""]
L += ["## 2. 경로와 high_confidence", "", "| 웨이퍼 N | 건수 | high_confidence | tcad_verify(비고신뢰) | manual |", "|---|---|---|---|---|"]
for n in NS2:
    s = [r for r in recs if r["n"] == n]
    L.append(f"| {n} | {len(s)} | {sum(r['hc'] for r in s)} | {sum(r['route'] in ('apply', 'tcad_verify') and not r['hc'] for r in s)} | {sum(r['route'] == 'manual' for r in s)} |")
L += ["", "## 3. high_confidence 의 근사 정확도 (이웃 TCAD 기준 \"보정 후 규격 안\")", "", "| 웨이퍼 N | 구분 | 이웃 거리 ≤ | 건수 | 이웃이 규격 안 | 이웃이 규격 밖 |", "|---|---|---|---|---|---|"]
for n in NS2:
    for name, f in (("high_confidence", lambda r: r["hc"]), ("고신뢰 아님", lambda r: not r["hc"] and r["route"] == "tcad_verify")):
        for t in TOLS:
            s = [r for r in recs if r["n"] == n and f(r) and r["nn_dist"] <= t]
            L.append(f"| {n} | {name} | {t} | {len(s)} | {sum(r['nn_ok'] for r in s)} | {sum(not r['nn_ok'] for r in s)} |")
L += ["", "읽는 법: high_confidence 줄에서 \"이웃이 규격 밖\"이 0이면 이 근사에서는 오판이 없다. 건수가 적으면 오판율 상한이 크다 (예: 10건 중 0건이면 95 % 상한은 약 26 %).", ""]
L += ["## 4. 기준을 바꿨을 때 (이웃 거리 ≤ 0.05인 건만)", "", "| 규격확률 ≥ | 원인확률 ≥ | 웨이퍼 N | high_confidence 건수 | 이웃 확인 가능 | 이웃이 규격 밖 |", "|---|---|---|---|---|---|"]
def hc_with(r, **over):
    saved = dict(cv.AUTO)
    cv.AUTO.update(over)
    try:
        return r["route"] in ("apply", "tcad_verify") and not cv.confidence_blockers(r["decision"], r["knobs"], r["comp"])
    finally:
        cv.AUTO.clear()
        cv.AUTO.update(saved)
for ps in (0.90, 0.95, 0.99):
    for pc in (0.70, 0.90):
        for n in NS2:
            hc = [r for r in recs if r["n"] == n and hc_with(r, p_spec_after=ps, p_cause=pc)]
            ck = [r for r in hc if r["nn_dist"] <= 0.05]
            L.append(f"| {ps} | {pc} | {n} | {len(hc)} | {len(ck)} | {sum(not r['nn_ok'] for r in ck)} |")
L += ["", "## 5. 한계", "", "- 이웃으로 근사한 판정이다. 보정 후 공정값을 TCAD 로 직접 돌린 것이 아니다 (`결과/소이탈평가_보정후공정값.csv` 에 그 공정값을 저장했다: 2단계 직접 검증용).",
      "- 측정 잡음은 가정값, 데이터는 합성 TCAD 다. 시험 문제는 36개 중 규격 밖으로 확인된 것뿐이라 건수가 적다."]
(OUT / "소이탈평가.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
print(f"총 {time.time() - t0:.0f}초")
