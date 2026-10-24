"""성능 보고서(워드)용 추가 평가. 성능보고서.py 가 저장한 교차검증 결과(결과/성능_평가.npz)와 최종 GP 를 쓴다.
노이즈를 입힌 학습 시험만 GP 를 다시 학습한다(약 1분). 결과/추가성능.json
  python 추가성능분석.py
"""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = next(p for p in (HERE, *HERE.parents) if (p / "최종_trench_template.in").exists())


def load(pattern_ok):
    q = next(q for q in HERE.glob("*.py") if pattern_ok(q.name))
    s = importlib.util.spec_from_file_location("m_" + str(abs(hash(q.name))), q)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


ev = load(lambda n: "TCAD" in n and "성능" not in n and "추가" not in n)
OUT = ev.OUT
D = np.load(OUT / "성능_평가.npz", allow_pickle=False)
Xb, yb, P3, S3 = D["Xb"], D["yb"], D["P3"], D["S3"]
P = P3.mean(0)
J = {}
names = ["Vth", "ln gm", "ln Id(4V)", "BV"]
ng = ev.ng
noise = [ng.NOISE["vth"][1], ng.NOISE["gm"][1], ng.NOISE["id_4v"][1], ng.NOISE["bv"][1]]

# 1. 오차 / 가정 측정 잡음
J["err_vs_noise"] = {}
for j, nm in enumerate(names):
    ok = ~np.isnan(yb[:, j])
    e = (P[ok, j] - yb[ok, j])
    sc = 1 if j in (0, 3) else 1              # Vth·BV 는 V, ln gm·ln Id 는 로그 = 상대 오차
    J["err_vs_noise"][nm] = float(np.sqrt(np.mean(e ** 2)) / noise[j])

# 2. 로트(웨이퍼 N 개 평균) 수준: 측정 잡음은 1/sqrt(N)로 줄지만 서로게이트 오차는 줄지 않는다
J["lot"] = {}
for j, nm in enumerate(names):
    ok = ~np.isnan(yb[:, j])
    e = float(np.sqrt(np.mean((P[ok, j] - yb[ok, j]) ** 2)))
    J["lot"][nm] = {"model_err": e, **{f"noise_N{N}": noise[j] / np.sqrt(N) for N in (1, 5, 25, 100)}}

# 3. 잔차 모양: 정규성, 기준값에서 멀수록 오차가 커지는가
from scipy import stats
dist = np.linalg.norm(np.c_[np.sqrt(Xb[:, 0]) - 1, np.log(Xb[:, 1]), Xb[:, 2] - 1], axis=1)
J["resid"] = {}
for j, nm in enumerate(names):
    ok = ~np.isnan(yb[:, j])
    e = P[ok, j] - yb[ok, j]
    J["resid"][nm] = {"kurt": float(stats.kurtosis(e)), "skew": float(stats.skew(e)), "shapiro_p": float(stats.shapiro(e)[1]),
                      "spearman_absErr_dist": float(stats.spearmanr(np.abs(e), dist[ok])[0]), "frac_gt_3sd": float(np.mean(np.abs(e) > 3 * e.std()))}

# 4. 합격/불합격 판정 정확도 (Vth 1.7~2.6 V, BV ≥ 40 V) — 교차검증 예측으로
vt, vp = yb[:, 0], P[:, 0]
ts, ps = (vt >= 1.7) & (vt <= 2.6), (vp >= 1.7) & (vp <= 2.6)
okb = ~np.isnan(yb[:, 3])
bt, bp = yb[okb, 3] >= 40, P[okb, 3] >= 40
J["spec_cls"] = {"vth_acc": float(np.mean(ts == ps)), "vth_err_n": int(np.sum(ts != ps)), "n": len(ts),
                 "vth_near_boundary_err": [float(np.min(np.minimum(abs(vt[i] - 1.7), abs(vt[i] - 2.6)))) for i in np.where(ts != ps)[0]],
                 "bv_acc": float(np.mean(bt == bp)), "bv_err_n": int(np.sum(bt != bp)), "bv_n": int(okb.sum()),
                 "bv_near_boundary_err": [float(abs(yb[okb, 3][i] - 40)) for i in np.where(bt != bp)[0]]}

# 5. 학습된 GP 의 커널 길이 척도 (작을수록 그 입력에 민감하게 변하는 함수)
import joblib

fitted = joblib.load(OUT / "서로게이트_GP.joblib")["models"]
J["kernel"] = {}
for key, nm in (("vth", "Vth"), ("log_gm", "ln gm"), ("log_id4v", "ln Id(4V)"), ("bv", "BV")):
    k = fitted[key].kernel_
    ls = None
    wn = None
    for part in (k.k1.k2, ) if hasattr(k, "k1") and hasattr(k.k1, "k2") else ():
        ls = [float(v) for v in np.atleast_1d(part.length_scale)]
    if hasattr(k, "k2") and hasattr(k.k2, "noise_level"):
        wn = float(k.k2.noise_level)
    J["kernel"][nm] = {"length_scale": ls, "white_noise": wn, "n_train": int(len(fitted[key].X_train_))}

# 6. 노이즈 낀 학습 데이터로 학습했을 때 (현실의 측정에 가깝다): 학습 목표값에만 가정 잡음을 입히고 깨끗한 값으로 평가
from sklearn.model_selection import KFold

M = ev.models()
Xs, ys = ev.load_single()
inside = np.array([ev.sp.in_domain(*x) for x in Xs])
ys_tr = ys.copy()
ys_tr[~inside, 3] = np.nan
rng = np.random.default_rng(0)


def noisy(y, scale):
    out = y.copy()
    out[:, 0] += rng.normal(0, ng.NOISE["vth"][1] * scale, len(y))
    out[:, 1] += np.log1p(rng.normal(0, ng.NOISE["gm"][1] * scale, len(y)))
    out[:, 2] += np.log1p(rng.normal(0, ng.NOISE["id_4v"][1] * scale, len(y)))
    out[:, 3] += rng.normal(0, ng.NOISE["bv"][1] * scale, len(y))
    return out


J["noisy_train"] = {}
for scale in (0.0, 0.5, 1.0, 2.0):
    e = [[] for _ in range(4)]
    for tr, te in KFold(5, shuffle=True, random_state=0).split(Xb):
        Ytr = np.vstack([noisy(yb[tr], scale), noisy(ys_tr, scale) if scale else ys_tr])
        Pn, _ = ev.predict_all(M, "2단GP", np.vstack([Xb[tr], Xs]), Ytr, Xb[te])
        for j in range(4):
            ok = ~np.isnan(yb[te, j])
            e[j] += list(ev.err(Pn[ok, j], yb[te, j][ok], j))
    J["noisy_train"][str(scale)] = [ev.rms(v) for v in e]
    print("노이즈 학습", scale, [round(ev.rms(v), 3) for v in e], flush=True)

# 7. 같은 시험을 GP 잡음항 상한을 1.0 으로 넓혀서 (원래 코드는 1e-2 로 제한 -> 잡음이 큰 gm·Id 에서 잡음을 따라 그린다)
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel as C, Matern, WhiteKernel


def gp_wide(d=3):
    return GaussianProcessRegressor(C(1.0) * Matern([0.5] * d, nu=2.5, length_scale_bounds=(0.05, 20)) + WhiteKernel(1e-3, (1e-10, 1.0)), normalize_y=True, n_restarts_optimizer=3, random_state=0)


M2 = dict(M)
M2["GP+변환"], M2["_gp4"] = (lambda: gp_wide(3)), (lambda: gp_wide(4))
J["noisy_train_relaxed"] = {}
for scale in (0.5, 1.0, 2.0):
    e = [[] for _ in range(4)]
    for tr, te in KFold(5, shuffle=True, random_state=0).split(Xb):
        Ytr = np.vstack([noisy(yb[tr], scale), noisy(ys_tr, scale)])
        Pn, _ = ev.predict_all(M2, "2단GP", np.vstack([Xb[tr], Xs]), Ytr, Xb[te])
        for j in range(4):
            ok = ~np.isnan(yb[te, j])
            e[j] += list(ev.err(Pn[ok, j], yb[te, j][ok], j))
    J["noisy_train_relaxed"][str(scale)] = [ev.rms(v) for v in e]
    print("잡음항 완화", scale, [round(ev.rms(v), 3) for v in e], flush=True)
(OUT / "추가성능.json").write_text(json.dumps(J, ensure_ascii=False, indent=1), encoding="utf-8")
print("저장")
