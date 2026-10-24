"""서로게이트 후보 비교용 공통 도구: 데이터 읽기(간의 TCAD 와 같은 데이터·분할), 평가 시험, 지표. TCAD 는 돌리지 않는다."""
import importlib.util
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
GPDIR = HERE.parent / "간의_TCAD_GP"
_f = next(q for q in GPDIR.glob("*.py") if "TCAD" in q.name and "성능" not in q.name and "추가" not in q.name)      # 현재 서로게이트 코드(간의TCAD.py)
_s = importlib.util.spec_from_file_location("ev", _f)
ev = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ev)
ng = ev.ng
TARGET = [ev.TARGET["Vth"], ev.TARGET["gm"], ev.TARGET["Id4V"], ev.TARGET["BV"]]       # 25 mV, 2.5 %, 2.5 %, 0.15 V
ONAME = ["Vth(mV)", "gm(%)", "Id(4V)(%)", "BV(V)"]
ARMN = ["도즈−", "도즈+", "에피−", "에피+", "산화막−", "산화막+"]


def phys(X):
    return np.c_[np.sqrt(X[:, 0]), np.log(X[:, 1]), X[:, 2]]


def arm_of(x):
    d = np.abs(x - 1)
    k = int(np.argmax(d))
    return -1 if d.max() <= 0.3 + 1e-9 else k * 2 + (0 if x[k] < 1 else 1)


def batch_numbers():
    import csv
    rows = list(csv.DictReader(open(ev.ROOT / "대량작업2" / "대량실행" / "결과" / "대량실행_결과_N146.csv", encoding="utf-8-sig")))
    return np.array([int(r["번호"]) for r in rows if r["상태"] == "ok" and ev.sp.in_domain(float(r["바디도즈비율"]), float(r["에피도핑비율"]), float(r["산화막비율"]))])


class Data:
    def __init__(self):
        self.Xb, self.yb, layer = ev.load_batch()
        self.Xs, self.ys = ev.load_single()
        ins = np.array([ev.sp.in_domain(*x) for x in self.Xs])
        self.ys_tr = self.ys.copy()
        self.ys_tr[~ins, 3] = np.nan                       # 영역 밖 단일 노브 점은 BV 학습에 쓰지 않는다 (현재 방식과 같다)
        self.num = batch_numbers()
        self.arms = np.array([arm_of(x) for x in self.Xb])
        self.sarms = np.array([arm_of(x) for x in self.Xs])
        self.inn = np.all(np.abs(self.Xs - 1) <= 0.3 + 1e-9, axis=1)

    def noisy(self, y, scale, rng):
        o = y.copy()
        o[:, 0] += rng.normal(0, ng.NOISE["vth"][1] * scale, len(y))
        o[:, 1] += np.log1p(rng.normal(0, ng.NOISE["gm"][1] * scale, len(y)))
        o[:, 2] += np.log1p(rng.normal(0, ng.NOISE["id_4v"][1] * scale, len(y)))
        o[:, 3] += rng.normal(0, ng.NOISE["bv"][1] * scale, len(y))
        return o


def stats(P, S, T):
    """예측 P, 불확실도 S(없으면 NaN), 실제 T (n×4) -> 출력별 RMSE, MAE, 95 %, 2σ 포함률, 오차/σ RMS"""
    out = []
    for j in range(4):
        ok = ~np.isnan(T[:, j])
        e = ev.err(P[ok, j], T[ok, j], j)
        d = dict(rmse=ev.rms(e), mae=float(np.mean(np.abs(e))), p95=float(np.percentile(np.abs(e), 95)), n=int(ok.sum()))
        s = S[ok, j]
        if np.all(np.isfinite(s)) and np.all(s > 0):
            z = np.abs(P[ok, j] - T[ok, j]) / s
            d.update(cov2=float(np.mean(z <= 2)), zrms=float(np.sqrt(np.mean(z ** 2))))
        else:
            d.update(cov2=None, zrms=None)
        out.append(d)
    return out


def evaluate(fit_predict, D, slow=False, seeds=(0, 1), do_arms=True, do_noise=True, log=print):
    """fit_predict(Xtr, Ytr, Xte) -> (P, S) (n×4). 후보 모델의 모든 시험을 한 번에 돌린다."""
    from sklearn.model_selection import KFold
    R = {}
    n = len(D.Xb)
    # 1) 교차검증
    PP, SS, TT = [], [], []
    for sd in seeds:
        for tr, te in KFold(5, shuffle=True, random_state=sd).split(D.Xb):
            P, S = fit_predict(np.vstack([D.Xb[tr], D.Xs]), np.vstack([D.yb[tr], D.ys_tr]), D.Xb[te])
            PP.append(P), SS.append(S), TT.append(D.yb[te])
        log(f"  CV seed {sd}")
    R["cv"] = stats(np.vstack(PP), np.vstack(SS), np.vstack(TT))
    # 2) 단일 노브 ±30 % 바깥 외삽
    P, S = fit_predict(np.vstack([D.Xb, D.Xs[D.inn]]), np.vstack([D.yb, D.ys_tr[D.inn]]), D.Xs[~D.inn])
    R["extrap"] = stats(P, S, D.ys[~D.inn])
    log("  외삽 끝")
    # 3) 팔 하나를 통째로 빼기
    if do_arms:
        R["arms"] = {}
        for a in range(6):
            te = D.arms == a
            if not te.any():
                continue
            keep = D.sarms != a
            P, S = fit_predict(np.vstack([D.Xb[~te], D.Xs[keep]]), np.vstack([D.yb[~te], D.ys_tr[keep]]), D.Xb[te])
            R["arms"][ARMN[a]] = stats(P, S, D.yb[te])
        log("  팔 끝")
    # 4) 사후 검증: 첫 배치(1~120) -> 둘째 배치
    old = D.num <= 120
    P, S = fit_predict(np.vstack([D.Xb[old], D.Xs]), np.vstack([D.yb[old], D.ys_tr]), D.Xb[~old])
    R["posthoc"] = stats(P, S, D.yb[~old])
    log("  사후 검증 끝")
    # 5) 가정 잡음이 섞인 값으로 학습 (한 번의 잡음 추출, 5-겹 1회)
    if do_noise:
        rng = np.random.default_rng(0)
        PP, SS, TT = [], [], []
        for tr, te in KFold(5, shuffle=True, random_state=0).split(D.Xb):
            Ytr = np.vstack([D.noisy(D.yb[tr], 1.0, rng), D.noisy(D.ys_tr, 1.0, rng)])
            P, S = fit_predict(np.vstack([D.Xb[tr], D.Xs]), Ytr, D.Xb[te])
            PP.append(P), SS.append(S), TT.append(D.yb[te])
        R["noise1"] = stats(np.vstack(PP), np.vstack(SS), np.vstack(TT))
        log("  잡음 학습 끝")
    return R
