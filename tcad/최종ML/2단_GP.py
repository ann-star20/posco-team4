"""서로게이트 실행용 모듈 (Jetson 에 가져갈 파일). NumPy 만 쓴다 (sklearn·scipy·torch 불필요).

노브 3개 (기준값 대비 비율) -> Vth(V), gm(A/V/μm), Id(4V)(A/μm), BV(V) 와 보정된 불확실도.
  - 학습 영역(in_domain) 밖이면 값을 내지 않거나(strict) 경고를 붙인다.
  - GP 는 float64 로만 계산한다 (float32 로 내리면 평균이 크게 어긋난다).

사용:
    from 서로게이트 import Surrogate
    s = Surrogate()                                   # 모델/ 폴더의 파일을 읽는다
    r = s.predict([[1.0, 1.0, 1.0], [0.9, 1.1, 1.0]])
    r["vth"], r["sigma_vth"], r["in_domain"]
    python 서로게이트.py                               # 자체 점검
"""
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT_NAMES = ("vth", "gm", "id4v", "bv")


def _matern52(A, B, ls):
    A, B = A / ls, B / ls
    d2 = (A * A).sum(1)[:, None] + (B * B).sum(1)[None, :] - 2 * A @ B.T
    d = np.sqrt(np.maximum(d2, 0))
    return (1 + np.sqrt(5) * d + 5 * d ** 2 / 3) * np.exp(-np.sqrt(5) * d)


class _GP:
    """학습된 GP 하나 (Matern 5/2 ARD + 잡음). 평균과 표준편차를 NumPy 행렬 연산으로 계산."""

    def __init__(self, p):
        self.X, self.alpha, self.Linv, self.ls = p["X"], p["alpha"], p["Linv"], p["ls"]
        self.c, self.noise, self.ymean, self.ystd = float(p["c"]), float(p["noise"]), float(p["ymean"]), float(p["ystd"])

    def predict(self, F):
        K = self.c * _matern52(F, self.X, self.ls)
        V = K @ self.Linv.T
        mean = (K @ self.alpha) * self.ystd + self.ymean
        var = (self.c + self.noise) - (V * V).sum(1)
        return mean, np.sqrt(np.maximum(var, 0)) * self.ystd


def features(X, kind):
    """입력 변환. 'phys' = [√도즈, ln 에피, 산화막], 'raw' = 원래 비율, 'dlogepi' = [도즈, ln 에피, 산화막]"""
    X = np.asarray(X, float)
    if kind == "phys":
        return np.c_[np.sqrt(X[:, 0]), np.log(X[:, 1]), X[:, 2]]
    if kind == "dlogepi":
        return np.c_[X[:, 0], np.log(X[:, 1]), X[:, 2]]
    return X


class Domain:
    """학습 영역 판정 (대량작업2/샘플링계획.py 의 in_domain 과 같은 규칙, 파일 의존 없이 계산)."""

    def __init__(self, d):
        self.core, self.verified, self.vth_min = d["core"], d["verified"], d["vth_min"]
        self.punch_dose, self.punch_epi = d["punch_dose"], d["punch_epi"]
        self.base = d["vth_base"]
        self.curves = {k: (np.array([a for a, _ in v]), np.array([b for _, b in v])) for k, v in d["vth_curves"].items()}

    def vth_additive(self, X):
        return self.base + sum(np.interp(X[:, i], *self.curves[k]) - self.base for i, k in enumerate(("dose", "epi", "tox")))

    def __call__(self, X):
        X = np.asarray(X, float).reshape(-1, 3)
        lo, hi = self.core
        out = np.zeros_like(X, bool)
        vok = np.ones(len(X), bool)
        for i, k in enumerate(("dose", "epi", "tox")):
            out[:, i] = (X[:, i] < lo - 1e-9) | (X[:, i] > hi + 1e-9)
            a, b = self.verified[k]
            vok &= ~out[:, i] | ((X[:, i] >= a - 1e-9) & (X[:, i] <= b + 1e-9))
        geom = (out.sum(1) == 0) | ((out.sum(1) == 1) & vok)
        punch = (X[:, 0] < self.punch_dose) & (X[:, 1] > self.punch_epi)
        return geom & (self.vth_additive(X) >= self.vth_min - 1e-9) & ~punch


class Surrogate:
    def __init__(self, folder=None, chunk=20000):
        folder = Path(folder) if folder else HERE / "모델"
        z = np.load(folder / "gp.npz")
        self.info = json.loads((folder / "모델정보.json").read_text(encoding="utf-8"))
        self.gp = {k: _GP({f: z[f"{k}__{f}"] for f in ("X", "alpha", "Linv", "ls", "c", "noise", "ymean", "ystd")}) for k in ("vth", "log_gm", "log_id4v", "bv")}
        self.domain = Domain(json.loads((folder / "영역.json").read_text(encoding="utf-8")))
        self.cal = self.info["보정배율"]          # 출력별 σ 보정 배율 (교차검증의 오차÷σ RMS)
        self.bv_input, self.bv_log = self.info["BV입력"], self.info["BV로그"]
        self.chunk = chunk

    def _raw(self, X):
        f = features(X, "phys")
        v, sv = self.gp["vth"].predict(f)
        g, sg = self.gp["log_gm"].predict(f)
        i, si = self.gp["log_id4v"].predict(np.c_[f, v])
        b, sb = self.gp["bv"].predict(features(X, self.bv_input))
        if self.bv_log:
            b, sb = np.exp(b), np.exp(b) * sb
        return v, sv, g, sg, i, si, b, sb

    def predict(self, X, strict=True):
        """X: (n,3) [도즈, 에피, 산화막] 비율. strict=True 면 영역 밖 행의 모든 출력을 NaN 으로 한다.
        돌려주는 값: vth(V), gm(A/V/μm), id4v(A/μm), bv(V), sigma_*(보정된 σ: Vth·BV 는 V, gm·Id 는 상대값), in_domain(bool)"""
        X = np.asarray(X, float).reshape(-1, 3)
        parts = [self._raw(X[i:i + self.chunk]) for i in range(0, len(X), self.chunk)]
        v, sv, g, sg, i, si, b, sb = (np.concatenate([p[k] for p in parts]) for k in range(8))
        c = self.cal
        r = dict(vth=v, gm=np.exp(g), id4v=np.exp(i), bv=b, sigma_vth=sv * c["vth"], sigma_gm=sg * c["gm"], sigma_id4v=si * c["id4v"], sigma_bv=sb * c["bv"], in_domain=self.domain(X))
        if strict:
            for k in r:
                if k != "in_domain":
                    r[k] = np.where(r["in_domain"], r[k], np.nan)
        return r


    def raw_calibrated(self, X):
        """로그 영역 그대로의 예측: (평균 n×4 = [Vth(V), ln gm, ln Id, BV(V)], 보정된 σ n×4). 영역 마스크 없음. 고정밀 모드가 두 모델을 합칠 때 쓴다."""
        X = np.asarray(X, float).reshape(-1, 3)
        parts = [self._raw(X[i:i + self.chunk]) for i in range(0, len(X), self.chunk)]
        v, sv, g, sg, i, si, b, sb = (np.concatenate([q[k] for q in parts]) for k in range(8))
        c = self.cal
        return np.c_[v, g, i, b], np.c_[sv * c["vth"], sg * c["gm"], si * c["id4v"], sb * c["bv"]]


def selftest():
    s = Surrogate()
    r = s.predict([[1, 1, 1], [1.0, 1.0, 1.2], [0.75, 1.6, 1.0], [1.2, 0.3, 1.0], [2.0, 1.0, 1.0]])
    assert r["in_domain"].tolist() == [True, True, False, True, False], r["in_domain"]       # 펀치스루 구석·너무 먼 점은 영역 밖
    assert np.isnan(r["vth"][2]) and np.isnan(r["bv"][4]) and abs(r["vth"][0] - s.info["기준값"]["vth"]) < 0.02
    rr = s.predict([[0.75, 1.6, 1.0]], strict=False)
    assert np.isfinite(rr["vth"][0]) and not rr["in_domain"][0]
    big = np.tile([[1.0, 1.0, 1.0]], (50000, 1))                                            # 청크 처리
    assert np.allclose(s.predict(big)["vth"], r["vth"][0])
    print("서로게이트 점검 통과: 기준값 예측 Vth %.3f V, gm %.3e, Id %.3e, BV %.1f V" % (r["vth"][0], r["gm"][0], r["id4v"][0], r["bv"][0]))


if __name__ == "__main__":
    selftest()
