"""진단 에이전트 평가: 실제 TCAD 샘플(학습 데이터)을 정답이 있는 시험 문제로 쓴다.
  - 시험 샘플의 TCAD 출력 + 가정 측정 잡음(노이즈가정.py 의 add_noise, 웨이퍼 N장 평균)을 측정값으로 에이전트에 주고 진짜 노브와 비교한다.
  - 서로게이트의 순환 논리를 피하려고 5-겹 교차검증으로 접힘마다 GP 를 새로 학습하고, 시험 샘플은 그 접힘의 학습에 쓰지 않는다.
  - 진단은 기본 모드로, 보정안 평가는 같은 서로게이트 기준(TCAD 확인 아님).
  python 에이전트평가.py        # 약 10분 -> 결과/에이전트평가.md, 결과/*.png, 결과/에이전트평가.json
"""
import re
import importlib.util
import json
import shutil
import sys
import tempfile
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OUT = HERE / "결과"
OUT.mkdir(exist_ok=True)
FINAL = HERE.parent / "최종ML"
spec = importlib.util.spec_from_file_location("agent", HERE / "진단에이전트.py")
AG = importlib.util.module_from_spec(spec)
spec.loader.exec_module(AG)


def load_file(pred, name):
    f = next(p for p in FINAL.glob("*.py") if pred(p.read_text(encoding="utf-8")))
    s = importlib.util.spec_from_file_location(name, f)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


B = load_file(lambda t: re.search(r"^def fit_all\b", t, re.M), "builder")
SUR = load_file(lambda t: re.search(r"^class Surrogate\b", t, re.M), "sur")
sys.path.insert(0, str(HERE.parent / "고칠것6" / "구분가능성"))
import 노이즈가정 as ng

assert ng.NOISE["vth"][1] == AG.NOISE["vth"] and ng.NOISE["gm"][1] == AG.NOISE["gm"] and ng.NOISE["id_4v"][1] == AG.NOISE["id4v"] and ng.NOISE["bv"][1] == AG.NOISE["bv"], "에이전트의 잡음 가정이 노이즈가정.py 와 다르다"

X, Y, kind, rows = B.load(FINAL / "데이터" / "학습데이터_최종.csv")
cfg = dict(bv_input=json.loads((FINAL / "모델" / "모델정보.json").read_text(encoding="utf-8"))["BV입력"], bv_log=False)
base_sur = SUR.Surrogate()
inside = base_sur.domain(X)
ev_idx = np.where(inside)[0]                               # 시험 후보: 영역 안의 모든 샘플 (대량 실행 + 영역 안 단일 노브)
always = np.where(~inside)[0]                              # 영역 밖 단일 노브(IV 만 사용)는 항상 학습에 포함
DELTA = 0.05
mask_of = lambda x: int(((np.abs(np.asarray(x) - 1) > DELTA) @ np.array([1, 2, 4])))
NS = (1, 5, 25)
rng = np.random.default_rng(2026)


def fold_surrogate(train_idx):
    m = B.fit_all(X[train_idx], Y[train_idx], cfg)
    tmp = Path(tempfile.mkdtemp())
    np.savez(tmp / "gp.npz", **{f"{k}__{kk}": np.asarray(vv, np.float64) for k in ("vth", "log_gm", "log_id4v", "bv") for kk, vv in B.export_gp(m[k]).items()})
    shutil.copy(FINAL / "모델" / "영역.json", tmp / "영역.json")
    shutil.copy(FINAL / "모델" / "모델정보.json", tmp / "모델정보.json")
    return SUR.Surrogate(tmp)


def measure(i, n):
    y = dict(vth=np.array([Y[i, 0]]), gm=np.array([np.exp(Y[i, 1])]), id_4v=np.array([np.exp(Y[i, 2])]), bv=np.array([Y[i, 3]]))
    z = ng.add_noise(y, scale=1.0, n_avg=n, rng=rng)
    return dict(vth=float(z["vth"][0]), gm=float(z["gm"][0]), id4v=float(z["id_4v"][0]), bv=float(z["bv"][0]))


from sklearn.model_selection import KFold

recs, comp, fine_meas = [], [], []
t0 = time.time()
for fold, (tr, te) in enumerate(KFold(5, shuffle=True, random_state=0).split(ev_idx)):
    sur = fold_surrogate(np.r_[ev_idx[tr], always])
    agent = AG.DiagnosisAgent(sur, seed=fold)
    comp_done = 0
    for i in ev_idx[te]:
        xt = X[i]
        has_bv = not np.isnan(Y[i, 3])
        for n in NS:
            for use_bv in ([False, True] if has_bv else [False]):
                m = measure(i, n)
                if not use_bv:
                    m["bv"] = None
                if fold == 4 and n == 25 and use_bv:
                    fine_meas.append((xt, m))
                for pri, lap in (("균등", None), ("희소", 0.10)):
                    r = agent.diagnose(m, n_wafers=n, prior_laplace=lap)
                    cat = np.array([r["범주확률"][c] for c in AG.CAT_NAMES])
                    lo = np.array([k["구간90"][0] for k in r["노브"]])
                    hi = np.array([k["구간90"][1] for k in r["노브"]])
                    mean = np.array([k["평균"] for k in r["노브"]])
                    recs.append(dict(fold=fold, i=int(i), n=n, bv=use_bv, prior=pri, truth=mask_of(xt), top=int(cat.argmax()), p=float(cat.max()), decided=bool(cat.max() >= agent.tau), cat=cat.tolist(),
                                     cover=((xt >= lo) & (xt <= hi)).tolist(), width=(hi - lo).tolist(), err=np.abs(mean - xt).tolist(), kind=str(kind[i])))
                    if pri == "균등":
                        r_uniform = r
                r = r_uniform
                if n == 5 and use_bv == has_bv and comp_done < 12 and not (SPEC_OK := (AG.SPEC["vth"][0] <= Y[i, 0] <= AG.SPEC["vth"][1])):
                    p = agent.compensate(r, samples=60, n=15)
                    xa = xt * np.array([p["도즈배율"], 1.0, p["산화막배율"]])
                    after = sur.raw_calibrated(xa[None])[0][0, 0]
                    dom = bool(sur.domain(xa[None])[0])
                    comp.append(dict(vth_before=float(Y[i, 0]), vth_after=float(after), ok_after=bool(dom and AG.SPEC["vth"][0] <= after <= AG.SPEC["vth"][1]), dose=p["도즈배율"], tox=p["산화막배율"], epi_dev=bool(abs(xt[1] - 1) > DELTA), truth=mask_of(xt)))
                    comp_done += 1
    print(f"접힘 {fold} 끝 ({time.time() - t0:.0f}초, 진단 {len(recs)}건, 보정 {len(comp)}건)", flush=True)

R_all = recs
R = [r for r in recs if r["prior"] == "균등"]
tab = lambda f: [r for r in R if f(r)]
L = ["# 진단 에이전트 평가", "",
     f"- 시험 문제: 학습 데이터의 TCAD 샘플 {len(ev_idx)}개 (영역 안; 대량 실행 + 영역 안 단일 노브). 측정값 = TCAD 출력 + 가정 잡음(웨이퍼 N장 평균). 5-겹 교차검증: 시험 샘플은 그 접힘의 서로게이트 학습에 쓰이지 않음.",
     f"- 진짜 범주: 노브 비율이 기준에서 {int(DELTA * 100)} % 넘게 벗어난 노브의 집합 (8가지). 판정 기준: 최다 범주 확률 ≥ {70} %. 총 진단 {len(R)}건.",
     "- 측정 잡음은 가정값(Vth 0.05 V, gm·Id 5 %, BV 0.3 V). 진단은 기본 모드(2단 GP)로 했다.", ""]
L += ["## 1. 웨이퍼 수와 BV 측정에 따른 진단 성능", "", "| 웨이퍼 N | BV | 진단 수 | 판정한 비율 | 판정이 맞은 비율(판정한 것 중) | 확신하고 틀린 비율(전체) | 항상 최다로 답할 때 정확도 | 평균 최다확률 |", "|---|---|---|---|---|---|---|---|"]
A = {}
for n in NS:
    for bv in (False, True):
        s = tab(lambda r: r["n"] == n and r["bv"] == bv)
        if not s:
            continue
        dec = [r for r in s if r["decided"]]
        right = [r for r in dec if r["top"] == r["truth"]]
        A[(n, bv)] = dict(n=len(s), dec=len(dec) / len(s), acc=(len(right) / len(dec) if dec else float("nan")), wrong=(len(dec) - len(right)) / len(s), map=np.mean([r["top"] == r["truth"] for r in s]), p=np.mean([r["p"] for r in s]))
        a = A[(n, bv)]
        L.append(f"| {n} | {'측정함' if bv else '없음'} | {a['n']} | {100 * a['dec']:.0f} % | {100 * a['acc']:.0f} % | {100 * a['wrong']:.0f} % | {100 * a['map']:.0f} % | {100 * a['p']:.0f} % |")
L += ["", "판정한 비율이 낮은 것은 오류가 아니라 \"구분 불가\"로 답한 것이다. 항상 최다 범주로 답하면 정확도가 위 표의 \"항상 최다로 답할 때\" 값이고, 기준을 넘길 때만 판정하면 맞은 비율이 올라가는 대신 판정 수가 줄어든다.", ""]
L += ["## 2. 노브별 90 % 신뢰구간의 정확성", "", "| 웨이퍼 N | BV | 도즈 포함률 | 에피 포함률 | 산화막 포함률 | 평균 구간폭(도즈/에피/산화막) | 평균 절대오차(도즈/에피/산화막) |", "|---|---|---|---|---|---|---|"]
for n in NS:
    for bv in (False, True):
        s = tab(lambda r: r["n"] == n and r["bv"] == bv)
        if not s:
            continue
        cv, wd, er = np.mean([r["cover"] for r in s], 0), np.mean([r["width"] for r in s], 0), np.mean([r["err"] for r in s], 0)
        L.append(f"| {n} | {'측정함' if bv else '없음'} | " + " | ".join(f"{100 * c:.0f} %" for c in cv) + " | " + "/".join(f"{w:.2f}" for w in wd) + " | " + "/".join(f"{e:.3f}" for e in er) + " |")
L += ["", "이상적인 포함률은 90 %. 에피는 BV 를 재지 않으면 사실상 관측되지 않으므로 BV 없음에서 구간이 넓고(0.3~1.7 의 넓은 범위) 포함률은 높게 나온다.", ""]
# 3) 진짜 범주별 (N=5, BV 있음 / 없음 별도)
L += ["## 3. 진짜로 벗어난 노브 개수별 (웨이퍼 5장)", "", "| BV | 벗어난 노브 수 | 진단 수 | 판정한 비율 | 판정이 맞은 비율(판정한 것 중) | 최다 범주가 맞은 비율 |", "|---|---|---|---|---|---|"]
for bv in (False, True):
    for kcount in (0, 1, 2, 3):
        s = tab(lambda r: r["n"] == 5 and r["bv"] == bv and bin(r["truth"]).count("1") == kcount)
        if len(s) < 3:
            continue
        dec = [r for r in s if r["decided"]]
        L.append(f"| {'측정함' if bv else '없음'} | {kcount} | {len(s)} | {100 * len(dec) / len(s):.0f} % | " + (f"{100 * np.mean([r['top'] == r['truth'] for r in dec]):.0f} %" if dec else "-") + f" | {100 * np.mean([r['top'] == r['truth'] for r in s]):.0f} % |")
L += [""]
# 4) 신뢰도 보정: 최다확률 구간별 실제 정확도
L += ["## 4. 확률이 믿을 만한가 (최다 범주 확률 구간별 실제로 맞은 비율, 전체 진단)", "", "| 최다 확률 구간 | 진단 수 | 실제 맞은 비율 | 평균 최다확률 |", "|---|---|---|---|"]
bins = [(0, 0.4), (0.4, 0.55), (0.55, 0.7), (0.7, 0.85), (0.85, 1.0001)]
rel = []
for lo, hi in bins:
    s = tab(lambda r: lo <= r["p"] < hi)
    if s:
        rel.append((np.mean([r["p"] for r in s]), np.mean([r["top"] == r["truth"] for r in s]), len(s)))
        L.append(f"| {lo:.2f}~{min(hi, 1):.2f} | {len(s)} | {100 * rel[-1][1]:.0f} % | {100 * rel[-1][0]:.0f} % |")
L += ["", "맞은 비율이 평균 확률과 비슷하면 확률을 믿을 수 있다. 훨씬 낮으면 과신, 훨씬 높으면 보수적.", ""]
# 5) 단일 노브 혼동 행렬
names = AG.CAT_NAMES
L += ["## 5. 진짜가 한 노브만 벗어난 경우 무엇으로 판정했나 (웨이퍼 5장, BV 있음, 진단 수 기준 비율)", "", "| 진짜 \\ 에이전트 최다 | " + " | ".join(names[1:]) + " | 판정 비율 |", "|---|" + "---|" * 8]
for t in (1, 2, 4):
    s = tab(lambda r: r["n"] == 5 and r["bv"] and r["truth"] == t)
    if not s:
        continue
    cnt = np.bincount([r["top"] for r in s], minlength=8) / len(s)
    L.append(f"| {names[t]} ({len(s)}건) | " + " | ".join(f"{100 * cnt[c]:.0f} %" for c in range(1, 8)) + f" | {100 * np.mean([r['decided'] for r in s]):.0f} % |")
L += ["", "도즈와 산화막이 서로 혼동되는 정도(도즈 행의 산화막·도즈+산화막 열, 산화막 행의 도즈·도즈+산화막 열)로 구별 가능성의 한계를 볼 수 있다.", ""]
# 6) 보정안
if comp:
    ok = np.mean([c["ok_after"] for c in comp])
    L += ["## 6. 보정안 시험 (서로게이트 기준, TCAD 확인 아님)", "", f"Vth 가 규격(1.7~2.6 V) 밖이던 시험 샘플 {len(comp)}개(웨이퍼 5장, BV 있으면 측정)에 에이전트가 낸 도즈·산화막 배율을 진짜 노브에 적용해 서로게이트로 예측한 Vth 가 규격 안에 드는 비율: **{100 * ok:.0f} %** (보정 전 0 %).",
          f"에피가 벗어난 {sum(c['epi_dev'] for c in comp)}건 포함. 평균 도즈 배율 {np.mean([c['dose'] for c in comp]):.3f}, 산화막 배율 {np.mean([c['tox'] for c in comp]):.3f}. 같은 서로게이트로 평가했으므로 낙관적일 수 있고 실제 확인은 TCAD 로 해야 한다.", ""]
# 7) 격자 해상도 점검: 같은 측정에 대해 격자 간격 0.025 와 0.0125 의 90 % 구간 포함률
if fine_meas:
    cov = {"거친 격자만 (간격 0.025)": [], "촘촘히 다시 계산 (간격 0.005, 에이전트 기본값)": []}
    for xt, m in fine_meas:
        for name, fl in zip(cov, (False, True)):
            rr = agent.diagnose(m, n_wafers=25, fine=fl)
            cov[name].append([k["구간90"][0] <= xt[j] <= k["구간90"][1] for j, k in enumerate(rr["노브"])])
    L += ["## 7. 촘촘한 격자 재계산의 영향 (웨이퍼 25장, BV 측정함, 마지막 접힘 " + str(len(fine_meas)) + "개)", "", "| 사후분포 계산 | 도즈 포함률 | 에피 포함률 | 산화막 포함률 |", "|---|---|---|---|"]
    for name in cov:
        c = np.mean(cov[name], 0)
        L.append(f"| {name} | " + " | ".join(f"{100 * v:.0f} %" for v in c) + " |")
    L += ["", "사후분포가 좁아져 90 % 구간의 폭이 격자 간격(0.025)과 비슷해지면 진짜 값이 격자 점 사이에 있어 포함률이 낮게 나온다. 에이전트는 이를 막으려고 거친 격자로 사후분포의 위치를 찾은 뒤 그 영역을 0.005 간격으로 다시 계산한다. 아래 표 외의 모든 표는 이 재계산을 켠 결과다.", ""]
# 8) 사전분포 비교
L += ["## 8. 사전분포 비교: 균등 vs 희소(라플라스 b=0.10, 노브 하나씩만 벗어나는 경우를 선호)", "", "| 웨이퍼 N | BV | 진짜 벗어난 노브 수 | 사전분포 | 진단 수 | 판정한 비율 | 판정이 맞은 비율 | 최다 범주가 맞은 비율 |", "|---|---|---|---|---|---|---|---|"]
for n, bv in ((5, False), (5, True), (25, True)):
    for kcount in (1, 2, 3):
        for pri in ("균등", "희소"):
            s = [r for r in R_all if r["n"] == n and r["bv"] == bv and r["prior"] == pri and bin(r["truth"]).count("1") == kcount]
            if len(s) < 3:
                continue
            dec = [r for r in s if r["decided"]]
            L.append(f"| {n} | {'측정함' if bv else '없음'} | {kcount} | {pri} | {len(s)} | {100 * len(dec) / len(s):.0f} % | " + (f"{100 * np.mean([r['top'] == r['truth'] for r in dec]):.0f} %" if dec else "-") + f" | {100 * np.mean([r['top'] == r['truth'] for r in s]):.0f} % |")
L += ["", "시험 문제의 대부분은 노브 세 개가 모두 벗어난 무작위 점이라 균등 사전분포(경우의 수가 많은 쪽을 선호)에 유리하다. 실제 공정에서 노브가 하나씩 벗어나는 경우가 많다고 믿는다면 희소 사전분포가 알맞다. 어느 쪽이 맞는지는 실제 공정 데이터가 없어 이 평가로는 알 수 없는 가정이다.", ""]
L += ["## 9. 해석", "", "해석과 한계는 README.md 의 \"평가 결과 요약\"에 정리했다.", ""]
(OUT / "에이전트평가.md").write_text("\n".join(L), encoding="utf-8")
json.dump(dict(recs=R_all, comp=comp), open(OUT / "에이전트평가.json", "w", encoding="utf-8"), ensure_ascii=False)
# 그림
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

for fn in ("Malgun Gothic", "NanumGothic"):
    if fn in {x.name for x in matplotlib.font_manager.fontManager.ttflist}:
        plt.rcParams["font.family"] = fn
        break
plt.rcParams["axes.unicode_minus"] = False
fig, ax = plt.subplots(1, 3, figsize=(15, 4.2))
for bv, c in ((False, "#e76f51"), (True, "#2a9d8f")):
    xs = [n for n in NS if (n, bv) in A]
    ax[0].plot(xs, [100 * A[(n, bv)]["dec"] for n in xs], "o-", color=c, label="BV " + ("측정함" if bv else "없음"))
    ax[1].plot(xs, [100 * A[(n, bv)]["acc"] for n in xs], "o-", color=c)
    ax[1].plot(xs, [100 * A[(n, bv)]["wrong"] for n in xs], "s--", color=c)
ax[0].set_title("판정한 비율 (%)")
ax[1].set_title("판정이 맞은 비율(실선) / 확신하고 틀린 비율(점선) (%)", fontsize=9)
for a in ax[:2]:
    a.set_xscale("log")
    a.set_xticks(NS)
    a.set_xticklabels(NS)
    a.set_xlabel("웨이퍼 수 N")
ax[0].legend()
if rel:
    ax[2].plot([100 * r[0] for r in rel], [100 * r[1] for r in rel], "o-")
    ax[2].plot([0, 100], [0, 100], "k--", lw=0.8)
    ax[2].set_xlabel("에이전트의 최다 범주 확률 (%)")
    ax[2].set_ylabel("실제 맞은 비율 (%)")
    ax[2].set_title("확률 보정")
fig.tight_layout()
fig.savefig(OUT / "에이전트평가_성능.png", dpi=130)
print("\n".join(L))
print(f"총 {time.time() - t0:.0f}초")
