"""서로게이트(노브 3개 -> Vth, gm, Id(4V), BV) 후보를 대량 실행 결과(N=120)로 비교하고, 선택한 GP 를 전체 데이터로 학습해 저장한다.
TCAD 는 돌리지 않는다. 판정 기준은 앞에서 정한 대로 가정 측정 잡음(노이즈가정.py)의 0.5 배: Vth 25 mV, gm 2.5 %, Id(4V) 2.5 %, BV 0.15 V.

후보: 선형 / 2차 다항식 / GP(원래 입력) / GP(물리 입력 변환) / 2단 GP(Vth 를 먼저 예측해 Id(4V)의 입력으로) / 작은 DNN 5개 앙상블.
입력 변환(물리): [√바디도즈, log 에피도핑, 산화막두께]  (Vth 는 도즈의 제곱근에 가깝고 BV 는 에피에 로그로 민감하다)
학습 데이터: 대량 실행 120개 + 이미 가진 단일 노브 시험 점(단계시험, ±10 %, 기준값; BV 는 영역 안의 점만). 평가는 대량 실행 샘플 위주.

  python 서로게이트평가.py selftest   # 데이터 읽기와 규칙 점검 (몇 초)
  python 서로게이트평가.py run        # 비교 평가 + 최종 GP 학습·저장 (수 분). 결과/서로게이트평가.md, 그림, 서로게이트_GP.joblib
"""
import csv
import importlib.util
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = next(p for p in (HERE, *HERE.parents) if (p / "최종_trench_template.in").exists())
OUT = HERE / "결과"
sys.path[:0] = [str(ROOT / "고칠것6"), str(ROOT / "고칠것6" / "구분가능성")]
import 노이즈가정 as ng


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ss = _load(ROOT / "대량작업2" / "안전범위시험" / "안전범위시험.py", "safe_range")     # 단일 노브 결과 읽기(PRIOR, step_json, bv_coarse)
sp = _load(ROOT / "대량작업2" / "샘플링계획" / "샘플링계획.py", "sampling_plan")      # in_domain
KN = ("dose", "epi", "tox")
TARGET = {"Vth": 0.5 * ng.sigma_analysis()[0], "gm": 0.5 * ng.sigma_analysis()[1], "Id4V": 0.5 * ng.sigma_analysis()[2], "BV": 0.5 * ng.sigma_analysis()[4]}
NAMES = ["Vth(mV)", "gm(%)", "Id(4V)(%)", "BV(V)"]


# ---------------------------------------------------------------- 데이터
def load_batch(n=146):
    rows = list(csv.DictReader(open(ROOT / "대량작업2" / "대량실행" / "결과" / f"대량실행_결과_N{n}.csv", encoding="utf-8-sig")))
    rows = [r for r in rows if r["상태"] == "ok"]
    rows = [r for r in rows if sp.in_domain(float(r["바디도즈비율"]), float(r["에피도핑비율"]), float(r["산화막비율"]))]     # 펀치스루 구석(126·128·129번)은 학습·평가에서 뺀다
    X = np.array([[float(r["바디도즈비율"]), float(r["에피도핑비율"]), float(r["산화막비율"])] for r in rows])
    y = np.array([[float(r["Vth"]), np.log(float(r["gm"])), np.log(float(r["Id4V"])), float(r["BV_1e-9"]) if r["BV_1e-9"] != "" else np.nan] for r in rows])
    return X, y, [r["층"] for r in rows]


def load_single():
    """단일 노브 시험 점: IV(Vth, gm, Id4V)와 BV. BV 는 B4·B3 를 통과한 점만 (영역 밖 포함 여부는 호출자가 정함)."""
    base = ss.PRIOR["base"]
    pts = {(1.0, 1.0, 1.0): [base[0], np.log(base[1]), np.log(base[2]), base[4]]}
    for k in KN:
        for r in [0.9, 1.1] + [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7]:
            x = [1.0, 1.0, 1.0]
            x[KN.index(k)] = r
            if r in (0.9, 1.1):
                p = ss.PRIOR[(k, r)]
                v = [p[0], np.log(p[1]), np.log(p[2])]
            else:
                j = ss.step_json(k, r)
                if not j or j.get("vth") is None:
                    continue
                v = [j["vth"], np.log(j["gm"]), np.log(j["id4v"])]
            res = ss.bv_coarse(k, r)
            ok_bv = res and res.get("bvt_levels") and all(ss.bv_rules(k, r) or [False])
            bv = ss.bv1(res) if ok_bv else np.nan
            pts[tuple(x)] = v + [bv if bv is not None else np.nan]
    X = np.array(list(pts))
    y = np.array(list(pts.values()), float)
    return X, y


def phys(X):
    return np.c_[np.sqrt(X[:, 0]), np.log(X[:, 1]), X[:, 2]]


# ---------------------------------------------------------------- 모델
def models():
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel as C, Matern, WhiteKernel
    from sklearn.linear_model import LinearRegression, Ridge
    from sklearn.neural_network import MLPRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import PolynomialFeatures, StandardScaler

    def gp(d=3):
        return GaussianProcessRegressor(C(1.0) * Matern([0.5] * d, nu=2.5, length_scale_bounds=(0.05, 20)) + WhiteKernel(1e-6, (1e-10, 1e-2)),
                                        normalize_y=True, n_restarts_optimizer=3, random_state=0)

    class Ens:
        def __init__(s, n=5):
            s.n = n

        def fit(s, X, y):
            s.sx, s.sy = StandardScaler().fit(X), StandardScaler().fit(y.reshape(-1, 1))
            Xn, yn = s.sx.transform(X), s.sy.transform(y.reshape(-1, 1)).ravel()
            s.m = [MLPRegressor(hidden_layer_sizes=(32, 32), activation="tanh", solver="lbfgs", max_iter=5000, alpha=1e-5, random_state=k).fit(Xn, yn) for k in range(s.n)]
            return s

        def predict(s, X, return_std=False):
            p = np.array([s.sy.inverse_transform(m.predict(s.sx.transform(X)).reshape(-1, 1)).ravel() for m in s.m])
            return (p.mean(0), p.std(0)) if return_std else p.mean(0)
    return {"선형": lambda: LinearRegression(), "2차다항": lambda: make_pipeline(PolynomialFeatures(2), Ridge(alpha=1e-6)),
            "GP": lambda: gp(3), "GP+변환": lambda: gp(3), "DNN앙상블": lambda: Ens(), "_gp4": lambda: gp(4)}


def err(pred, true, j):
    return (pred - true) * 1000 if j == 0 else (100 * (np.exp(pred - true) - 1) if j in (1, 2) else pred - true)      # mV, %, %, V


def rms(a):
    return float(np.sqrt(np.mean(np.square(a)))) if len(a) else float("nan")


def predict_all(M, name, Xtr, Ytr, Xte):
    """한 모델 이름으로 4개 출력(Vth, log gm, log Id4V, BV)을 예측해 (예측 4열, 표준편차 4열)로. BV 는 NaN 이 아닌 학습 점만 쓴다."""
    P, S = np.zeros((len(Xte), 4)), np.full((len(Xte), 4), np.nan)
    f = phys if name in ("GP+변환", "2단GP", "DNN앙상블") else (lambda x: x)
    mk = M["GP+변환" if name == "2단GP" else name]
    vth_hat = None
    for j in range(4):
        ok = ~np.isnan(Ytr[:, j])
        if name == "2단GP" and j == 2:
            m = M["_gp4"]().fit(np.c_[f(Xtr[ok]), Ytr[ok, 0]], Ytr[ok, 2])
            p, s = m.predict(np.c_[f(Xte), vth_hat], return_std=True)
        else:
            m = mk().fit(f(Xtr[ok]), Ytr[ok, j])
            out = m.predict(f(Xte), return_std=True) if name not in ("선형", "2차다항") else (m.predict(f(Xte)), None)
            p, s = out
        if j == 0:
            vth_hat = p
        P[:, j] = p
        if s is not None:
            S[:, j] = s
    return P, S


# ---------------------------------------------------------------- 평가
def evaluate():
    from sklearn.model_selection import KFold
    M = models()
    Xb, yb, layer = load_batch()
    Xs, ys = load_single()
    layer = np.array(layer)
    print(f"대량 실행 {len(Xb)}개(코어 {np.sum(layer == '코어')}, 확장 {np.sum(layer == '확장')}, BV {np.sum(~np.isnan(yb[:, 3]))}개), 단일 노브 {len(Xs)}개(BV {np.sum(~np.isnan(ys[:, 3]))}개)", flush=True)
    inside_bv = np.array([sp.in_domain(*x) for x in Xs])                    # BV 단일 노브 점은 학습 영역 안의 것만 학습에 쓴다
    ys_train = ys.copy()
    ys_train[~inside_bv, 3] = np.nan
    names = ["선형", "2차다항", "GP", "GP+변환", "2단GP", "DNN앙상블"]
    res = {n: [[] for _ in range(4)] for n in names}
    cov = {j: [] for j in range(4)}
    cvp = np.zeros((len(Xb), 4))                                              # 최종 후보(2단GP)의 교차검증 예측 (그림용)
    seeds = [0, 1, 2]
    for seed in seeds:
        for tr, te in KFold(5, shuffle=True, random_state=seed).split(Xb):
            Xtr, Ytr = np.vstack([Xb[tr], Xs]), np.vstack([yb[tr], ys_train])
            for n in names:
                if n == "DNN앙상블" and seed > 0:
                    continue
                P, S = predict_all(M, n, Xtr, Ytr, Xb[te])
                for j in range(4):
                    ok = ~np.isnan(yb[te, j])
                    res[n][j] += list(err(P[ok, j], yb[te, j][ok], j))
                    if n == "2단GP":
                        if seed == 0:
                            cvp[te, j] = P[:, j]
                        z = np.abs(P[ok, j] - yb[te, j][ok]) / S[ok, j]
                        cov[j] += list(z <= 2)
        print(f"  교차검증 seed {seed} 끝", flush=True)
    # 외삽: ±30 % 바깥 단일 노브 점 (IV)
    inn = np.all(np.abs(Xs - 1) <= 0.3 + 1e-9, axis=1)
    ex = {n: [] for n in names}
    ex_std = None
    for n in names:
        Ytr = np.vstack([yb, ys[inn]])
        P, S = predict_all(M, n, np.vstack([Xb, Xs[inn]]), Ytr, Xs[~inn])
        ex[n] = [rms(err(P[:, j], ys[~inn, j], j)) for j in range(3)]
        if n == "2단GP":
            ex_std = (S[:, 0], np.abs(P[:, 0] - ys[~inn, 0]))
    return M, names, res, cov, ex, ex_std, (Xb, yb, layer, cvp, Xs, ys, ys_train)


def final_fit_and_speed(M, Xb, yb, Xs, ys_train):
    import joblib
    Xtr, Ytr = np.vstack([Xb, Xs]), np.vstack([yb, ys_train])
    f = phys
    fitted = {}
    for j, key in enumerate(("vth", "log_gm", "log_id4v", "bv")):
        ok = ~np.isnan(Ytr[:, j])
        if j == 2:
            fitted[key] = M["_gp4"]().fit(np.c_[f(Xtr[ok]), Ytr[ok, 0]], Ytr[ok, 2])
        else:
            fitted[key] = M["GP+변환"]().fit(f(Xtr[ok]), Ytr[ok, j])
    OUT.mkdir(exist_ok=True)
    joblib.dump({"models": fitted, "입력": ["dose", "epi", "tox"], "입력변환": "[sqrt(dose), log(epi), tox]", "Id4V": "2단: [변환 입력, Vth 예측]으로 log Id4V 예측",
                 "단위": "dose·epi·tox 는 기준값 대비 비율, Vth V, gm·Id4V 는 로그(A/V/μm, A/μm), BV V", "영역": "샘플링계획.in_domain 안에서만 사용"}, OUT / "서로게이트_GP.joblib")
    X = np.column_stack([np.random.default_rng(0).uniform(0.7, 1.3, 100_000) for _ in range(3)])
    t0 = time.time()
    v = fitted["vth"].predict(f(X), return_std=True)
    g = fitted["log_gm"].predict(f(X), return_std=True)
    i = fitted["log_id4v"].predict(np.c_[f(X), v[0]], return_std=True)
    b = fitted["bv"].predict(f(X), return_std=True)
    return time.time() - t0, len(Xtr), int(np.sum(~np.isnan(Ytr[:, 3])))


def report(names, res, cov, ex, ex_std, data, speed):
    Xb, yb, layer, cvp, Xs, ys, ys_train = data
    tg = [TARGET["Vth"], TARGET["gm"], TARGET["Id4V"], TARGET["BV"]]
    L = ["# 서로게이트 후보 비교 (대량 실행 N=146 중 영역 안 143개 + 단일 노브 점)", "",
         f"- 판정 기준 = 가정 측정 잡음의 0.5배(**가정**): Vth {tg[0]:.0f} mV, gm {tg[1]:.1f} %, Id(4V) {tg[2]:.1f} %, BV {tg[3]:.2f} V. 오차는 RMS.",
         f"- 대량 실행 {len(Xb)}개(BV {int(np.sum(~np.isnan(yb[:, 3])))}개) 위주로 5-겹 교차검증 (학습에는 나머지 대량 실행 + 단일 노브 점 {len(Xs)}개를 함께 사용). 선형·다항·GP 는 3회 반복, DNN 은 1회.", "",
         "## 0. 서로게이트란 (TCAD 와 비교)", "", "TCAD 를 빠르게 흉내 내는 대역 모델이다. 노브를 넣으면 TCAD 처럼 Vth·gm·Id(4V)·BV 를 내고, 불확실도도 함께 낸다.", "",
         "| | 진짜 TCAD | 서로게이트 (2단 GP) |", "|---|---|---|",
         "| 입력 | 노브 3개 (도즈, 에피, 산화막) | 같음 |", "| 출력 | Vth, gm, Id(4V), BV | 같음 (+ 예측 불확실도) |",
         f"| 속도 | 한 번에 수십 분 | 한 점에 약 {speed[0] / 100000 * 1000:.2f} ms (10만 점에 {speed[0]:.1f}초, 이 PC 기준) |",
         f"| 방식 | 물리 방정식을 직접 풂 | TCAD 결과 {speed[1]}개를 보고 입력과 출력의 관계를 학습 |",
         f"| 정확도 | 기준(정답) | 교차검증 오차: Vth {rms(res['2단GP'][0]):.1f} mV, gm {rms(res['2단GP'][1]):.2f} %, Id(4V) {rms(res['2단GP'][2]):.2f} %, BV {rms(res['2단GP'][3]):.2f} V |",
         "| 믿을 수 있는 범위 | 제한 없음 | 학습한 영역(`in_domain`) 안. 바깥에서는 불확실도가 커진다 |", "",
         "## 1. 교차검증 (학습 영역 안)", "", "| 모델 | " + " | ".join(NAMES) + " |", "|---|---|---|---|---|"]
    for n in names:
        cells = [f"{rms(res[n][j]):.2f}" + (" ✔" if rms(res[n][j]) <= tg[j] else "") for j in range(4)]
        L.append(f"| {n} | " + " | ".join(cells) + " |")
    L += ["", "✔ = 기준 이내. (BV 는 BV 를 구한 샘플에서만)", "",
          "## 2. 외삽 (±30 % 바깥 단일 노브 점 24~30개를 학습에서 빼고 예측), RMS", "", "| 모델 | Vth(mV) | gm(%) | Id(4V)(%) |", "|---|---|---|---|"]
    for n in names:
        L.append(f"| {n} | " + " | ".join(f"{v:.1f}" for v in ex[n]) + " |")
    s, e = ex_std
    L += ["", f"- 2단 GP 가 외삽 점에서 스스로 알린 Vth 불확실도(평균 {np.mean(s) * 1000:.0f} mV)와 실제 오차(평균 {np.mean(e) * 1000:.0f} mV). "
          f"영역 안 교차검증의 실제 오차는 {rms(res['2단GP'][0]):.1f} mV 였다 → 불확실도가 바깥에서 커지면 \"범위 밖\" 경고로 쓸 수 있다.", "",
          "## 3. GP 불확실도 보정 (2단 GP, 교차검증에서 실제 오차가 예측 ±2σ 안에 든 비율, 이상적으로 약 95 %)", "",
          "| 출력 | 비율 |", "|---|---|"] + [f"| {NAMES[j]} | {100 * np.mean(cov[j]):.0f} % |" for j in range(4)]
    L += ["", "## 4. 최종 모델 (2단 GP, 입력 변환)", "",
          f"- 전체 데이터로 학습해 `서로게이트_GP.joblib`에 저장 (학습 점 {speed[1]}개, BV 학습 점 {speed[2]}개).",
          f"- 코어 영역 무작위 10만 점을 4개 출력으로 예측하는 데 이 PC에서 **{speed[0]:.2f}초** (Jetson 시간은 아직 측정 전).",
          "- 사용 영역: `샘플링계획.in_domain()` 안. 진단·보정은 이 함수와 GP 불확실도로 후보를 제한한다.", ""]
    (OUT / "서로게이트평가.md").write_text("\n".join(L), encoding="utf-8")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for fn in ("Malgun Gothic", "NanumGothic", "AppleGothic"):
            if fn in {f.name for f in matplotlib.font_manager.fontManager.ttflist}:
                plt.rcParams["font.family"] = fn
                break
        plt.rcParams["axes.unicode_minus"] = False
        fig, ax = plt.subplots(1, 4, figsize=(15, 3.8))
        for j, a in enumerate(ax):
            ok = ~np.isnan(yb[:, j])
            t, p = yb[ok, j], cvp[ok, j]
            if j in (1, 2):
                t, p = np.exp(t) * 1e6, np.exp(p) * 1e6
            lo, hi = min(t.min(), p.min()), max(t.max(), p.max())
            a.plot([lo, hi], [lo, hi], color="gray", lw=0.8)
            a.scatter(t, p, s=14, c=["#3b6fb6" if l == "코어" else "#d1603d" for l in np.array(layer)[ok]])
            a.set_title(["Vth (V)", "gm (μS/μm)", "Id(4V) (μA/μm)", "BV (V)"][j], fontsize=10)
            a.set_xlabel("TCAD")
            a.set_ylabel("서로게이트 예측 (교차검증)")
        fig.suptitle("2단 GP 교차검증: 파랑 = 코어, 주황 = 확장", fontsize=10)
        fig.tight_layout()
        fig.savefig(OUT / "서로게이트_예측vs실제.png", dpi=150)
    except Exception as e:
        print("그림 생략:", e)
    print("\n".join(L))


# ---------------------------------------------------------------- 점검
def selftest():
    Xb, yb, layer = load_batch()
    assert Xb.shape == (143, 3) and yb.shape == (143, 4) and np.sum(~np.isnan(yb[:, 3])) == 64 and layer.count("확장") == 47          # 146개 중 영역 밖 3개 제외
    assert abs(yb[0, 0] - 2.25829) < 1e-4 and abs(yb[0, 3] - 41.117) < 0.01                       # 번호 1 = 기준값
    Xs, ys = load_single()
    assert len(Xs) >= 40 and (Xs == 1.0).all(axis=1).sum() == 1
    assert np.allclose(phys(np.array([[1.0, 1.0, 0.06]])), [[1.0, 0.0, 0.06]])
    assert abs(err(np.log(1.05), 0.0, 1) - 5.0) < 1e-9 and abs(err(2.3, 2.26, 0) - 40) < 1e-6
    assert abs(TARGET["Vth"] - 25) < 1e-9 and abs(TARGET["BV"] - 0.15) < 1e-9
    P, S = predict_all(models(), "GP", Xb[:60], yb[:60], Xb[60:70])                                  # GP 가 실제로 돌고 불확실도를 낸다
    assert P.shape == (10, 4) and np.isfinite(S[:, 0]).all() and np.abs(err(P[:, 0], yb[60:70, 0], 0)).max() < 400
    print("selftest ok")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "run":
        M, names, res, cov, ex, ex_std, data = evaluate()
        Xb, yb, layer, cvp, Xs, ys, ys_train = data
        speed = final_fit_and_speed(M, Xb, yb, Xs, ys_train)
        report(names, res, cov, ex, ex_std, data, speed)
    else:
        print(__doc__)
