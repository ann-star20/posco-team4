"""고정밀 모드: 2단 GP 와 TabPFN v2 를 정밀도 가중 평균으로 합친다 (비교 실험의 13번 모델). 후보를 수십 개로 좁힌 뒤 최종 확인에만 쓴다.
  - 기본 모드(GP)가 먼저 수만 개 후보를 평가하고, 이 모드는 남은 후보 몇 개~100개에만 쓴다 (TabPFN 은 호출당 약 6초 고정 비용 + 점당 약 0.03초, CPU 기준).
  - 필요: torch, tabpfn(9.x). 가중치는 모델/tabpfn/tabpfn-v2-regressor.ckpt (44 MB, 로그인·키 불필요). 없으면 기본 모드로 되돌린다 (ml_파이프라인.py).
  - TabPFN 은 입력 [√도즈, ln 에피, 산화막]을 쓰고 Id 는 TabPFN 자신의 Vth 예측을 입력에 더한 2단 구조 (학습 때는 실제 Vth).
  - 합치기: 출력마다 가중치 ∝ 1/σ² (GP 는 보정된 σ, TabPFN 은 84 %−16 % 분위수 폭/2), 합친 σ = sqrt(1/(w_GP + w_Tab)).
"""
import importlib.util
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def combine(Pg, Sg, Pt, St):
    """두 모델의 평균·σ (n×4) 를 정밀도 가중 평균으로 합친다. 합친 평균, 합친 σ 를 돌려준다."""
    wg, wt = 1 / np.maximum(Sg, 1e-12) ** 2, 1 / np.maximum(St, 1e-12) ** 2
    return (wg * Pg + wt * Pt) / (wg + wt), np.sqrt(1 / (wg + wt))


def _phys(X):
    X = np.asarray(X, float)
    return np.c_[np.sqrt(X[:, 0]), np.log(X[:, 1]), X[:, 2]]


class HighPrecision:
    def __init__(self, surrogate, train_npz=None, weights=None, device="auto"):
        w = Path(weights) if weights else HERE / "모델" / "tabpfn" / "tabpfn-v2-regressor.ckpt"
        if not w.exists():                                             # torch 를 불러오기 전에 바로 실패시킨다 (무거운 import 와 인터넷 내려받기 시도를 피함). 호출한 쪽이 기본 모드로 되돌아간다
            raise FileNotFoundError(f"TabPFN 가중치 파일이 없다: {w} (고정밀 모드를 쓰지 않으면 무시해도 기본 모드로 동작한다)")
        from tabpfn import TabPFNRegressor
        from tabpfn.constants import ModelVersion
        self.sur = surrogate
        z = np.load(train_npz or HERE / "모델" / "학습배열.npz")
        X, Y = z["X"], z["Y"]
        make = lambda: TabPFNRegressor.create_default_for_version(ModelVersion.V2, device=device, model_path=str(w))        # 비교 실험과 같은 v2 기본 설정
        f = _phys(X)
        self.m = []
        for j in range(4):
            ok = ~np.isnan(Y[:, j])
            F = np.c_[f[ok], Y[ok, 0]] if j == 2 else f[ok]
            self.m.append(make().fit(F, Y[ok, j]))

    def _tab(self, X):
        f = _phys(X)
        P, S = np.zeros((len(f), 4)), np.zeros((len(f), 4))
        vth = None
        for j in range(4):
            F = np.c_[f, vth] if j == 2 else f
            q = np.asarray(self.m[j].predict(F, output_type="quantiles", quantiles=[0.1587, 0.5, 0.8413]))
            p = np.asarray(self.m[j].predict(F))
            if j == 0:
                vth = p
            P[:, j], S[:, j] = p, np.maximum((q[2] - q[0]) / 2, 1e-12)
        return P, S

    def predict(self, X, strict=True):
        """Surrogate.predict 와 같은 형식 + 고정밀 모드의 평균·σ. 영역 밖(strict)이면 NaN."""
        X = np.asarray(X, float).reshape(-1, 3)
        Pg, Sg = self.sur.raw_calibrated(X)
        Pt, St = self._tab(X)
        P, S = combine(Pg, Sg, Pt, St)
        c = self.sur.info.get("고정밀보정배율", {})                        # 고정밀 모드의 σ 보정 배율 (고정밀_점검.py 가 교차검증으로 구해 모델정보.json 에 기록)
        S = S * np.array([c.get(k, 1.0) for k in ("vth", "gm", "id4v", "bv")])
        dom = self.sur.domain(X)
        r = dict(vth=P[:, 0], gm=np.exp(P[:, 1]), id4v=np.exp(P[:, 2]), bv=P[:, 3], sigma_vth=S[:, 0], sigma_gm=S[:, 1], sigma_id4v=S[:, 2], sigma_bv=S[:, 3], in_domain=dom,
                 gp_vth=Pg[:, 0], gp_bv=Pg[:, 3], tabpfn_vth=Pt[:, 0], tabpfn_bv=Pt[:, 3])
        if strict:
            for k in r:
                if k != "in_domain":
                    r[k] = np.where(dom, r[k], np.nan)
        return r


def selftest_combine():
    Pg, Sg, Pt, St = np.array([[1.0, 2.0]]), np.array([[0.1, 1.0]]), np.array([[2.0, 4.0]]), np.array([[0.1, 1.0]])
    P, S = combine(Pg, Sg, Pt, St)
    assert np.allclose(P, [[1.5, 3.0]]) and np.allclose(S, 0.1 / np.sqrt(2) * np.array([[1, 10]]))            # 같은 σ 면 단순 평균, σ 는 1/√2 배
    P, S = combine(np.array([[1.0]]), np.array([[0.01]]), np.array([[5.0]]), np.array([[1.0]]))
    assert abs(P[0, 0] - 1.0) < 0.001                                                                         # σ 가 작은 쪽이 지배
    print("합치기 규칙 점검 통과")


if __name__ == "__main__":
    selftest_combine()
