"""두 번째 배치(번호 121~)는 첫 배치로 학습한 서로게이트가 한 번도 못 본 점이라 진짜 사후 검증이 된다. 이 스크립트는
  1. 새 샘플마다 서로게이트 예측과 TCAD 결과를 비교하고 (Vth, gm, Id(4V), BV),
  2. 크게 어긋난 점(BV 절벽 등)을 찾아 어느 구석인지 그림으로 보여 주고,
  3. 그 점들을 영역에서 빼는 규칙 후보(바디 도즈가 D 미만이고 에피가 E 초과인 조합 제외)를 제안한다.
끝난 샘플만 읽으므로 배치가 도는 중에도 돌릴 수 있다. TCAD 는 돌리지 않는다.

  python 영역점검.py     # 결과/영역점검.md, 결과/영역점검_도즈vs에피.png
"""
import csv
import json
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = next(p for p in (HERE, *HERE.parents) if (p / "최종_trench_template.in").exists())
OUT = HERE / "결과"
BASE_N = 120                                                    # 서로게이트를 학습한 첫 배치 크기
BV_ABS, BV_SIGMA, VTH_MV = 1.0, 5.0, 10.0                       # 이상 판정: BV 오차가 max(1 V, 5σ) 초과, Vth 오차 10 mV 초과 (평소 오차는 2~4 mV) — 가정


def runs():
    out = {}
    for p in (ROOT / "대량작업2" / "대량실행" / "runs").glob("*/결과.json"):
        j = json.loads(p.read_text(encoding="utf-8"))
        if j.get("status") == "ok" and "ratios" in j:
            out[int(j["번호"])] = j
    return out


def predict(models, X):
    f = np.c_[np.sqrt(X[:, 0]), np.log(X[:, 1]), X[:, 2]]
    v, sv = models["vth"].predict(f, return_std=True)
    g = models["log_gm"].predict(f)
    i = models["log_id4v"].predict(np.c_[f, v])
    b, sb = models["bv"].predict(f, return_std=True)
    return v, g, i, b, sb


def main():
    import joblib
    models = joblib.load(OUT / "서로게이트_GP.joblib")["models"]
    R = runs()
    nums = sorted(R)
    X = np.array([[R[n]["ratios"]["dose"], R[n]["ratios"]["epi"], R[n]["ratios"]["tox"]] for n in nums])
    v, g, i, b, sb = predict(models, X)
    rows = []
    for k, n in enumerate(nums):
        j = R[n]
        bv = (j.get("bvt_levels") or {}).get("1e-09")
        rows.append(dict(no=n, x=X[k], new=n > BASE_N, ev=(v[k] - j["vth"]) * 1000, eg=100 * (np.exp(g[k] - np.log(j["gm"])) - 1),
                         ei=100 * (np.exp(i[k] - np.log(j["id4v"])) - 1), bv=bv, bp=b[k], sb=sb[k], eb=(b[k] - bv) if bv else None, arm=j.get("확장축", "")))
    new = [r for r in rows if r["new"]]
    for r in new:
        r["bv_flag"] = r["eb"] is not None and abs(r["eb"]) > max(BV_ABS, BV_SIGMA * r["sb"])
        r["vth_flag"] = abs(r["ev"]) > VTH_MV
    done_bv = [r for r in new if r["eb"] is not None]
    L = ["# 영역 점검: 두 번째 배치 vs 첫 배치로 학습한 서로게이트", "",
         f"- 지금까지 끝난 새 샘플 {len(new)}개 (BV 까지 끝난 것 {len(done_bv)}개). 서로게이트는 첫 배치 {BASE_N}개 + 단일 노브 점으로만 학습했다 → 모든 비교는 **학습에 쓰지 않은 점에 대한 사후 검증**이다.",
         f"- 이상 판정(가정): BV 오차 > max({BV_ABS} V, {BV_SIGMA:g}σ) 또는 Vth 오차 > {VTH_MV:g} mV.", "",
         "## 1. 새 샘플별 예측 오차 (예측 − 실제)", "",
         "| 번호 | 팔 | 도즈 | 에피 | 산화막 | Vth(mV) | gm(%) | Id4V(%) | BV 실제 | BV 예측 | 예측σ | BV 오차(V) | 판정 |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in new:
        flag = ("**BV 이상** " if r["bv_flag"] else "") + ("**Vth 이탈**" if r["vth_flag"] else "")
        bvs = f"{r['bv']:.2f} | {r['bp']:.2f} | {r['sb']:.3f} | {r['eb']:+.3f}" if r["eb"] is not None else "(진행 중) | | | "
        L.append(f"| {r['no']} | {r['arm']} | {r['x'][0]:.2f} | {r['x'][1]:.2f} | {r['x'][2]:.2f} | {r['ev']:+.1f} | {r['eg']:+.2f} | {r['ei']:+.2f} | {bvs} | {flag or '정상'} |")
    ok = [r for r in done_bv if not r["bv_flag"]]
    if ok:
        L += ["", f"- BV 이상이 아닌 {len(ok)}개의 BV 오차 RMS {np.sqrt(np.mean([r['eb'] ** 2 for r in ok])):.3f} V, Vth 오차 RMS {np.sqrt(np.mean([r['ev'] ** 2 for r in new if not r['vth_flag']])):.1f} mV (이상 점 제외)."]
    bad = [r for r in new if r["bv_flag"] or r["vth_flag"]]
    L += ["", f"- **이상으로 판정된 샘플 {len(bad)}개**: " + (", ".join(f"{r['no']}번(도즈 {r['x'][0]:.2f}, 에피 {r['x'][1]:.2f})" for r in bad) if bad else "없음"), ""]
    # 규칙 후보: 도즈 < D 이고 에피 > E 인 조합 제외
    collapsed = [r for r in done_bv if r["bv_flag"]]
    normal_bv = [r for r in rows if r["bv"] is not None and not (r["new"] and r.get("bv_flag"))]
    allx = np.array([r["x"] for r in rows])
    L += ["## 2. 영역에서 뺄 구석 (규칙 후보)", ""]
    if not collapsed:
        L += ["BV 이상 점이 아직 없어서 규칙이 필요하지 않다."]
    else:
        cand = []
        for D in np.arange(0.70, 1.051, 0.025):
            for E in np.arange(1.00, 1.701, 0.05):
                excl = lambda x: x[0] < D and x[1] > E
                if all(excl(r["x"]) for r in collapsed):
                    cand.append((sum(excl(r["x"]) for r in normal_bv), int(np.sum((allx[:, 0] < D) & (allx[:, 1] > E))), D, E))
        cand.sort()
        L += [f"BV 이상 점 {len(collapsed)}개를 **모두** 제외하면서 정상 BV 점을 가장 적게 제외하는 규칙 \"도즈 < D 이고 에피 > E\" 후보 (정상 BV 점 {len(normal_bv)}개 기준):", "",
              "| D | E | 제외되는 정상 BV 점 | 제외되는 전체 샘플 |", "|---|---|---|---|"]
        L += [f"| {D:.3f} | {E:.2f} | {a} | {c} |" for a, c, D, E in cand[:6]] if cand else ["(이 형태의 규칙으로는 모두 제외하지 못함)"]
        L += ["", "- 이 규칙은 이상 점이 적은 지금 단계의 **잠정안**이다. 배치가 모두 끝나고 이상 점이 더 모이면 다시 구한다. 경계 근처는 점이 적어서 세 번째 배치로 확인할 수 있다."]
    (OUT / "영역점검.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        for fn in ("Malgun Gothic", "NanumGothic", "AppleGothic"):
            if fn in {f.name for f in matplotlib.font_manager.fontManager.ttflist}:
                plt.rcParams["font.family"] = fn
                break
        plt.rcParams["axes.unicode_minus"] = False
        fig, ax = plt.subplots(figsize=(7, 5.4))
        old = [r for r in rows if not r["new"]]
        ax.scatter([r["x"][0] for r in old], [r["x"][1] for r in old], s=14, c="#bbbbbb", label="첫 배치")
        for r in new:
            bad_ = r.get("bv_flag") or r.get("vth_flag")
            ax.scatter(r["x"][0], r["x"][1], s=70 if bad_ else 30, c="#d62728" if r.get("bv_flag") else ("#ff9f1c" if bad_ else "#2a9d8f"), edgecolors="k", linewidths=0.5)
            ax.annotate(str(r["no"]), (r["x"][0], r["x"][1]), fontsize=6, xytext=(3, 3), textcoords="offset points")
        ax.axvline(0.7, color="gray", lw=0.8, ls=":")
        ax.set_xlabel("바디 도즈 (기준 대비 비율)")
        ax.set_ylabel("에피 도핑 (기준 대비 비율)")
        ax.set_title("회색 = 첫 배치, 초록 = 새 샘플(정상), 주황 = Vth 이탈, 빨강 = BV 이상", fontsize=9)
        fig.tight_layout()
        fig.savefig(OUT / "영역점검_도즈vs에피.png", dpi=140)
    except Exception as e:
        print("그림 생략:", e)
    print("\n".join(L))


if __name__ == "__main__":
    main()
