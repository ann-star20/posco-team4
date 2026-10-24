"""최종 학습데이터 EDA: 학습데이터_최종.csv (대량 실행 샘플 + 단일 노브 시험 점)를 여러 방향에서 본다. TCAD 는 돌리지 않는다.
  0. 최종 파일 구성
  1. 구성·품질: 층/팔별 개수, 규칙 통과, 재시도, BV 가 있는 샘플, 학습 영역(in_domain) 안인지
  2. 입력 커버리지: 노브 3개가 영역을 고르게 덮는가 (노브 간 상관, 빈 칸)
  3. 출력 분포: Vth, gm, Id(4V), BV 와 스펙(Vth 1.7~2.6 V, BV >= 40 V)
  4. 입력 -> 출력 관계: 상관(순위), 노브별 산점도
  5. 모델링에 영향을 주는 점: 출력 간 중복, 거의 꺼진 영역(Vth 큰 곳), BV 절벽 근처, 덧셈 예측과의 차이
  6. 단일 노브 점

  python EDA.py              # 대량작업2/학습데이터/결과/학습데이터_최종.csv 사용
  python EDA.py 120          # 학습데이터_N120.csv (중간 점검용)
결과/EDA_요약.md 와 그림 4장. 데이터가 바뀌면 같은 명령으로 다시 만든다.
"""
import csv
import importlib.util
import sys
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = next(p for p in (HERE, *HERE.parents) if (p / "최종_trench_template.in").exists())
OUT = HERE / "결과"
DATA_DIR = ROOT / "대량작업2" / "학습데이터" / "결과"
DATA = DATA_DIR / (f"학습데이터_N{sys.argv[1]}.csv" if len(sys.argv) > 1 and sys.argv[1].isdigit() else "학습데이터_최종.csv")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


sp = _load(ROOT / "대량작업2" / "샘플링계획" / "샘플링계획.py", "sampling_plan")       # in_domain, vth_pred, CORE
KN = ("dose", "epi", "tox")
KO = {"dose": "바디 도즈", "epi": "에피 도핑", "tox": "산화막 두께"}
OUTN = {"Vth": "Vth (V)", "gm": "gm (μS/μm)", "Id4V": "Id(4V) (μA/μm)", "BV": "BV (V)"}
SPEC = {"Vth": (1.7, 2.6), "BV": (40.0, None)}


def load():
    rows = list(csv.DictReader(open(DATA, encoding="utf-8-sig")))
    f = lambda k, u=1.0: np.array([float(r[k]) * u if r[k] != "" else np.nan for r in rows])
    X = np.c_[f("바디도즈비율"), f("에피도핑비율"), f("산화막비율")]
    Y = {"Vth": f("Vth"), "gm": f("gm", 1e6), "Id4V": f("Id4V", 1e6), "BV": f("BV_1e-9"), "leak": f("누설")}
    meta = {"src": np.array([r["출처"] for r in rows]), "layer": np.array([r["층"] for r in rows]), "arm": np.array([r["확장축"] for r in rows]),
            "status": np.array([r["상태"] for r in rows]), "tries": f("시도횟수"), "sweep": f("스윕V"),
            "rules": np.array([[r[k] == "True" for k in ("I1", "I2", "I5", "I6", "B4")] for r in rows]), "id": np.array([r["ID"] for r in rows]),
            "far": np.array([r["외삽시험용"] == "Y" for r in rows])}
    return rows, X, Y, meta


def fmt(a, d=2):
    a = a[~np.isnan(a)]
    return " / ".join(f"{x:.{d}f}" for x in (a.min(), np.percentile(a, 5), np.median(a), np.percentile(a, 95), a.max()))


def main():
    OUT.mkdir(exist_ok=True)
    rows_all, X_all, Y_all, meta_all = load()
    b = meta_all["src"] == "대량실행"
    s = ~b
    sub = lambda a, m: a[m]
    X, Y = X_all[b], {k: v[b] for k, v in Y_all.items()}
    meta = {k: v[b] for k, v in meta_all.items()}
    ids = meta["id"]
    n = len(X)
    L = [f"# 최종 학습데이터 EDA ({DATA.name})", "",
         "표 안의 \"최소 / 5 % / 중앙 / 95 % / 최대\"는 이 순서의 분위수다. 코드: `대량작업2/EDA/EDA.py`. 1~5절은 대량 실행 샘플, 6절은 단일 노브 점이다.", ""]
    nbv_all = int(np.sum(~np.isnan(Y_all["BV"])))
    L += ["## 0. 최종 파일 구성", "",
          f"- 전체 {len(rows_all)}행 = 대량 실행 {b.sum()}행 + 단일 노브 {s.sum()}행. BV 가 있는 행 {nbv_all}개 (대량 실행 {int(np.sum(~np.isnan(Y['BV'])))}개 + 단일 노브 {nbv_all - int(np.sum(~np.isnan(Y['BV'])))}개).",
          f"- 학습 영역(`in_domain`) 안 {int(np.sum([r['영역안'] == 'True' for r in rows_all]))}행, 단일 노브 중 외삽시험용(±30 % 바깥) {int(meta_all['far'].sum())}행.", ""]
    # 1. 구성과 품질
    arms = {}
    for a, l in zip(meta["arm"], meta["layer"]):
        arms[(l, a)] = arms.get((l, a), 0) + 1
    inside = np.array([sp.in_domain(*x) for x in X])
    bv = ~np.isnan(Y["BV"])
    retried = [ids[i] for i in np.where(meta["tries"] > 1)[0]]
    L += ["## 1. 대량 실행 샘플의 구성과 품질", "",
          f"- 샘플 {n}개: 코어 {np.sum(meta['layer'] == '코어')}개(기준값 1개 포함), 확장 {np.sum(meta['layer'] == '확장')}개. 확장 팔별: " +
          ", ".join(f"{a} {c}" for (l, a), c in sorted(arms.items()) if l == "확장"),
          f"- 상태 ok {np.sum(meta['status'] == 'ok')}개. 규칙 I1·I2·I5·I6·B4 를 모두 통과한 샘플 {np.sum(meta['rules'].all(axis=1))}개. 재시도한 샘플 {len(retried)}개 ({', '.join(retried)}).",
          f"- 학습 영역(`in_domain`) 안: {inside.sum()}/{n}. 게이트 스윕 6 V 샘플 {int(np.sum(meta['sweep'] == 6))}개.",
          (f"- **영역 밖으로 표시된 샘플 {int((~inside).sum())}개**: " + ", ".join(f"{ids[i]}(도즈 {X[i, 0]:.2f}, 에피 {X[i, 1]:.2f}, BV {Y['BV'][i]:.1f} V)" for i in np.where(~inside)[0]) +
           f". 바디 도즈가 낮고 에피가 높은 구석에서 BV 가 무너져(서로게이트 예측과 5~13 V 차이) 규칙 \"도즈 < {sp.PUNCH_DOSE} 이고 에피 > {sp.PUNCH_EPI}\"를 영역에서 뺐다. TCAD 가 낸 실제 값이라 파일에는 남기고 `영역안=False`로 표시한다.") if (~inside).any() else "- 영역 밖으로 표시된 샘플 없음.",
          f"- BV 가 있는 샘플 {bv.sum()}개 ({100 * bv.mean():.0f} %). 확장 층은 전부, 코어는 기준값과 바디 도즈 −20 % 이하에만 계산했다 → **BV 가 있고 없는 것이 입력에 의존**한다 (임의 결측이 아님).",
          f"- 중복 입력 점 {n - len({tuple(np.round(x, 4)) for x in X})}개, 결측(Vth·gm·Id4V) {int(np.isnan(Y['Vth']).sum() + np.isnan(Y['gm']).sum() + np.isnan(Y['Id4V']).sum())}개.", ""]
    # 2. 입력 커버리지
    core = (meta["layer"] == "코어") & (meta["arm"] != "기준값")
    cc = np.corrcoef(X[core].T)
    cell = np.floor((X[core] - sp.CORE[0]) / (sp.CORE[1] - sp.CORE[0]) * 4).clip(0, 3).astype(int)
    filled = len({tuple(c) for c in cell})
    L += ["## 2. 입력 커버리지", "",
          "- 코어 입력끼리의 상관(0에 가까울수록 좋음): " + ", ".join(f"{KO[KN[i]]}–{KO[KN[j]]} {cc[i, j]:+.2f}" for i in range(3) for j in range(i + 1, 3)),
          "- 노브별 범위(비율, 최소~최대): " + ", ".join(f"{KO[k]} {X[:, i].min():.2f}~{X[:, i].max():.2f}" for i, k in enumerate(KN)),
          f"- 코어를 노브별 4등분한 64칸 중 샘플이 있는 칸 {filled}개 (코어 샘플 {core.sum()}개, 칸당 평균 {core.sum() / 64:.1f}개) → 빈 칸 {64 - filled}개.", ""]
    ext_arm = {a: np.sum(meta["arm"] == a) for a in ("에피도핑−", "에피도핑+", "바디도즈+", "산화막−", "산화막+")}
    L += ["- 확장 팔별 샘플 수: " + ", ".join(f"{a} {c}" for a, c in ext_arm.items()) + " (팔이 짧을수록 적게 배치).", ""]
    # 3. 출력 분포
    L += ["## 3. 출력 분포 (최소 / 5 % / 중앙 / 95 % / 최대)", "", "| 출력 | 값 |", "|---|---|"]
    for k in ("Vth", "gm", "Id4V", "BV"):
        L.append(f"| {OUTN[k]} | {fmt(Y[k])} (n = {int(np.sum(~np.isnan(Y[k])))}) |")
    v = Y["Vth"]
    lo, hi = SPEC["Vth"]
    out_spec = (v < lo) | (v > hi)
    bvn = Y["BV"][bv]
    L += ["", f"- **Vth 스펙({lo}~{hi} V) 밖: {out_spec.sum()}/{n} ({100 * out_spec.mean():.0f} %)** (아래쪽 {np.sum(v < lo)}개, 위쪽 {np.sum(v > hi)}개). "
          f"BV 스펙(≥ 40 V) 밖: {np.sum(bvn < 40)}/{len(bvn)} ({100 * np.mean(bvn < 40):.0f} %).",
          f"- 코어만 보면 Vth 스펙 밖 {np.sum(out_spec & core)}/{core.sum()} ({100 * np.sum(out_spec & core) / core.sum():.0f} %). 즉 ±30 % 영역에는 **양품과 불량이 섞여 있어** 진단 연습에 알맞다.",
          f"- Vg=0 누설 최대 {np.nanmax(Y['leak']):.1e} A/μm (기준 5e-16). 가장 큰 값은 Vth 가 낮은 샘플 {ids[int(np.nanargmax(Y['leak']))]}.", ""]
    # 4. 관계
    allv = np.c_[X, Y["Vth"], np.log(Y["gm"]), np.log(Y["Id4V"])]
    rho = spearmanr(allv).correlation
    L += ["## 4. 입력 → 출력 순위 상관 (스피어만, 대량 실행 샘플)", "", "| | Vth | ln gm | ln Id(4V) | BV(있는 샘플) |", "|---|---|---|---|---|"]
    for i, k in enumerate(KN):
        rb = spearmanr(X[bv, i], Y["BV"][bv]).correlation
        L.append(f"| {KO[k]} | {rho[i, 3]:+.2f} | {rho[i, 4]:+.2f} | {rho[i, 5]:+.2f} | {rb:+.2f} |")
    L += ["", "- 읽는 법: Vth 는 바디 도즈·산화막에 크게 반응하고 에피에는 거의 반응하지 않는다. **BV 는 에피에 가장 크게 반응**한다 (구분 가능성 분석의 결론과 같은 방향).", ""]
    # 5. 모델링에 영향을 주는 점
    near_off = v > 3.0
    vp = np.array([sp.vth_pred(*x) for x in X])
    d_add = (v - vp) * 1000
    cliff = (X[:, 0] <= 0.8)
    L += ["## 5. 모델링에 영향을 주는 점", "",
          f"- **출력 간 중복**: Id(4V)와 gm 의 로그 상관 {np.corrcoef(np.log(Y['gm']), np.log(Y['Id4V']))[0, 1]:+.2f}, Vth 와 ln Id(4V)의 상관 {np.corrcoef(v, np.log(Y['Id4V']))[0, 1]:+.2f}. "
          "Id(4V)는 Vth 를 거쳐 정해지므로 서로게이트를 2단으로 만든 것이 맞다.",
          f"- **거의 꺼진 영역**: Vth > 3 V 인 샘플 {near_off.sum()}개 ({100 * near_off.mean():.0f} %). 이 영역에서 Id(4V)는 {np.min(Y['Id4V'][near_off]):.2f}~{np.max(Y['Id4V'][near_off]):.2f} μA/μm 로 기준(5.2)의 {100 * np.min(Y['Id4V'][near_off]) / 5.207:.0f}~{100 * np.max(Y['Id4V'][near_off]) / 5.207:.0f} % 라 특징으로서 신호가 약하다.",
          f"- **BV 절벽 근처**: 바디 도즈 ≤ 0.8 인 샘플 {cliff.sum()}개(BV 전부 계산). 이 구간은 −30 %(0.7) 바깥에서 BV 가 급락하므로 영역 경계에 가까운 점이 중요하다.",
          f"- **덧셈 예측과의 차이**(노브 하나씩 결과를 더한 Vth 예측 대비): 평균 {np.mean(d_add):+.0f} mV, 표준편차 {np.std(d_add):.0f} mV, 최대 |{np.max(np.abs(d_add)):.0f}| mV. 가산성이 완벽하지 않으므로 서로게이트가 조합을 직접 배워야 한다.",
          f"- **경계 샘플**: 코어 중 Vth 가 가장 낮은 샘플 {ids[int(np.argmin(np.where(core, v, 9)))]}({np.min(np.where(core, v, 9)):.2f} V), 가장 높은 샘플 {ids[int(np.argmax(np.where(core, v, 0)))]}({np.max(np.where(core, v, 0)):.2f} V).", ""]
    # 6. 단일 노브 점
    Xs, Ys = X_all[s], {k: vv[s] for k, vv in Y_all.items()}
    ms = {k: vv[s] for k, vv in meta_all.items()}
    bvs = ~np.isnan(Ys["BV"])
    L += ["## 6. 단일 노브 점", "",
          f"- {s.sum()}개 (노브마다 ±10~70 % 14점, 확산 시간은 제외). BV 가 있는 점 {bvs.sum()}개 (BV 가 정의되지 않는 바디 도즈 −70 % 등은 비어 있음).",
          f"- Vth 범위 {Ys['Vth'].min():.2f}~{Ys['Vth'].max():.2f} V. 대량 실행 샘플이 덮지 않는 **±30 % 바깥 영역**을 보여 주는 점이라 외삽 시험에 쓴다 ({int(ms['far'].sum())}개).",
          "- 학습에 넣을 때는 BV 는 학습 영역 안의 점만 쓰는 것을 권장한다 (영역 밖의 바디 도즈 −40~−60 % 는 BV 가 절벽이라 서로게이트에 해롭다).", ""]
    (OUT / "EDA_요약.md").write_text("\n".join(L), encoding="utf-8")
    figures(X_all, Y_all, meta_all, b)
    print("\n".join(L))


def figures(X, Y, meta, b):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for fn in ("Malgun Gothic", "NanumGothic", "AppleGothic"):
        if fn in {f.name for f in matplotlib.font_manager.fontManager.ttflist}:
            plt.rcParams["font.family"] = fn
            break
    plt.rcParams["axes.unicode_minus"] = False
    col = np.where(meta["layer"] == "확장", "#d1603d", np.where(meta["layer"] == "단일노브", "#3a9a6a", "#3b6fb6"))
    legend = "파랑 = 코어, 주황 = 확장, 초록 = 단일 노브"
    OUT.mkdir(exist_ok=True)
    fig, ax = plt.subplots(1, 3, figsize=(13, 4.2))
    for a, (i, j) in zip(ax, ((0, 1), (0, 2), (1, 2))):
        a.scatter(X[:, i], X[:, j], s=16, c=col)
        a.axvspan(0.7, 1.3, color="gray", alpha=0.08)
        a.axhspan(0.7, 1.3, color="gray", alpha=0.08)
        a.set_xlabel(KO[KN[i]] + " (기준 대비 비율)")
        a.set_ylabel(KO[KN[j]])
    ax[0].set_title(legend + " (회색 띠 = ±30 %)", fontsize=9)
    fig.suptitle("그림 1. 입력 커버리지")
    fig.tight_layout()
    fig.savefig(OUT / "그림1_입력커버리지.png", dpi=140)
    plt.close(fig)
    fig, ax = plt.subplots(1, 4, figsize=(15, 3.6))
    for a, k in zip(ax, ("Vth", "gm", "Id4V", "BV")):
        v = Y[k][b & ~np.isnan(Y[k])]
        a.hist(v, bins=24, color="#3b6fb6")
        a.set_title(OUTN[k], fontsize=10)
        for sp_ in SPEC.get(k, ()):
            if sp_ is not None:
                a.axvline(sp_, color="#d1603d", ls="--", lw=1)
    ax[0].text(0.02, 0.95, "점선 = 스펙", transform=ax[0].transAxes, fontsize=8, va="top", color="#d1603d")
    fig.suptitle("그림 2. 출력 분포 (대량 실행 샘플)")
    fig.tight_layout()
    fig.savefig(OUT / "그림2_출력분포.png", dpi=140)
    plt.close(fig)
    allv = np.c_[X[b], Y["Vth"][b], np.log(Y["gm"][b]), np.log(Y["Id4V"][b])]
    rho = spearmanr(allv).correlation
    names = ["도즈", "에피", "산화막", "Vth", "ln gm", "ln Id4V"]
    fig, a = plt.subplots(figsize=(5.2, 4.4))
    im = a.imshow(rho, cmap="RdBu_r", vmin=-1, vmax=1)
    a.set_xticks(range(6), names, fontsize=8)
    a.set_yticks(range(6), names, fontsize=8)
    for i in range(6):
        for j in range(6):
            a.text(j, i, f"{rho[i, j]:+.2f}", ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=a, fraction=0.046)
    a.set_title("그림 3. 스피어만 상관 (대량 실행 샘플)", fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / "그림3_상관.png", dpi=140)
    plt.close(fig)
    fig, ax = plt.subplots(3, 4, figsize=(15, 9))
    for i, k in enumerate(KN):
        for j, o in enumerate(("Vth", "gm", "Id4V", "BV")):
            a = ax[i, j]
            ok = ~np.isnan(Y[o])
            a.scatter(X[ok, i], Y[o][ok], s=12, c=col[ok])
            if i == 0:
                a.set_title(OUTN[o], fontsize=10)
            if j == 0:
                a.set_ylabel(KO[k] + " 에 대해")
            a.set_xlabel("비율", fontsize=8)
    fig.suptitle("그림 4. 노브별 출력 (" + legend + ")")
    fig.tight_layout()
    fig.savefig(OUT / "그림4_노브별출력.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
