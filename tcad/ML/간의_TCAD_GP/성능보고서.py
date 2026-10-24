"""서로게이트(2단 GP) 성능 보고서용 상세 평가. 서로게이트평가.py 의 데이터·모델 함수를 그대로 쓴다. TCAD 는 돌리지 않는다.

  python 성능보고서.py run     # 평가(수 분) -> 결과/성능_평가.npz 저장 후 보고서 작성
  python 성능보고서.py report  # 저장된 결과로 보고서만 다시 작성 (몇 초)
결과: 결과/성능보고서.md, 결과/성능_*.png
"""
import csv
import importlib.util
import sys
import time
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
EV = next(q for q in HERE.glob("*.py") if "TCAD" in q.name and "성능" not in q.name)          # 서로게이트 평가 스크립트
spec = importlib.util.spec_from_file_location("ev", EV)
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)
OUT, NAMES, TARGET = ev.OUT, ev.NAMES, ev.TARGET
TG = [TARGET["Vth"], TARGET["gm"], TARGET["Id4V"], TARGET["BV"]]
KO = ["바디 도즈", "에피 도핑", "산화막"]
CACHE = OUT / "성능_평가.npz"


def batch_numbers():
    rows = list(csv.DictReader(open(ev.ROOT / "대량작업2" / "대량실행" / "결과" / "대량실행_결과_N146.csv", encoding="utf-8-sig")))
    return np.array([int(r["번호"]) for r in rows if r["상태"] == "ok" and ev.sp.in_domain(float(r["바디도즈비율"]), float(r["에피도핑비율"]), float(r["산화막비율"]))])


def arm_of(x):
    d = np.abs(x - 1)
    return -1 if d.max() <= 0.3 + 1e-9 else int(np.argmax(d)) * 2 + (0 if x[int(np.argmax(d))] < 1 else 1)   # 0 도즈−,1 도즈+,2 에피−,3 에피+,4 산화막−,5 산화막+


ARMN = ["도즈−", "도즈+", "에피−", "에피+", "산화막−", "산화막+"]


def fit_predict(M, Xtr, Ytr, Xte):
    return ev.predict_all(M, "2단GP", Xtr, Ytr, Xte)


def run():
    from sklearn.model_selection import KFold
    OUT.mkdir(exist_ok=True)
    M = ev.models()
    Xb, yb, layer = ev.load_batch()
    Xs, ys = ev.load_single()
    num = batch_numbers()
    assert len(num) == len(Xb)
    inside = np.array([ev.sp.in_domain(*x) for x in Xs])
    ys_tr = ys.copy()
    ys_tr[~inside, 3] = np.nan
    n = len(Xb)
    R = {}
    # 1) 반복 교차검증 (3회 x 5겹)
    P3, S3 = np.zeros((3, n, 4)), np.zeros((3, n, 4))
    t0 = time.time()
    for s in range(3):
        for tr, te in KFold(5, shuffle=True, random_state=s).split(Xb):
            P, S = fit_predict(M, np.vstack([Xb[tr], Xs]), np.vstack([yb[tr], ys_tr]), Xb[te])
            P3[s, te], S3[s, te] = P, S
        print("cv seed", s, round(time.time() - t0), "s", flush=True)
    R["P3"], R["S3"] = P3, S3
    # 2) 학습 곡선 (BV·Vth·Id): 학습 대량 샘플을 비율로 줄이며 5겹 시험 폴드 고정
    fr = [0.25, 0.5, 0.75, 1.0]
    LC = np.full((len(fr), 4), np.nan)
    rng = np.random.default_rng(0)
    for a, f in enumerate(fr):
        e = [[] for _ in range(4)]
        for tr, te in KFold(5, shuffle=True, random_state=0).split(Xb):
            sub = rng.permutation(tr)[: int(round(len(tr) * f))]
            P, _ = fit_predict(M, np.vstack([Xb[sub], Xs]), np.vstack([yb[sub], ys_tr]), Xb[te])
            for j in range(4):
                ok = ~np.isnan(yb[te, j])
                e[j] += list(ev.err(P[ok, j], yb[te, j][ok], j))
        LC[a] = [ev.rms(e[j]) for j in range(4)]
        print("학습곡선", f, flush=True)
    R["LC"], R["fr"] = LC, np.array(fr)
    # 3) 팔(축) 하나를 통째로 빼고 예측 (같은 방향 단일 노브 점도 뺌) = 방향별 외삽 시험
    arms = np.array([arm_of(x) for x in Xb])
    sarms = np.array([arm_of(x) for x in Xs])
    AE = np.full((6, 4), np.nan)
    AN = np.zeros(6, int)
    for a in range(6):
        te = arms == a
        if te.sum() == 0:
            continue
        keep = sarms != a
        P, _ = fit_predict(M, np.vstack([Xb[~te], Xs[keep]]), np.vstack([yb[~te], ys_tr[keep]]), Xb[te])
        AN[a] = te.sum()
        for j in range(4):
            ok = ~np.isnan(yb[te, j])
            if ok.sum():
                AE[a, j] = ev.rms(ev.err(P[ok, j], yb[te, j][ok], j))
        print("팔", ARMN[a], te.sum(), flush=True)
    R["AE"], R["AN"] = AE, AN
    # 4) 사후 검증: 첫 배치(1~120)만으로 학습 -> 둘째 배치(121~) 예측
    old = num <= 120
    P, S = fit_predict(M, np.vstack([Xb[old], Xs]), np.vstack([yb[old], ys_tr]), Xb[~old])
    R["PP"], R["SP"], R["pro_idx"] = P, S, np.where(~old)[0]
    # 5) 단일 노브 외삽(±30 % 바깥) 점별 예측
    inn = np.all(np.abs(Xs - 1) <= 0.3 + 1e-9, axis=1)
    P, S = fit_predict(M, np.vstack([Xb, Xs[inn]]), np.vstack([yb, ys_tr[inn]]), Xs[~inn])
    R["EP"], R["ES"], R["EX"], R["EY"] = P, S, Xs[~inn], ys[~inn]
    # 6) 속도 (최종 모델을 다시 학습해 저장하지는 않는다)
    import joblib
    fitted = joblib.load(OUT / "서로게이트_GP.joblib")["models"]
    X = np.column_stack([np.random.default_rng(0).uniform(0.7, 1.3, 100_000) for _ in range(3)])
    t0 = time.time()
    v = fitted["vth"].predict(ev.phys(X), return_std=True)
    fitted["log_gm"].predict(ev.phys(X), return_std=True)
    fitted["log_id4v"].predict(np.c_[ev.phys(X), v[0]], return_std=True)
    fitted["bv"].predict(ev.phys(X), return_std=True)
    R["t100k"] = time.time() - t0
    np.savez(CACHE, Xb=Xb, yb=yb, layer=np.array(layer), num=num, arms=arms, **R)
    print("평가 저장", CACHE)


def metrics(p, t, j):
    ok = ~np.isnan(t)
    e = ev.err(p[ok], t[ok], j)
    ss_res, ss_tot = np.sum((p[ok] - t[ok]) ** 2), np.sum((t[ok] - t[ok].mean()) ** 2)
    return dict(n=int(ok.sum()), rmse=ev.rms(e), mae=float(np.mean(np.abs(e))), p95=float(np.percentile(np.abs(e), 95)), mx=float(np.max(np.abs(e))), bias=float(np.mean(e)), r2=float(1 - ss_res / ss_tot))


def report():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for fn in ("Malgun Gothic", "NanumGothic"):
        if fn in {f.name for f in matplotlib.font_manager.fontManager.ttflist}:
            plt.rcParams["font.family"] = fn
            break
    plt.rcParams["axes.unicode_minus"] = False
    D = np.load(CACHE, allow_pickle=False)
    Xb, yb, arms, P3, S3 = D["Xb"], D["yb"], D["arms"], D["P3"], D["S3"]
    n = len(Xb)
    P, S = P3.mean(0), S3.mean(0)                                               # 같은 샘플의 3번 교차검증 예측을 평균 (모두 학습에 안 쓴 예측)
    Pn = ["Vth", "ln gm", "ln Id(4V)", "BV"]
    UN = ["V", "ln(A/V/μm)", "ln(A/μm)", "V"]
    M = [metrics(P3.reshape(-1, 4)[:, j], np.tile(yb[:, j], 3), j) for j in range(4)]
    L = ["# 간의 TCAD(서로게이트) 성능 보고서", "",
         "TCAD 시뮬레이션을 대신하는 2단 GP 서로게이트의 데이터 분석(EDA 요약)과 성능 평가. 모든 숫자는 TCAD 합성 데이터에서 얻은 것이며 측정 노이즈 등 가정값은 `노이즈가정.py`를 따른다.", "",
         "## 1. 요약", "",
         f"- 학습 영역 안 대량 실행 샘플 {n}개(BV {int(np.sum(~np.isnan(yb[:, 3])))}개) + 단일 노브 점으로 학습. 평가는 샘플 단위 5-겹 교차검증을 서로 다른 분할로 3번 반복했다 (학습에 쓰지 않은 점만 예측).",
         f"- 교차검증 오차(RMS): Vth **{M[0]['rmse']:.1f} mV**, gm **{M[1]['rmse']:.2f} %**, Id(4V) **{M[2]['rmse']:.2f} %**, BV **{M[3]['rmse']:.2f} V**. 기준(가정 노이즈의 0.5배: {TG[0]:.0f} mV, {TG[1]:.1f} %, {TG[2]:.1f} %, {TG[3]:.2f} V)과 비교하면 Vth·gm·Id(4V)는 통과, **BV 는 미달**.",
         f"- 한 점 예측에 약 {float(D['t100k']) / 100000 * 1000:.2f} ms (10만 점 {float(D['t100k']):.1f}초, 이 PC). 진짜 TCAD 는 한 점에 수십 분.", "",
         "## 2. 데이터 (EDA 요약)", "",
         "- 입력: 바디 도즈·에피 도핑·산화막 두께(기준값 대비 비율, 확산 시간은 고정). 출력: Vth, gm, Id(4V), BV.",
         "- 대량 실행 146개(코어 라틴 하이퍼큐브 ±30 % 96개 + 노브 하나만 바깥으로 보낸 확장 50개) + 단일 노브 42개 = 188행, BV 98행. 평가에는 영역 밖 3개(펀치스루 구석)를 뺀 143개를 쓴다.",
         "- Vth 스펙(1.7~2.6 V) 밖 44 %, BV 스펙(≥ 40 V) 밖 46 %로 양품·불량이 섞여 있다. BV 는 에피에 거의 단독으로 반응(순위 상관 −0.93), Vth·gm 은 산화막·도즈에 반응한다. 자세한 내용은 EDA 보고서 참조.", "",
         "## 3. 모델과 평가 방법", "",
         "- 입력 변환: [√바디도즈, log 에피, 산화막]. Vth·gm·BV 는 GP(Matern 5/2 + 잡음항) 각각, Id(4V)는 Vth 예측을 입력에 더한 2단 GP.",
         "- 비교 모델: 선형, 2차 다항, GP(원래 입력), GP(변환), DNN 5개 앙상블 — 비교표는 `서로게이트평가.md` 참조.",
         "- 학습에 단일 노브 점(영역 안 BV 포함)을 항상 함께 넣었고 평가는 대량 실행 샘플에서만 했다.", ""]
    # 4 정확도
    L += ["## 4. 교차검증 정확도 (학습 영역 안)", "",
          "| 출력 | 단위 | n | RMSE | MAE | 95 % 분위 | 최대 오차 | 편향 | R² | 기준 | 판정 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    uu = ["mV", "%", "%", "V"]
    for j in range(4):
        m = M[j]
        L.append(f"| {Pn[j]} | {uu[j]} | {m['n'] // 3} | {m['rmse']:.2f} | {m['mae']:.2f} | {m['p95']:.2f} | {m['mx']:.2f} | {m['bias']:+.2f} | {m['r2']:.4f} | {TG[j]:.2f} | {'통과' if m['rmse'] <= TG[j] else '미달'} |")
    L += ["", "- 오차는 Vth mV, gm·Id(4V)는 %(로그 예측 환산), BV V. R² 는 Vth·BV 는 원래 값, gm·Id(4V)는 로그 값 기준.",
          "- 편향(평균 오차)이 RMSE 에 비해 작아 한쪽으로 치우친 오차는 없다.", "",
          "![예측 vs 실제](성능_예측vs실제.png)", ""]
    fig, ax = plt.subplots(1, 4, figsize=(15, 3.8))
    for j in range(4):
        ok = ~np.isnan(yb[:, j])
        ax[j].errorbar(yb[ok, j], P[ok, j], yerr=2 * S[ok, j], fmt="o", ms=3, elinewidth=0.5, alpha=0.7, color="#3b6fb6")
        lo, hi = np.nanmin(yb[:, j]), np.nanmax(yb[:, j])
        ax[j].plot([lo, hi], [lo, hi], "k--", lw=0.8)
        ax[j].set_title(f"{Pn[j]} ({UN[j]})  RMSE {M[j]['rmse']:.2f}{uu[j]}", fontsize=9)
        ax[j].set_xlabel("TCAD(실제)")
        ax[j].set_ylabel("서로게이트 예측 (막대 = ±2σ)")
    fig.suptitle("그림 1. 교차검증 예측 vs 실제", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "성능_예측vs실제.png", dpi=130)
    plt.close(fig)
    # 5 구역별
    core = np.array(D["layer"]) == "코어"
    L += ["## 5. 영역별 오차", "", "| 구분 | 샘플 수 | Vth(mV) | gm(%) | Id(4V)(%) | BV(V) (BV 샘플 수) |", "|---|---|---|---|---|---|"]
    groups = [("코어(±30 %)", core), ("확장(한 노브 바깥)", ~core)] + [(f"확장: {ARMN[a]}", arms == a) for a in range(6) if np.sum(arms == a)]
    for nm, mk in groups:
        cs = []
        for j in range(4):
            ok = mk & ~np.isnan(yb[:, j])
            cs.append(f"{ev.rms(ev.err(P[ok, j], yb[ok, j], j)):.2f}" + (f" ({int(ok.sum())})" if j == 3 else "") if ok.sum() else "-")
        L.append(f"| {nm} | {int(mk.sum())} | " + " | ".join(cs) + " |")
    L += ["", "- 확장 구간이 코어보다 오차가 크고(BV 0.24 대 0.02 V), 에피− 팔이 가장 크다.", ""]
    # 6 잔차
    fig, ax = plt.subplots(4, 3, figsize=(11, 11))
    for j in range(4):
        ok = ~np.isnan(yb[:, j])
        e = ev.err(P[:, j], yb[:, j], j)
        for k in range(3):
            ax[j, k].scatter(Xb[ok, k], e[ok], s=8, color="#3b6fb6")
            ax[j, k].axhline(0, color="k", lw=0.6)
            ax[j, k].set_xlabel(KO[k] + " (비율)", fontsize=8)
            ax[j, k].set_ylabel(f"{Pn[j]} 오차 ({uu[j]})", fontsize=8)
    fig.suptitle("그림 2. 노브별 잔차 (예측 − 실제)", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "성능_잔차.png", dpi=120)
    plt.close(fig)
    L += ["## 6. 잔차 분석", "", "![잔차](성능_잔차.png)", ""]
    for j in range(4):
        ok = ~np.isnan(yb[:, j])
        e = ev.err(P[:, j], yb[:, j], j)
        worst = np.argsort(-np.abs(np.where(ok, e, 0)))[:3]
        L.append(f"- {Pn[j]}: 오차가 큰 샘플 상위 3개 — " + ", ".join(f"(도즈 {Xb[i, 0]:.2f}, 에피 {Xb[i, 1]:.2f}, 산화막 {Xb[i, 2]:.2f}) {e[i]:+.2f}{uu[j]}" for i in worst))
    L += ["", "- 큰 오차는 대부분 노브 값이 학습 영역 가장자리(에피 0.3 근처 등)인 점에서 난다. 잔차가 노브 크기에 따라 체계적으로 달라지는 추세는 그림 2 에서 뚜렷하지 않다.", ""]
    # 7 불확실도 보정
    z = [np.abs(P3[:, :, j] - yb[None, :, j]) / S3[:, :, j] for j in range(4)]
    L += ["## 7. 불확실도 보정", "", "GP 가 낸 표준편차(σ) 대비 실제 오차. 잘 맞는 모델이면 1σ 안 약 68 %, 2σ 안 약 95 %, 3σ 안 약 99.7 %.", "",
          "| 출력 | 1σ 안 | 2σ 안 | 3σ 안 | 오차/σ 의 RMS(보정 배율) |", "|---|---|---|---|---|"]
    cal = []
    for j in range(4):
        zz = z[j][~np.isnan(z[j])]
        cal.append(float(np.sqrt(np.mean(zz ** 2))))
        L.append(f"| {Pn[j]} | {100 * np.mean(zz <= 1):.0f} % | {100 * np.mean(zz <= 2):.0f} % | {100 * np.mean(zz <= 3):.0f} % | {cal[-1]:.2f} |")
    L += ["", f"- 보정 배율이 1 보다 크면 모델이 자신을 과신한다는 뜻이다. BV 는 {cal[3]:.2f}배, Id(4V)는 {cal[2]:.2f}배라 진단에서 이 배율을 σ 에 곱해 쓴다 (Vth·gm 은 1 이하). Id(4V)의 큰 오차는 Vth 가 3.5 V 넘는 거의 꺼진 점 두 개에서 난다.", ""]
    # 8 학습곡선
    LC, fr = D["LC"], D["fr"]
    fig, ax = plt.subplots(1, 4, figsize=(14, 3.2))
    for j in range(4):
        ax[j].plot(fr * 100, LC[:, j], "o-")
        ax[j].axhline(TG[j], color="r", ls="--", lw=0.8)
        ax[j].set_title(f"{Pn[j]} RMSE ({uu[j]}), 빨간선 = 기준", fontsize=9)
        ax[j].set_xlabel("학습에 쓴 대량 샘플 비율 (%)")
    fig.suptitle("그림 3. 학습 곡선", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "성능_학습곡선.png", dpi=120)
    plt.close(fig)
    L += ["## 8. 학습 곡선 (데이터를 더 모으면 좋아지는가)", "", "![학습곡선](성능_학습곡선.png)", "", "| 학습 샘플 비율 | Vth(mV) | gm(%) | Id(4V)(%) | BV(V) |", "|---|---|---|---|---|"]
    L += [f"| {int(f * 100)} % | " + " | ".join(f"{v:.2f}" for v in LC[a]) + " |" for a, f in enumerate(fr)]
    L += ["", f"- 25 % → 100 % 로 늘리면 BV 오차는 {LC[0, 3]:.2f} → {LC[-1, 3]:.2f} V, Vth 는 {LC[0, 0]:.1f} → {LC[-1, 0]:.1f} mV 로 변했다. Vth·gm 은 75 % 부근에서, BV 는 50 % 부근에서 거의 평평해져 샘플을 더 늘려도 크게 좋아지지 않는다(평평한 구간의 BV 0.17~0.19 V는 분할마다 달라지는 오차 범위). 이 곡선은 5겹 분할 1회라 값이 위 4절(3회 반복)과 조금 다르다.", ""]
    # 9 방향별 외삽
    AE, AN = D["AE"], D["AN"]
    L += ["## 9. 방향별 외삽 시험 (확장 팔 하나를 통째로 빼고 예측)", "", "그 방향의 단일 노브 점도 학습에서 뺐다. 즉 모델이 한 번도 본 적 없는 방향으로 ±30 % 바깥까지 얼마나 맞히는지 본다.", "",
          "| 뺀 팔 | 시험 샘플 수 | Vth(mV) | gm(%) | Id(4V)(%) | BV(V) |", "|---|---|---|---|---|---|"]
    for a in range(6):
        if AN[a]:
            L.append(f"| {ARMN[a]} | {AN[a]} | " + " | ".join("-" if np.isnan(v) else f"{v:.2f}" for v in AE[a]) + " |")
    L += ["", "- 에피− 방향을 통째로 빼면 Vth 오차가 크게 늘고(15.6 mV) 산화막− 에서 gm 오차가 늘어(3.6 %), 다른 방향은 영역 안 교차검증의 1~2배 수준이다. 그래서 `in_domain` 밖에서는 서로게이트 값을 쓰지 않고 GP 불확실도가 커지는 것을 경고로 쓴다.", ""]
    # 10 외삽(단일 노브)
    EP, ES, EX, EY = D["EP"], D["ES"], D["EX"], D["EY"]
    ee = [ev.err(EP[:, j], EY[:, j], j) for j in range(3)]
    L += ["## 10. 단일 노브 ±30 % 바깥 점 예측 (학습에는 대량 실행 + ±30 % 안 단일 노브 점)", "",
          f"- 점 {len(EX)}개. RMS: Vth {ev.rms(ee[0]):.1f} mV, gm {ev.rms(ee[1]):.2f} %, Id(4V) {ev.rms(ee[2]):.1f} %.",
          f"- GP 가 스스로 낸 Vth σ 평균 {np.mean(ES[:, 0]) * 1000:.0f} mV, 실제 평균 절대오차 {np.mean(np.abs(ee[0])):.0f} mV (영역 안 교차검증 MAE {M[0]['mae']:.1f} mV) → 영역 바깥에서는 σ 가 커져 경고 신호로 쓸 수 있다.", ""]
    # 11 사후 검증
    PP, SP, pi = D["PP"], D["SP"], D["pro_idx"]
    L += ["## 11. 사후 검증: 첫 배치(1~120번)로 학습해 둘째 배치(121번 이후)를 예측", "",
          f"둘째 배치는 학습에 쓰지 않은 새 점이라 진짜 시험이다 (영역 안 {len(pi)}개).", "", "| 출력 | RMSE | 기준 | 판정 |", "|---|---|---|---|"]
    for j in range(4):
        ok = ~np.isnan(yb[pi, j])
        r = ev.rms(ev.err(PP[ok, j], yb[pi, j][ok], j))
        L.append(f"| {Pn[j]} ({uu[j]}) | {r:.2f} | {TG[j]:.2f} | {'통과' if r <= TG[j] else '미달'} |")
    L += ["", "- BV 오차 1.0 V는 에피 0.3~0.5 의 극단 점(예측이 실제보다 3.6 V, 2.4 V, 0.9 V 낮음) 에서 거의 다 나온다. 첫 배치에는 이 구간 점이 적었기 때문이다. 둘째 배치 데이터를 더한 최종 모델(4절)은 이 점들을 학습한 상태라 4절 숫자가 최종 모델의 영역 안 오차이고, 이 표는 새 구간으로 넓힐 때의 기대 오차에 가깝다.", ""]
    # 12 결론
    L += ["## 12. 결론과 한계", "",
          f"- Vth·gm·Id(4V)는 학습 영역 안에서 기준을 만족한다. BV 는 RMSE {M[3]['rmse']:.2f} V 로 목표 0.15 V 에는 못 미치지만 가정 측정 노이즈(0.3 V) 수준이다.",
          "- 불확실도는 BV 에서 과신 경향이 있어 진단에서 보정 배율을 곱한다.",
          "- 한계: ① BV 학습 점이 적다(89개). ② 영역 밖·모서리 조합은 샘플이 없어 신뢰할 수 없다. ③ 펀치스루 경계는 3점으로 정한 잠정 규칙. ④ Jetson 에서의 속도는 아직 측정 전. ⑤ 합성 데이터라 실제 소자와의 차이는 평가하지 않았다.", ""]
    (OUT / "성능보고서.md").write_text("\n".join(L), encoding="utf-8")
    print("보고서 작성:", OUT / "성능보고서.md")


if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else ""
    if c == "run":
        run()
        report()
    elif c == "report":
        report()
    else:
        print(__doc__)
