"""EDA 보고서(워드)용 추가 분석. 학습데이터_최종.csv 만 읽고 TCAD 는 돌리지 않는다. 결과/추가분석.json, 결과/추가_*.png
  python 추가분석.py
"""
import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = HERE / "결과"
ROOT = next(p for p in (HERE, *HERE.parents) if (p / "최종_trench_template.in").exists())
sys.path[:0] = [str(ROOT / "고칠것6" / "구분가능성")]
import 노이즈가정 as ng

EV = next(q for q in (HERE.parent / "간의_TCAD").glob("*.py") if "TCAD" in q.name and "성능" not in q.name and "추가" not in q.name)
spec = importlib.util.spec_from_file_location("ev", EV)
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)

rows = list(csv.DictReader(open(ROOT / "대량작업2" / "학습데이터" / "결과" / "학습데이터_최종.csv", encoding="utf-8-sig")))
f = lambda r, k: float(r[k]) if r[k] not in ("", None) else np.nan
B = [r for r in rows if r["출처"] == "대량실행" and r["영역안"] == "True"]
X = np.array([[f(r, "바디도즈비율"), f(r, "에피도핑비율"), f(r, "산화막비율")] for r in B])
Y = np.array([[f(r, "Vth"), np.log(f(r, "gm")), np.log(f(r, "Id4V")), f(r, "BV_1e-9")] for r in B])
core = np.array([r["층"] == "코어" for r in B])
J = {}
names = ["Vth", "ln gm", "ln Id(4V)", "BV"]


def r2(F, y, mask):
    ok = mask & ~np.isnan(y)
    A = np.c_[np.ones(ok.sum()), F[ok]]
    c, *_ = np.linalg.lstsq(A, y[ok], rcond=None)
    res = y[ok] - A @ c
    return float(1 - res.var() / y[ok].var()), float(res.std())


# 1. 선형 설명력 (원래 입력 / 물리 변환 입력 / 2차항 포함), 코어만과 전체
phys = np.c_[np.sqrt(X[:, 0]), np.log(X[:, 1]), X[:, 2]]
quad = np.c_[phys, phys ** 2, phys[:, 0] * phys[:, 1], phys[:, 0] * phys[:, 2], phys[:, 1] * phys[:, 2]]
J["lin"] = {nm: {"raw_core": r2(X, Y[:, j], core), "phys_core": r2(phys, Y[:, j], core), "phys_all": r2(phys, Y[:, j], core | ~core), "quad_all": r2(quad, Y[:, j], core | ~core)} for j, nm in enumerate(names)}

# 2. 표준화 회귀계수 (물리 변환 입력, 전체) = 노브 한 표준편차가 출력을 몇 표준편차 움직이는가
Z = (phys - phys.mean(0)) / phys.std(0)
J["beta"] = {}
for j, nm in enumerate(names):
    ok = ~np.isnan(Y[:, j])
    yz = (Y[ok, j] - Y[ok, j].mean()) / Y[ok, j].std()
    c, *_ = np.linalg.lstsq(np.c_[np.ones(ok.sum()), Z[ok]], yz, rcond=None)
    J["beta"][nm] = [float(v) for v in c[1:]]

# 3. 기준값 근처 국소 민감도 (최종 GP 로, 노브 +1 % 때 출력 변화) 와 가정 잡음 대비 신호 대 잡음
import joblib

M = joblib.load(OUT.parent.parent / "간의_TCAD" / "결과" / "서로게이트_GP.joblib")["models"]


def pred(x):
    x = np.atleast_2d(x)
    ph = np.c_[np.sqrt(x[:, 0]), np.log(x[:, 1]), x[:, 2]]
    v = M["vth"].predict(ph)
    g = M["log_gm"].predict(ph)
    i = M["log_id4v"].predict(np.c_[ph, v])
    b = M["bv"].predict(ph)
    return np.c_[v, g, i, b]


base = pred([1, 1, 1])[0]
sens = {}
for k, nm in enumerate(["바디 도즈", "에피 도핑", "산화막"]):
    up, dn = np.ones(3), np.ones(3)
    up[k], dn[k] = 1.01, 0.99
    dp = (pred(up)[0] - pred(dn)[0]) / 0.02
    sens[nm] = dp.tolist()                       # 비율 1 변화당 출력 변화 (x 0.01 하면 1 % 당)
J["base"] = base.tolist()
J["sens_per_pct"] = {k: [v * 0.01 for v in vv] for k, vv in sens.items()}
noise = [ng.NOISE["vth"][1], ng.NOISE["gm"][1], ng.NOISE["id_4v"][1], ng.NOISE["bv"][1]]     # 절대 V / 상대 / 상대 / 절대 V (gm·Id 는 로그 기준 상대와 같은 크기)
J["noise"] = noise
J["snr_per_pct"] = {k: [abs(v * 0.01) / n for v, n in zip(vv, noise)] for k, vv in sens.items()}

# 4. 주성분 (출력 4개 중 BV 가 있는 샘플 / 3개 전체)
def pca(M_):
    Zs = (M_ - M_.mean(0)) / M_.std(0)
    w, v = np.linalg.eigh(np.cov(Zs.T))
    o = np.argsort(-w)
    return (w[o] / w.sum()).tolist(), v[:, o].T.tolist()


J["pca3"] = pca(Y[:, :3])
ok = ~np.isnan(Y[:, 3])
J["pca4"] = pca(Y[ok])

# 5. 편상관 (노브 영향을 제거한 출력 간 상관) = 출력 간 남는 정보
res = []
for j in range(4):
    okj = ~np.isnan(Y[:, j])
    res.append(None)
ok4 = ~np.isnan(Y[:, 3])
Rm = np.zeros((4, 4))
Rs = []
for j in range(4):
    c, *_ = np.linalg.lstsq(np.c_[np.ones(ok4.sum()), quad[ok4]], Y[ok4, j], rcond=None)
    Rs.append(Y[ok4, j] - np.c_[np.ones(ok4.sum()), quad[ok4]] @ c)
J["resid_corr"] = np.corrcoef(np.array(Rs)).tolist()

# 6. 분포 모양
from scipy import stats
J["shape"] = {nm: {"skew": float(stats.skew(Y[~np.isnan(Y[:, j]), j])), "kurt": float(stats.kurtosis(Y[~np.isnan(Y[:, j]), j])), "std": float(np.nanstd(Y[:, j])), "min": float(np.nanmin(Y[:, j])), "max": float(np.nanmax(Y[:, j]))} for j, nm in enumerate(names)}

# 7. 스펙 판정 결합: Vth 스펙(1.7~2.6 V), BV 스펙(≥ 40 V)
vs = (Y[:, 0] >= 1.7) & (Y[:, 0] <= 2.6)
bs = Y[:, 3] >= 40
okb = ~np.isnan(Y[:, 3])
J["spec"] = {"vth_pass": int(vs.sum()), "n": len(vs), "vth_low": int((Y[:, 0] < 1.7).sum()), "vth_high": int((Y[:, 0] > 2.6).sum()),
             "bv_n": int(okb.sum()), "bv_pass": int(bs[okb].sum()), "both_pass_among_bv": int((vs & bs)[okb].sum()),
             "vth_fail_but_bv_pass": int((~vs & bs)[okb].sum()), "vth_pass_but_bv_fail": int((vs & ~bs)[okb].sum()), "both_fail": int((~vs & ~bs)[okb].sum())}
# 불량 원인 분해: Vth 스펙 이탈 샘플에서 어떤 노브가 가장 크게 벗어났는가 (|비율-1| 최댓값)
dev = np.abs(X - 1)
cause = np.argmax(dev, axis=1)
fail = ~vs
J["vth_fail_cause"] = {k: int(((cause == i) & fail).sum()) for i, k in enumerate(["바디 도즈", "에피 도핑", "산화막"])}
# Vth 이탈이 두 노브 이상 비슷하게 기여하는지(상대 영향 비율)
# 8. 설계 점검: 코어 3차원 최근접 거리, 가장 큰 빈 공간(몬테카를로)
C = X[core]
from scipy.spatial import cKDTree
t = cKDTree(C)
d, _ = t.query(C, k=2)
rng = np.random.default_rng(0)
G = rng.uniform(0.7, 1.3, (100000, 3))
dg, _ = t.query(G)
J["design"] = {"n_core": int(core.sum()), "nn_mean": float(d[:, 1].mean()), "nn_min": float(d[:, 1].min()), "empty_max": float(dg.max()), "empty_p95": float(np.percentile(dg, 95)), "empty_mean": float(dg.mean())}
# 9. 코어와 확장의 출력 이동
J["core_vs_ext"] = {nm: {"core_mean": float(np.nanmean(Y[core, j])), "ext_mean": float(np.nanmean(Y[~core, j])), "core_std": float(np.nanstd(Y[core, j])), "ext_std": float(np.nanstd(Y[~core, j]))} for j, nm in enumerate(names)}
# 10. 비선형성: 단일 노브 곡선에서 선형 대비 최대 편차
single = [r for r in rows if r["출처"] == "단일노브" and r["영역안"] == "True"]
J["single_curv"] = {}
for k, col in enumerate(["바디도즈비율", "에피도핑비율", "산화막비율"]):
    pts = sorted([(f(r, col), f(r, "Vth"), np.log(f(r, "gm")), f(r, "BV_1e-9")) for r in single if abs(f(r, col) - 1) > 1e-9] + [(1.0, J["base"][0], J["base"][1], J["base"][3])])
    arr = np.array(pts)
    out = []
    for j in (1, 2, 3):
        ok = ~np.isnan(arr[:, j])
        if ok.sum() >= 4:
            A = np.c_[np.ones(ok.sum()), arr[ok, 0]]
            c, *_ = np.linalg.lstsq(A, arr[ok, j], rcond=None)
            out.append(float(np.abs(arr[ok, j] - A @ c).max() / (arr[ok, j].max() - arr[ok, j].min())))
        else:
            out.append(None)
    J["single_curv"][["도즈", "에피", "산화막"][k]] = out
# 11. 입력 쌍별 상호작용: GP 로 노브 2개를 동시에 +20 % 올렸을 때 가산 예측과의 차이 (코어 안)
inter = {}
for a, b, nm in [(0, 1, "도즈×에피"), (0, 2, "도즈×산화막"), (1, 2, "에피×산화막")]:
    for sa, sb in [(1.2, 1.2), (0.8, 0.8), (1.2, 0.8), (0.8, 1.2)]:
        xa, xb, xab = np.ones(3), np.ones(3), np.ones(3)
        xa[a], xb[b], xab[a], xab[b] = sa, sb, sa, sb
        dd = pred(xab)[0] - (pred(xa)[0] + pred(xb)[0] - base)
        inter.setdefault(nm, []).append(dd.tolist())
J["interaction"] = {k: np.abs(np.array(v)).max(0).tolist() for k, v in inter.items()}
# 12. 노이즈 대비: 학습 영역에서 출력의 표준편차 / 가정 잡음
J["signal_over_noise"] = {nm: float(np.nanstd(Y[:, j]) / noise[j]) for j, nm in enumerate(names)}
(OUT / "추가분석.json").write_text(json.dumps(J, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps(J, ensure_ascii=False, indent=1)[:6000])
