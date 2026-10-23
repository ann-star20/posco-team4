"""Jetson 에서 모델이 제대로 도는지 확인한다: 테스트/jetson_테스트입력.csv 의 노브 비율을 넣고
  1) PC 에서 계산해 둔 값과 같은지 (기본 모드는 거의 정확히 같아야 한다),
  2) TCAD 정답이 있는 점은 예측이 얼마나 맞는지,
  3) 영역 밖 점은 NaN 으로 막히는지,
  4) (고정밀 모드를 쓸 수 있으면) 고정밀 값이 PC 값과 비슷한지
를 확인하고 결과를 jetson_결과.csv 로 저장한다.
  python jetson_검증.py
"""
import csv
import re
import importlib.util
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def load(classname):
    f = next(p for p in HERE.glob("*.py") if re.search(rf"^class {classname}\b", p.read_text(encoding="utf-8"), re.M) and p.name != Path(__file__).name)
    s = importlib.util.spec_from_file_location("m_" + classname, f)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


rows = list(csv.DictReader(open(HERE / "테스트" / "jetson_테스트입력.csv", encoding="utf-8-sig")))
X = np.array([[float(r["도즈"]), float(r["에피"]), float(r["산화막"])] for r in rows])
num = lambda r, k: float(r[k]) if r[k] != "" else np.nan
ref = {k: np.array([num(r, "PC_" + k) for r in rows]) for k in ("vth", "gm", "id4v", "bv")}
group = np.array([r["구분"] for r in rows])
ok_all = True


def check(name, cond, detail=""):
    global ok_all
    ok_all &= bool(cond)
    print(("통과  " if cond else "실패  ") + name + (f"  ({detail})" if detail else ""))


print(f"테스트 점 {len(X)}개 (구분별: " + ", ".join(f"{g} {int((group == g).sum())}" for g in dict.fromkeys(group)) + ")")
sur = load("Surrogate").Surrogate()
t = time.perf_counter()
r = sur.predict(X)
print(f"기본 모드 {len(X)}점 예측 {time.perf_counter() - t:.3f}초")
dom = ~np.isnan(ref["vth"])
rel = lambda a, b: np.abs(a - b) / np.maximum(np.abs(b), 1e-30)
diff = max(rel(r[k][dom], ref[k][dom]).max() for k in ("vth", "gm", "id4v", "bv"))
check("기본 모드 값이 PC 값과 같다", diff < 1e-6, f"최대 상대 차이 {diff:.2e}")
check("영역 밖 점은 NaN, 영역 안 점은 값이 있다", np.array_equal(~np.isnan(r["vth"]), dom) and np.array_equal(r["in_domain"], dom))
tc = group == "TCAD"
if tc.any():
    T = {k: np.array([num(x, "TCAD_" + k) for x in rows]) for k in ("vth", "gm", "id4v", "bv")}
    e = dict(vth=np.abs(r["vth"][tc] - T["vth"][tc]) * 1000, gm=100 * rel(r["gm"][tc], T["gm"][tc]), id4v=100 * rel(r["id4v"][tc], T["id4v"][tc]), bv=np.abs(r["bv"][tc] - T["bv"][tc]))
    print(f"TCAD 정답이 있는 {int(tc.sum())}점 (학습에 쓴 점이라 정확도 시험이 아니라 일치 확인): 평균 오차 Vth {e['vth'].mean():.2f} mV, gm {e['gm'].mean():.2f} %, Id {e['id4v'].mean():.2f} %, BV {e['bv'].mean():.2f} V")
    check("TCAD 점 예측이 정상 범위 (Vth 20 mV, gm·Id 10 %, BV 1 V 이내)", e["vth"].max() < 20 and e["gm"].max() < 10 and e["id4v"].max() < 10 and e["bv"].max() < 1)
check("σ 가 모두 양수", all(np.all(r[k][dom] > 0) for k in ("sigma_vth", "sigma_gm", "sigma_id4v", "sigma_bv")))
out = {"ID": [x["ID"] for x in rows], **{k: r[k] for k in ("vth", "gm", "id4v", "bv", "sigma_vth", "sigma_bv", "in_domain")}}
# 고정밀 모드 (있으면)
hp_idx = np.array([i for i, x in enumerate(rows) if x["PC_고정밀_bv"] != ""])
try:
    pipe = load("TwoStagePipeline").TwoStagePipeline()
    if pipe.high_precision_available and len(hp_idx):
        t = time.perf_counter()
        h = pipe.refine(X[hp_idx])
        print(f"고정밀 모드 {len(hp_idx)}점 {time.perf_counter() - t:.1f}초 (모드: {h['mode']})")
        hv = np.array([num(rows[i], "PC_고정밀_vth") for i in hp_idx])
        hb = np.array([num(rows[i], "PC_고정밀_bv") for i in hp_idx])
        dv, db = np.abs(h["vth"] - hv).max() * 1000, np.abs(h["bv"] - hb).max()
        check("고정밀 값이 PC 값과 비슷하다 (GPU/CPU 수치 차이 허용: Vth 5 mV, BV 0.3 V)", dv < 5 and db < 0.3, f"최대 차이 Vth {dv:.2f} mV, BV {db:.3f} V")
        out["고정밀_vth"] = [h["vth"][list(hp_idx).index(i)] if i in hp_idx else "" for i in range(len(rows))]
        out["고정밀_bv"] = [h["bv"][list(hp_idx).index(i)] if i in hp_idx else "" for i in range(len(rows))]
    else:
        print("고정밀 모드: 사용 불가 →", pipe.hp_error or "비활성", "(기본 모드만 확인)")
except Exception as e:
    print("고정밀 모드 확인 건너뜀:", type(e).__name__, e)
with open("jetson_결과.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(list(out))
    w.writerows(zip(*out.values()))
print("결과 저장: jetson_결과.csv")
print("== 전체 판정:", "모두 통과" if ok_all else "실패 항목 있음 (위 로그 확인)")
