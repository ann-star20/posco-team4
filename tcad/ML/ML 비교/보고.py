"""비교결과.json(+속도.json)을 표와 그림으로 정리해 결과/비교결과.md, 결과/비교_*.png 를 만든다.
  python 보고.py
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from 공통 import ARMN, ONAME, TARGET

OUT = Path(__file__).resolve().parent / "결과"
R = json.loads((OUT / "비교결과.json").read_text(encoding="utf-8"))
SP = json.loads((OUT / "속도.json").read_text(encoding="utf-8")) if (OUT / "속도.json").exists() else {}
names = sorted(R, key=lambda s: int(s.split()[0]))
f = lambda v, d=2: "-" if v is None else f"{v:.{d}f}"
ok = lambda v, j: "✔" if v is not None and v <= TARGET[j] else ""


def row(n, key, cols=range(4), d=2, mark=True):
    r = R[n].get(key)
    if r is None:
        return ["-"] * len(list(cols))
    return [f(r[j]["rmse"], d) + (" " + ok(r[j]["rmse"], j) if mark else "") for j in cols]


L = ["# 서로게이트 후보 비교 결과", "",
     f"- 판정 기준(가정 잡음의 0.5배): Vth {TARGET[0]:.0f} mV, gm {TARGET[1]:.1f} %, Id(4V) {TARGET[2]:.1f} %, BV {TARGET[3]:.2f} V. ✔ = 기준 이내. 값은 RMSE.",
     "- 같은 데이터(영역 안 대량 실행 143개 + 단일 노브 점), 같은 분할에서 평가. 교차검증은 5-겹 2회(느린 모델은 1회). `공통.py`·`모델들.py`·`비교실행.py`로 재현.", ""]
L += ["## 1. 교차검증 (학습 영역 안)", "", "| 모델 | " + " | ".join(ONAME) + " |", "|---|---|---|---|---|"]
L += [f"| {n} | " + " | ".join(row(n, "cv")) + " |" for n in names]
L += ["", "## 2. 단일 노브 ±30 % 바깥 외삽 (24점; BV 제외)", "", "| 모델 | Vth(mV) | gm(%) | Id(4V)(%) |", "|---|---|---|---|"]
L += [f"| {n} | " + " | ".join(row(n, "extrap", range(3), 1, False)) + " |" for n in names]
L += ["", "## 3. 방향별 외삽 (확장 팔 하나를 통째로 빼고 예측) — 가장 어려운 두 방향", ""]
L += ["| 모델 | 에피− Vth(mV) | 에피− BV(V) | 산화막− gm(%) | 산화막− Vth(mV) | 팔 5개 Vth 평균(mV) |", "|---|---|---|---|---|---|"]
for n in names:
    A = R[n].get("arms")
    if not A:
        L.append(f"| {n} | (미실시) | | | | |")
        continue
    L.append(f"| {n} | {f(A['에피−'][0]['rmse'], 1)} | {f(A['에피−'][3]['rmse'])} | {f(A['산화막−'][1]['rmse'])} | {f(A['산화막−'][0]['rmse'], 1)} | {f(np.mean([a[0]['rmse'] for a in A.values()]), 1)} |")
L += ["", "## 4. 사후 검증 (첫 배치로 학습 → 둘째 배치 23개 예측)", "", "| 모델 | " + " | ".join(ONAME) + " |", "|---|---|---|---|---|"]
L += [f"| {n} | " + " | ".join(row(n, "posthoc")) + " |" for n in names]
L += ["", "## 5. 학습 목표값에 가정 잡음(1배)을 입혀 학습 → 잡음 없는 값으로 평가", "", "| 모델 | " + " | ".join(ONAME) + " |", "|---|---|---|---|---|"]
L += [f"| {n} | " + " | ".join(row(n, "noise1")) + " |" for n in names]
L += ["", "## 6. 불확실도 (교차검증에서 실제 오차가 모델 σ 의 2배 안에 든 비율 / 오차÷σ 의 RMS)", "", "| 모델 | Vth | gm | Id(4V) | BV |", "|---|---|---|---|---|"]
for n in names:
    c = R[n]["cv"]
    L.append(f"| {n} | " + " | ".join("-" if c[j]["cov2"] is None else f"{100 * c[j]['cov2']:.0f} % / {c[j]['zrms']:.2f}" for j in range(4)) + " |")
L += ["", "이상적 값은 95 % / 1.00. 클수록 과신.", ""]
L += ["## 7. 소요 시간 (평가 전체, 초)", "", "| 모델 | 초 |", "|---|---|"] + [f"| {n} | {R[n]['seconds']:.0f} |" for n in names]
if SP:
    L += ["", "## 8. 배포 형태와 추론 속도 (이 PC CPU)", "", "| 방식 | 1점 지연(ms) | 10만 점(초) | 비고 |", "|---|---|---|---|"]
    for k, v in SP.items():
        if isinstance(v, dict) and "sec_100k" in v:
            L.append(f"| {k} | {v['ms_per_call_1pt']:.3f} | {v['sec_100k']:.2f} | |")
    L += ["", "```json", json.dumps({k: v for k, v in SP.items() if not (isinstance(v, dict) and 'sec_100k' in v)}, ensure_ascii=False, indent=1), "```"]
# 그림
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
for fn in ("Malgun Gothic", "NanumGothic"):
    if fn in {x.name for x in matplotlib.font_manager.fontManager.ttflist}:
        plt.rcParams["font.family"] = fn
        break
plt.rcParams["axes.unicode_minus"] = False
fig, ax = plt.subplots(2, 4, figsize=(17, 7))
for j in range(4):
    for r, key in enumerate(("cv", "posthoc")):
        vals = [R[n][key][j]["rmse"] / TARGET[j] for n in names]
        a = ax[r, j]
        a.barh(range(len(names)), vals, color=["#2a9d8f" if v <= 1 else "#e76f51" for v in vals])
        a.set_yticks(range(len(names)))
        a.set_yticklabels([n.split(" ", 1)[1] for n in names] if j == 0 else [], fontsize=8)
        a.invert_yaxis()
        a.axvline(1, color="k", ls="--", lw=0.8)
        a.set_xscale("log")
        a.set_title(f"{ONAME[j]} " + ("교차검증" if key == "cv" else "사후 검증") + " (기준=1)", fontsize=9)
fig.tight_layout()
fig.savefig(OUT / "비교_정확도.png", dpi=130)
(OUT / "비교결과.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
