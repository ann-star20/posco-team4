"""과적합 비교: 모델마다 5-겹(분할 시드 0)에서 학습 점에 대한 오차(학습 오차)와 학습에 쓰지 않은 점에 대한 오차(검증 오차)를 함께 구해 비교한다.
한 번 학습한 모델로 두 오차를 모두 구한다 (학습 오차 = 같은 접힘의 대량 실행 학습 샘플을 다시 예측한 오차).
  python 과적합.py 1 2 3     # 번호로 일부 (결과/과적합.json 에 쌓는다)
  python 과적합.py 그림      # json 으로 그림·표 작성
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from 공통 import Data, ONAME, TARGET, ev
import 모델들 as M

OUT = Path(__file__).resolve().parent / "결과"
PATH = OUT / "과적합.json"


def run(pick):
    from sklearn.model_selection import KFold
    D = Data()
    for name, (fn, slow) in M.MODELS.items():
        if name.split()[0] not in pick:
            continue
        t0 = time.time()
        Etr = [[] for _ in range(4)]
        Ete = [[] for _ in range(4)]
        for tr, te in KFold(5, shuffle=True, random_state=0).split(D.Xb):
            Xtr, Ytr = np.vstack([D.Xb[tr], D.Xs]), np.vstack([D.yb[tr], D.ys_tr])
            P, _ = fn(Xtr, Ytr, np.vstack([D.Xb[te], D.Xb[tr]]))
            for j in range(4):
                for E, idx, Pj in ((Ete, te, P[:len(te)]), (Etr, tr, P[len(te):])):
                    ok = ~np.isnan(D.yb[idx, j])
                    E[j] += list(ev.err(Pj[ok, j], D.yb[idx, j][ok], j))
        R = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
        R[name] = {"train": [ev.rms(e) for e in Etr], "val": [ev.rms(e) for e in Ete]}
        PATH.write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
        print(name, [round(v, 4) for v in R[name]["train"]], [round(v, 4) for v in R[name]["val"]], round(time.time() - t0), "s", flush=True)


def figure():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for fn in ("Malgun Gothic", "NanumGothic"):
        if fn in {x.name for x in matplotlib.font_manager.fontManager.ttflist}:
            plt.rcParams["font.family"] = fn
            break
    plt.rcParams["axes.unicode_minus"] = False
    R = json.loads(PATH.read_text(encoding="utf-8"))
    names = sorted(R, key=lambda s: int(s.split()[0]))
    lab = [n.split(" ", 1)[1] for n in names]
    x = np.arange(len(names))
    fig, ax = plt.subplots(2, 2, figsize=(16, 9))
    for j, a in enumerate(ax.ravel()):
        tr = [max(R[n]["train"][j], 1e-6) for n in names]
        va = [R[n]["val"][j] for n in names]
        a.bar(x - 0.2, tr, 0.4, label="학습 오차", color="#4c78a8")
        a.bar(x + 0.2, va, 0.4, label="검증 오차(보지 않은 점)", color="#e45756")
        a.axhline(TARGET[j], color="k", ls="--", lw=0.8, label="요구 성능")
        a.set_yscale("log")
        a.set_xticks(x)
        a.set_xticklabels(lab, rotation=40, ha="right", fontsize=8)
        a.set_title(ONAME[j] + " RMSE", fontsize=10)
        if j == 0:
            a.legend(fontsize=8)
    fig.suptitle("그림 1. 모델별 학습 오차와 검증 오차 (5-겹 교차검증, 로그 축)", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "과적합_학습vs검증.png", dpi=130)
    # 과적합 비율 (검증/학습) 히트맵
    G = np.array([[R[n]["val"][j] / max(R[n]["train"][j], 1e-9) for j in range(4)] for n in names])
    fig, ax = plt.subplots(figsize=(7.5, 6.5))
    im = ax.imshow(np.log10(G), cmap="RdYlGn_r", vmin=0, vmax=3)
    ax.set_xticks(range(4))
    ax.set_xticklabels(ONAME)
    ax.set_yticks(x)
    ax.set_yticklabels(lab)
    for i in range(len(names)):
        for j in range(4):
            ax.text(j, i, f"{G[i, j]:.1f}배", ha="center", va="center", fontsize=8)
    fig.colorbar(im, label="log10(검증 오차 ÷ 학습 오차)")
    ax.set_title("그림 2. 과적합 정도 (검증 오차 ÷ 학습 오차)", fontsize=11)
    fig.tight_layout()
    fig.savefig(OUT / "과적합_비율.png", dpi=130)
    L = ["# 과적합 비교", "", "학습 오차 = 같은 모델이 자기가 본 점을 다시 예측한 오차, 검증 오차 = 보지 않은 점 오차 (5-겹, 분할 시드 0). 비율이 클수록 외운 정도가 크다.", "",
         "| 모델 | " + " | ".join(f"{o} 학습 / 검증 (비율)" for o in ONAME) + " |", "|---|---|---|---|---|"]
    for n, g in zip(names, G):
        L.append(f"| {n} | " + " | ".join(f"{R[n]['train'][j]:.3g} / {R[n]['val'][j]:.3g} ({g[j]:.1f}배)" for j in range(4)) + " |")
    (OUT / "과적합.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


if __name__ == "__main__":
    a = sys.argv[1:]
    figure() if a == ["그림"] else run(set(a))
