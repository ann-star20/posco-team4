"""최종 서로게이트를 학습데이터_최종.csv 로 처음부터 만들고 점검한다 (이 PC 에서 한 번 실행, 결과 모델/ 를 Jetson 으로 복사).
  입력 : 데이터/학습데이터_최종.csv  (대량 실행 + 단일 노브, 영역 밖 BV 붕괴 샘플 제외)
  구조 : Vth·gm 은 GP 하나씩, Id(4V)는 Vth 예측을 입력에 더한 2단 GP, BV 는 설정(--bv)한 입력의 GP. 입력 변환 [√도즈, ln 에피, 산화막]
  출력 : 모델/gp.npz (NumPy 로 푼 GP), 모델/영역.json (in_domain 규칙), 모델/모델정보.json (성능·보정배율), 결과/최종평가.md

  python 최종ML만들기.py                   # 학습 + 교차검증 + 내보내기 + 점검
  python 최종ML만들기.py --bv dlogepi      # BV 입력 변환 선택: phys | raw | dlogepi (기본은 CONFIG)
"""
import argparse
import csv
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import re
import importlib.util as _u
_f = next(p for p in HERE.glob("*.py") if re.search(r"^class Surrogate\b", p.read_text(encoding="utf-8"), re.M) and p.name != Path(__file__).name)      # 실행용 서로게이트 모듈 (파일 이름이 바뀌어도 찾는다)
_s = _u.spec_from_file_location("surrogate_runtime", _f)
_m = _u.module_from_spec(_s)
_s.loader.exec_module(_m)
Surrogate, features = _m.Surrogate, _m.features

CONFIG = dict(bv_input="raw", bv_log=False)                      # 비교 결과에 따라 정한다
TARGET = dict(vth=25.0, gm=2.5, id4v=2.5, bv=0.15)               # 요구 성능 (가정 측정 잡음의 0.5배: mV, %, %, V)
OUTS = ("vth", "gm", "id4v", "bv")


def load(csv_path):
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8-sig")))
    f = lambda r, k: float(r[k]) if r[k] not in ("", None) else np.nan
    X, Y, kind = [], [], []
    for r in rows:
        if r["상태"] != "ok":
            continue
        batch = r["출처"] == "대량실행"
        if batch and r["영역안"] != "True":
            continue                                             # 펀치스루 구석 3개는 학습·평가에서 뺀다
        bv = f(r, "BV_1e-9")
        if not batch and not (r["영역안"] == "True" and r["B1"] == "True" and r["B3"] == "True" and r["B4"] == "True"):
            bv = np.nan                                          # 단일 노브 BV 는 영역 안이고 규칙을 통과한 점만
        X.append([f(r, "바디도즈비율"), f(r, "에피도핑비율"), f(r, "산화막비율")])
        Y.append([f(r, "Vth"), np.log(f(r, "gm")), np.log(f(r, "Id4V")), bv])
        kind.append("batch" if batch else "single")
    return np.array(X), np.array(Y), np.array(kind), rows


def _gp(d):
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import ConstantKernel as C, Matern, WhiteKernel
    return GaussianProcessRegressor(C(1.0) * Matern([0.5] * d, nu=2.5, length_scale_bounds=(0.05, 20)) + WhiteKernel(1e-3, (1e-10, 1.0)),
                                    normalize_y=True, n_restarts_optimizer=3, random_state=0)


def fit_all(X, Y, cfg):
    f = features(X, "phys")
    m = {}
    ok = ~np.isnan(Y[:, 0])
    m["vth"] = _gp(3).fit(f[ok], Y[ok, 0])
    m["log_gm"] = _gp(3).fit(f[ok], Y[ok, 1])
    vh = m["vth"].predict(f)
    m["log_id4v"] = _gp(4).fit(np.c_[f, Y[:, 0]], Y[:, 2])      # 학습 때는 Vth 실제값, 예측 때는 Vth 예측값을 넣는다 (예측 오차가 Id 로 전파됨을 평가에 포함)
    ok = ~np.isnan(Y[:, 3])
    y = np.log(Y[ok, 3]) if cfg["bv_log"] else Y[ok, 3]
    m["bv"] = _gp(3).fit(features(X[ok], cfg["bv_input"]), y)
    return m


def predict_sk(m, X, cfg):
    f = features(X, "phys")
    v, sv = m["vth"].predict(f, return_std=True)
    g, sg = m["log_gm"].predict(f, return_std=True)
    i, si = m["log_id4v"].predict(np.c_[f, v], return_std=True)
    b, sb = m["bv"].predict(features(X, cfg["bv_input"]), return_std=True)
    if cfg["bv_log"]:
        b, sb = np.exp(b), np.exp(b) * sb
    return np.c_[v, g, i, b], np.c_[sv, sg, si, sb]


def err(p, t, j):
    return (p - t) * 1000 if j == 0 else (100 * (np.exp(p - t) - 1) if j in (1, 2) else p - t)


def cross_validate(X, Y, kind, cfg, seeds=(0, 1)):
    from sklearn.model_selection import KFold
    bi = np.where(kind == "batch")[0]
    si = np.where(kind == "single")[0]
    P, S, T = [], [], []
    for sd in seeds:
        for tr, te in KFold(5, shuffle=True, random_state=sd).split(bi):
            trn = np.r_[bi[tr], si]
            m = fit_all(X[trn], Y[trn], cfg)
            p, s = predict_sk(m, X[bi[te]], cfg)
            P.append(p), S.append(s), T.append(Y[bi[te]])
        print(f"  교차검증 분할 {sd} 끝", flush=True)
    P, S, T = np.vstack(P), np.vstack(S), np.vstack(T)
    res, cal = {}, {}
    for j, k in enumerate(OUTS):
        ok = ~np.isnan(T[:, j])
        e = err(P[ok, j], T[ok, j], j)
        z = np.abs(P[ok, j] - T[ok, j]) / S[ok, j]
        res[k] = dict(rmse=float(np.sqrt(np.mean(e ** 2))), mae=float(np.mean(np.abs(e))), p95=float(np.percentile(np.abs(e), 95)), max=float(np.max(np.abs(e))), n=int(ok.sum()) // len(seeds),
                      cov2_원래=float(np.mean(z <= 2)), zrms=float(np.sqrt(np.mean(z ** 2))))
        cal[k] = max(1.0, res[k]["zrms"])                         # 과신하는 출력만 σ 를 키운다 (이미 보수적이면 1)
        res[k]["cov2_보정후"] = float(np.mean(z / cal[k] <= 2))
    return res, cal


def export_gp(g):
    k = g.kernel_
    L = g.L_
    return dict(X=g.X_train_, alpha=g.alpha_.ravel(), Linv=np.linalg.solve(L, np.eye(len(L))), ls=np.atleast_1d(k.k1.k2.length_scale), c=k.k1.k1.constant_value, noise=k.k2.noise_level,
                ymean=float(np.ravel(g._y_train_mean)[0]), ystd=float(np.ravel(g._y_train_std)[0]))


def export_domain(path):
    """영역 규칙을 JSON 으로 저장 (원본 규칙 파일이 있는 PC 에서만 새로 만들 수 있다. 이미 있으면 그대로 쓴다)."""
    if path.exists():
        return
    import importlib.util
    root = next(p for p in (HERE, *HERE.parents) if (p / "대량작업2" / "샘플링계획" / "샘플링계획.py").exists())
    spec = importlib.util.spec_from_file_location("sp", root / "대량작업2" / "샘플링계획" / "샘플링계획.py")
    sp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sp)
    base, cv = sp.vth_curves()
    path.write_text(json.dumps(dict(core=list(sp.CORE), verified={k: list(v) for k, v in sp.VERIFIED.items()}, vth_min=sp.VTH_MIN, punch_dose=sp.PUNCH_DOSE, punch_epi=sp.PUNCH_EPI,
                                    vth_base=float(base), vth_curves={k: [[float(a), float(b)] for a, b in v] for k, v in cv.items()}), ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bv", default=CONFIG["bv_input"], choices=["phys", "raw", "dlogepi"])
    ap.add_argument("--bvlog", action="store_true", default=CONFIG["bv_log"])
    ap.add_argument("--no-cv", action="store_true")
    a = ap.parse_args()
    cfg = dict(bv_input=a.bv, bv_log=a.bvlog)
    X, Y, kind, rows = load(HERE / "데이터" / "학습데이터_최종.csv")
    print(f"학습 점 {len(X)}개 (대량 실행 {int((kind == 'batch').sum())}, 단일 노브 {int((kind == 'single').sum())}), BV 학습 점 {int((~np.isnan(Y[:, 3])).sum())}개, BV 설정 {cfg}", flush=True)
    t0 = time.time()
    res, cal = ({k: None for k in OUTS}, {k: 1.0 for k in OUTS}) if a.no_cv else cross_validate(X, Y, kind, cfg)
    print("교차검증", {k: (round(v["rmse"], 3) if v else None) for k, v in res.items()}, "보정배율", {k: round(v, 2) for k, v in cal.items()}, flush=True)
    m = fit_all(X, Y, cfg)
    out = HERE / "모델"
    out.mkdir(exist_ok=True)
    np.savez(out / "gp.npz", **{f"{k}__{kk}": np.asarray(vv, np.float64) for k in ("vth", "log_gm", "log_id4v", "bv") for kk, vv in export_gp(m[k]).items()})
    export_domain(out / "영역.json")
    np.savez(out / "학습배열.npz", X=X, Y=Y)                       # 고정밀 모드(TabPFN)가 문맥으로 쓰는 학습 점 (입력 비율, [Vth, ln gm, ln Id, BV])
    base = next(r for r in rows if r["ID"] == "B001")
    info = dict(만든날=time.strftime("%Y-%m-%d"), 학습점=int(len(X)), BV학습점=int((~np.isnan(Y[:, 3])).sum()), BV입력=cfg["bv_input"], BV로그=cfg["bv_log"], 보정배율={"vth": cal["vth"], "gm": cal["gm"], "id4v": cal["id4v"], "bv": cal["bv"]},
                교차검증=res, 요구성능=TARGET, 기준값=dict(vth=float(base["Vth"]), gm=float(base["gm"]), id4v=float(base["Id4V"]), bv=float(base["BV_1e-9"])),
                주의=["TCAD 합성 데이터로 학습, 측정 잡음·산포는 가정값", "in_domain 밖에서는 사용하지 않는다 (strict=True 가 NaN 을 돌려준다)", "GP 는 float64 로만 계산한다", "BV 입력이 raw/dlogepi 이면 에피 감소 방향 영역 밖 외삽이 크게 틀린다"])
    (out / "모델정보.json").write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
    # 점검: NumPy 서로게이트 == sklearn, 영역 규칙 == 원본 규칙
    s = Surrogate()
    rng = np.random.default_rng(0)
    T = np.c_[rng.uniform(0.7, 1.3, (3000, 3))]
    pn = s.predict(T, strict=False)
    ps, ss = predict_sk(m, T, cfg)
    d = max(np.abs(pn["vth"] - ps[:, 0]).max(), np.abs(np.log(pn["gm"]) - ps[:, 1]).max(), np.abs(np.log(pn["id4v"]) - ps[:, 2]).max(), np.abs(pn["bv"] - ps[:, 3]).max())
    assert d < 1e-6, f"NumPy 와 sklearn 이 다르다: {d}"
    try:
        import importlib.util
        root = next(p for p in (HERE, *HERE.parents) if (p / "대량작업2" / "샘플링계획" / "샘플링계획.py").exists())
        spec = importlib.util.spec_from_file_location("sp", root / "대량작업2" / "샘플링계획" / "샘플링계획.py")
        sp = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sp)
        G = np.c_[rng.uniform(0.25, 1.8, (4000, 1)), rng.uniform(0.25, 1.8, (4000, 1)), rng.uniform(0.45, 1.5, (4000, 1))]
        assert all(bool(sp.in_domain(*g)) == bool(w) for g, w in zip(G, s.domain(G))), "영역 규칙이 원본과 다르다"
        print("영역 규칙 점검: 원본과 4000개 점에서 모두 일치")
    except StopIteration:
        print("(원본 영역 규칙 파일이 없어 영역 점검은 건너뜀)")
    print(f"NumPy 서로게이트와 sklearn 최대 차이 {d:.2e}")
    L = ["# 최종 서로게이트 평가", "", f"- 학습 점 {info['학습점']}개 (BV {info['BV학습점']}개), BV 입력 `{cfg['bv_input']}`, 로그 {cfg['bv_log']}. 교차검증은 5-겹 2회 (학습에 쓰지 않은 대량 실행 샘플만 평가).",
         "- 요구 성능은 가정 측정 잡음의 0.5배. 보정배율 = 오차÷σ 의 RMS (1 보다 크면 σ 를 그만큼 키워서 쓴다).", "",
         "| 출력 | n | RMSE | MAE | 95 % | 최대 | 요구 | 판정 | 2σ 포함률(원래→보정후) | 보정배율 |", "|---|---|---|---|---|---|---|---|---|---|"]
    unit = dict(vth="mV", gm="%", id4v="%", bv="V")
    for k in OUTS:
        r = res[k]
        if r:
            L.append(f"| {k} ({unit[k]}) | {r['n']} | {r['rmse']:.3g} | {r['mae']:.3g} | {r['p95']:.3g} | {r['max']:.3g} | {TARGET[k]} | {'통과' if r['rmse'] <= TARGET[k] else '미달'} | {100 * r['cov2_원래']:.0f} % → {100 * r['cov2_보정후']:.0f} % | {cal[k]:.2f} |")
    (HERE / "결과" / "최종평가.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L), f"\n총 {time.time() - t0:.0f}초")


if __name__ == "__main__":
    main()
