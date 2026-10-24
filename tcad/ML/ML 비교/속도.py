"""배포 형태와 추론 속도. GP 를 sklearn 없이 NumPy(행렬 곱)만으로 계산하도록 내보내고(Jetson 에서 sklearn·scipy 설치 불필요),
MLP 앙상블도 NumPy 로 계산해 이 PC 에서 시간을 잰다. 내보낸 파일 결과/배포_GP.npz 와 이 스크립트의 `bench` 함수를 Jetson 에 가져가서 그대로 돌리면 된다.
  python 속도.py            # 내보내기 + 일치 확인 + 시간 측정 -> 결과/속도.json
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
OUT = Path(__file__).resolve().parent / "결과"


# ------------------------------------------------------------ NumPy 추론 (Jetson 에는 이 부분만 있으면 된다)
def matern52(A, B, ls):
    A, B = A / ls, B / ls
    d2 = (A * A).sum(1)[:, None] + (B * B).sum(1)[None, :] - 2 * A @ B.T
    d = np.sqrt(np.maximum(d2, 0))
    return (1 + np.sqrt(5) * d + 5 * d ** 2 / 3) * np.exp(-np.sqrt(5) * d)


class NPGP:
    def __init__(self, p):
        self.p = {k: np.asarray(v) for k, v in p.items()}

    def predict(self, F):
        p = self.p
        K = p["c"] * matern52(F, p["X"], p["ls"])
        mean = (K @ p["alpha"]) * p["ystd"] + p["ymean"]
        V = K @ p["Linv"].T
        var = (p["c"] + p["noise"]) - (V * V).sum(1)
        return mean, np.sqrt(np.maximum(var, 0)) * p["ystd"]


def export_sklearn(g):
    k = g.kernel_
    n = len(g.X_train_)
    L = g.L_
    Linv = np.linalg.solve(L, np.eye(n))
    return dict(X=g.X_train_, alpha=g.alpha_.ravel(), Linv=Linv, ls=k.k1.k2.length_scale, c=k.k1.k1.constant_value, noise=k.k2.noise_level,
                ymean=float(np.ravel(g._y_train_mean)[0]), ystd=float(np.ravel(g._y_train_std)[0]))


def np_mlp_forward(layers, X):
    h = X
    for i, (W, b) in enumerate(layers):
        h = h @ W + b
        if i < len(layers) - 1:
            h = h / (1 + np.exp(-h))              # SiLU
    return h


def bench(fn, X1, Xn, rep1=300, repn=3):
    t = time.perf_counter()
    for _ in range(rep1):
        fn(X1)
    one = (time.perf_counter() - t) / rep1
    t = time.perf_counter()
    for _ in range(repn):
        fn(Xn)
    return one * 1000, (time.perf_counter() - t) / repn


def main():
    import joblib
    from 공통 import Data, phys
    import 모델들 as M
    D = Data()
    Xtr, Ytr = np.vstack([D.Xb, D.Xs]), np.vstack([D.yb, D.ys_tr])
    rng = np.random.default_rng(0)
    Xn = rng.uniform(0.7, 1.3, (100_000, 3))
    X1 = Xn[:1]
    R = {}
    # 1) 현재 모델(joblib) -> NumPy
    cur = joblib.load(OUT.parent.parent / "간의_TCAD_GP" / "결과" / "서로게이트_GP.joblib")["models"]
    ex = {k: export_sklearn(cur[k]) for k in ("vth", "log_gm", "log_id4v", "bv")}
    np.savez(OUT / "배포_GP.npz", **{f"{k}__{kk}": vv for k, d in ex.items() for kk, vv in d.items()})
    G = {k: NPGP(v) for k, v in ex.items()}

    def np_predict(X):
        f = phys(X)
        v, sv = G["vth"].predict(f)
        g, sg = G["log_gm"].predict(f)
        i, si = G["log_id4v"].predict(np.c_[f, v])
        b, sb = G["bv"].predict(f)
        return np.c_[v, g, i, b], np.c_[sv, sg, si, sb]

    def sk_predict(X):
        f = phys(X)
        v, sv = cur["vth"].predict(f, return_std=True)
        g, sg = cur["log_gm"].predict(f, return_std=True)
        i, si = cur["log_id4v"].predict(np.c_[f, v], return_std=True)
        b, sb = cur["bv"].predict(f, return_std=True)
        return np.c_[v, g, i, b], np.c_[sv, sg, si, sb]
    Pn, Sn = np_predict(Xn[:2000])
    Ps, Ss = sk_predict(Xn[:2000])
    R["np_vs_sklearn_max_mean_diff"] = float(np.abs(Pn - Ps).max())
    R["np_vs_sklearn_max_std_diff"] = float(np.abs(Sn - Ss).max())
    for nm, fn in (("GP sklearn", sk_predict), ("GP NumPy(float64)", np_predict)):
        one, many = bench(fn, X1, Xn)
        R[nm] = dict(ms_per_call_1pt=one, sec_100k=many)
        print(nm, f"1점 {one:.2f} ms, 10만 점 {many:.2f} s", flush=True)
    # float32
    G32 = {k: NPGP({kk: (np.asarray(vv, np.float32) if np.ndim(vv) else np.float32(vv)) for kk, vv in v.items()}) for k, v in ex.items()}

    def np32(X):
        X = X.astype(np.float32)
        f = np.c_[np.sqrt(X[:, 0]), np.log(X[:, 1]), X[:, 2]]
        v, sv = G32["vth"].predict(f)
        g, sg = G32["log_gm"].predict(f)
        i, si = G32["log_id4v"].predict(np.c_[f, v])
        b, sb = G32["bv"].predict(f)
        return np.c_[v, g, i, b]
    one, many = bench(np32, X1, Xn)
    R["GP NumPy(float32)"] = dict(ms_per_call_1pt=one, sec_100k=many, max_diff=float(np.abs(np32(Xn[:2000]) - Pn).max()))
    print("GP float32", f"1점 {one:.2f} ms, 10만 점 {many:.2f} s", flush=True)
    # 2) MLP 앙상블 (전체 데이터 학습 -> NumPy)
    mlp = M.MLPEns().fit(Xtr, Ytr)
    layers = [[(m.weight.detach().numpy().T.astype(np.float64), m.bias.detach().numpy().astype(np.float64)) for m in net if hasattr(m, "weight")] for net in mlp.nets]

    def mlp_np(X):
        f = (phys(X) - mlp.mu) / mlp.sd
        p = np.array([np_mlp_forward(l, f) for l in layers]) * mlp.ys + mlp.ym
        return p.mean(0)
    R["MLP 앙상블 NumPy 일치"] = float(np.abs(mlp_np(Xn[:500]) - mlp.predict(Xn[:500])[0]).max())
    one, many = bench(mlp_np, X1, Xn)
    R["MLP 앙상블 NumPy"] = dict(ms_per_call_1pt=one, sec_100k=many)
    print("MLP NumPy", f"1점 {one:.3f} ms, 10만 점 {many:.2f} s", flush=True)
    # 3) 크기
    R["크기"] = dict(GP_floats=int(sum(np.size(vv) for d in ex.values() for vv in d.values())), MLP_params=int(sum(W.size + b.size for l in layers for W, b in l)))
    # 4) torch (GPU 가 있으면 GPU) 로 같은 계산 (Jetson 에서 GPU 로 돌릴 때의 형태)
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    T = {k: {kk: torch.tensor(np.asarray(vv, np.float32), device=dev) for kk, vv in d.items()} for k, d in ex.items()}

    def tmatern(A, B, ls):
        d = torch.cdist(A / ls, B / ls)
        return (1 + 5 ** 0.5 * d + 5 * d ** 2 / 3) * torch.exp(-5 ** 0.5 * d)

    def tgp(p, F):
        K = p["c"] * tmatern(F, p["X"], p["ls"])
        return (K @ p["alpha"]) * p["ystd"] + p["ymean"]

    def tpred(X):
        with torch.no_grad():
            X = torch.as_tensor(X, dtype=torch.float32, device=dev)
            f = torch.stack([X[:, 0].sqrt(), X[:, 1].log(), X[:, 2]], 1)
            v = tgp(T["vth"], f)
            g = tgp(T["log_gm"], f)
            i = tgp(T["log_id4v"], torch.cat([f, v[:, None]], 1))
            b = tgp(T["bv"], f)
            out = torch.stack([v, g, i, b], 1)
            if dev == "cuda":
                torch.cuda.synchronize()
            return out
    tpred(Xn[:10])
    R["GP torch float32 일치(최대 차이)"] = float(np.abs(tpred(Xn[:2000]).numpy() - Pn).max())
    one, many = bench(tpred, X1, Xn)
    R[f"GP torch({dev}, 평균만)"] = dict(ms_per_call_1pt=one, sec_100k=many)
    print(f"GP torch {dev}", f"1점 {one:.2f} ms, 10만 점 {many:.2f} s", flush=True)
    (OUT / "속도.json").write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(R, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
