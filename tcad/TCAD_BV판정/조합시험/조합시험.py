"""고칠것 6-C: 소량 보강 시험.
  (1) 조합 시험 5점: 노브를 동시에 ±10 % 틀었을 때 "하나씩 틀었을 때 변화의 합"과 맞는가 (가산성). IV 와 진짜 BV(곡선 추적).
  (2) BV 단계 시험 6점: 에피 ±20/±30 %, 산화막 ±20 % 의 BV. 에피에서 BV 가 단조 감소하는가 (규칙 B2), B1·B3 도 확인.
기존 코드는 가져다 쓰기만 하고(단계시험.py, BV_Ron_영향도.py) 기존 폴더에는 아무것도 쓰지 않는다. 온저항 단계는 돌리지 않는다.

  python 조합시험.py selftest   # TCAD 없이 deck, 파서, 판정 규칙, 기존 결과 읽기 점검 (몇 초)
  python 조합시험.py run        # 전체 실행 (조합 5 x (IV+BV) + BV 6). 끝난 실행은 건너뜀. 약 2시간 추정 (병렬 3개 기준)
  python 조합시험.py report     # 저장된 결과로 표와 요약만 다시 만듦
환경변수: DBASCII, TCAD_WORKERS(기본 3), TCAD_TIMEOUT(초, 기본 3600). BV 가 오래 걸리면 TCAD_TIMEOUT=5400 으로 늘린다.
"""
import csv
import importlib.util
import json
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True                                 # 기존 폴더에 __pycache__ 를 만들지 않는다
HERE = Path(__file__).resolve().parent
ROOT = next(p for p in (HERE, *HERE.parents) if (p / "최종_trench_template.in").exists())   # TCAD_ML. 폴더를 옮겨도 찾는다
sys.path[:0] = [str(ROOT / "TCAD_노이즈판정"), str(ROOT / "TCAD_노이즈판정" / "구분가능성")]                  # 노이즈가정.py 는 지금 구분가능성/ 안에 있다
import 노이즈가정 as ng                                         # 합성 오차를 측정 잡음(가정) 단위로 판정한다


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


st = _load(ROOT / "TCAD_단계실행" / "단계시험" / "단계시험.py", "stage_test")           # deck 만들기, IV 파서, 실행
bvr = _load(ROOT / "TCAD_BV_Ron분석" / "BV_온저항" / "BV_Ron_영향도.py", "bv_ron")        # 곡선 추적 BV deck, 파서
RUNS, OUT = HERE / "runs", HERE / "결과"
WORK = ROOT / "_work"
STEP_RUNS = ROOT / "TCAD_단계실행" / "단계시험" / "runs"

# ---- 시험 목록 (결과를 보기 전에 정해 둔 것) ----
COMBOS = {                                                      # 이름 -> 노브 비율. 모두 ±10 % 라서 예측에 TCAD_BV_Ron분석의 실측을 그대로 쓴다
    "조합1_도즈-10_산화막+10": {"dose": 0.9, "tox": 1.1},     # Vth 가 거의 상쇄되는 최악의 쌍
    "조합2_도즈+10_산화막-10": {"dose": 1.1, "tox": 0.9},
    "조합3_에피+10_산화막+10": {"epi": 1.1, "tox": 1.1},
    "조합4_에피-10_도즈+10":   {"epi": 0.9, "dose": 1.1},
    "조합5_도즈-10_에피+10_산화막+10": {"dose": 0.9, "epi": 1.1, "tox": 1.1},
}
BV_STEPS = [("epi", 0.7), ("epi", 0.8), ("epi", 1.2), ("epi", 1.3), ("tox", 0.8), ("tox", 1.2)]   # 구조는 단계시험 결과를 재사용
KO = st.KO
IDX = [0, 1, 2, 4]                                              # 분석 출력 순서(Vth mV, gm %, Id4V %, Id(Vd=4V) %, BV V)에서 이번에 비교하는 것
LABEL = {0: "Vth(mV)", 1: "gm(%)", 2: "Id(4V)(%)", 4: "BV(V)"}
PASS_SIGMA, WARN_SIGMA = 0.5, 1.0                               # 합성 오차 ≤ 0.5σ 통과, ≤ 1σ 주의, 그 위는 가산 불가 (σ = 가정 측정 잡음)
B3_TOL = 0.6                                                    # 규칙 B3: 판정 전류 1e-9 vs 1e-6 의 BV 차이 허용 (V)


def tag_of(name):
    return {"조합1": "c1", "조합2": "c2", "조합3": "c3", "조합4": "c4", "조합5": "c5"}[name[:3]]


def step_tag(knob, ratio):
    return f"{knob}_{'m' if ratio < 1 else 'p'}{round(abs(ratio - 1) * 100)}"


def step_name(knob, ratio):
    return f"BV단계_{KO[knob]}_{'감소' if ratio < 1 else '증가'}{round(abs(ratio - 1) * 100)}퍼"


# ---------------------------------------------------------------- 실행
def run_bv(final, tag, bv_in_name="입력deck_진짜항복전압.in", log_name="실행기록_진짜항복전압.log"):
    """final/소자구조.str 을 읽어 곡선 추적 BV 를 계산한다. 반환: bvt_* 항목 dict."""
    d = WORK / f"{tag}_bv"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(final / "소자구조.str", d / f"{tag}.str")
    (d / "bvt.in").write_text(bvr.TRUEBV_DECK.format(tag=tag), encoding="utf-8")
    t0 = time.time()
    status = st.run_deck_retry(d, "bvt.in", "bvt_console.log")
    text = (d / "bvt_console.log").read_text(errors="ignore") if (d / "bvt_console.log").exists() else ""
    pts = bvr.parse_rows(text)
    for src, new in (("bvt.in", bv_in_name), ("bvt_console.log", log_name)):
        if (d / src).exists():
            shutil.copy(d / src, final / new)
    shutil.rmtree(d, ignore_errors=True)
    return {"bvt_status": status, "bvt_points": pts, "bvt_seconds": round(time.time() - t0, 1),
            "bvt_levels": {f"{lv:g}": bvr.bv_at(pts, lv) for lv in bvr.TRUEBV_LEVELS}}


def run_combo(name, ratios):
    final = RUNS / name
    cache = final / "결과.json"
    r = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    tag = tag_of(name)
    if r.get("status") != "ok":                                  # IV
        d = WORK / f"cb_{tag}"
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
        (d / "deck.in").write_text(st.make_deck(tag, ratios), encoding="utf-8")
        t0 = time.time()
        iv_status = st.run_deck_retry(d, "deck.in", "console.log")
        text = (d / "console.log").read_text(errors="ignore") if (d / "console.log").exists() else ""
        pts = st.parse_iv(text)
        f = st.features(pts)
        r = {"name": name, "ratios": ratios, "iv_status": iv_status, "points": pts, "warnings": len(st.WARN_RE.findall(text)), **f,
             "status": "ok" if f and (d / f"{tag}.str").exists() else "failed", "seconds": round(time.time() - t0, 1)}
        final.mkdir(parents=True, exist_ok=True)
        for src, new in (("deck.in", "입력deck.in"), ("console.log", "실행기록.log"), (f"{tag}.str", "소자구조.str")):
            if (d / src).exists():
                shutil.move(str(d / src), str(final / new))
        shutil.rmtree(d, ignore_errors=True)
        cache.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    if r["status"] == "ok" and not r.get("bvt_levels"):         # BV
        r.update(run_bv(final, tag))
        cache.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    print(f"{name:34s} IV {r['status']:6s} Vth={r.get('vth')}  BV(1e-9)={(r.get('bvt_levels') or {}).get('1e-09')}", flush=True)
    return r


def run_step(knob, ratio):
    name = step_name(knob, ratio)
    final = RUNS / name
    cache = final / "결과.json"
    r = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    if not r.get("bvt_levels"):
        final.mkdir(parents=True, exist_ok=True)
        shutil.copy(STEP_RUNS / st.name_of(knob, ratio) / "소자구조.str", final / "소자구조.str")   # 읽기만 함, 복사본으로 계산
        r = {"name": name, "knob": knob, "ratio": ratio, **run_bv(final, step_tag(knob, ratio))}
        cache.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    print(f"{name:34s} BV(1e-9)={(r.get('bvt_levels') or {}).get('1e-09')}  ({r.get('bvt_seconds')}초)", flush=True)
    return r


def run_all():
    t0 = time.time()
    with ThreadPoolExecutor(st.WORKERS) as ex:
        futs = [ex.submit(run_combo, n, r) for n, r in COMBOS.items()] + [ex.submit(run_step, k, r) for k, r in BV_STEPS]
        for fu in futs:
            fu.result()
    print(f"전체 {time.time() - t0:.0f}초")


# ---------------------------------------------------------------- 기존 결과 읽기 (TCAD_BV_Ron분석, 읽기만 함)
def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _pick(r, sub):
    return float(r[next(k for k in r if sub in k)])


def prior():
    """기준값과 노브별 ±10 % 의 (Vth V, gm, Id4V, Id(Vd=4V), BV) 와 BV 1e-9/1e-6."""
    r1, r2 = _rows(st.PREV1), _rows(st.PREV2)

    def get(k1, k2):
        a, b = next(r for r in r1 if k1 in r["실험"]), next(r for r in r2 if k2 in r["실험"])
        return np.array([_pick(a, "Vth("), _pick(a, "gm("), _pick(a, "Id_4V"), _pick(b, "Id(Vd=4V"), _pick(b, "BV(V) 판정기준")])
    out = {"base": get("기준값_1회", "기준값")}
    for k in ("dose", "epi", "tox"):
        for w, rt in (("감소", 0.9), ("증가", 1.1)):
            out[(k, rt)] = get(f"{KO[k]}_{w}10퍼", f"{KO[k]}_{w}10퍼")
    return out


def delta(y, y0):                                               # 분석과 같은 단위: Vth mV, gm·Id %, BV V
    return np.array([(y[0] - y0[0]) * 1000, 100 * (y[1] / y0[1] - 1), 100 * (y[2] / y0[2] - 1), 100 * (y[3] / y0[3] - 1), y[4] - y0[4]])


def prior_bv(knob, ratio):
    """±10 % 와 기준값의 BV (1e-9 기준)."""
    p = prior()
    return (p["base"] if ratio == 1.0 else p[(knob, ratio)])[4]


# ---------------------------------------------------------------- 판정
def judge_add(err_over_sigma):
    a = abs(err_over_sigma)
    return "통과" if a <= PASS_SIGMA else ("주의" if a <= WARN_SIGMA else "가산 불가")


def check_bv_rules(r):
    """B1: 곡선 추적이 1e-9 A/μm 에 닿고 정상 종료, B3: 1e-9 와 1e-6 기준 BV 차이가 B3_TOL 이내. -> (B1, B3) 각각 True/False."""
    lv = r.get("bvt_levels") or {}
    b1 = r.get("bvt_status") == "ok" and lv.get("1e-09") is not None
    b3 = lv.get("1e-09") is not None and lv.get("1e-06") is not None and abs(lv["1e-09"] - lv["1e-06"]) <= B3_TOL
    return b1, b3


def monotonic(vals, direction):
    """vals 가 direction(-1 감소, +1 증가) 방향으로 엄격 단조인가. 비교할 점이 모자라거나 None 이 있으면 None."""
    if len(vals) < 2 or any(v is None for v in vals):
        return None
    return all((b - a) * direction > 0 for a, b in zip(vals, vals[1:]))


def load_all():
    combos = {n: json.loads((RUNS / n / "결과.json").read_text(encoding="utf-8")) for n in COMBOS if (RUNS / n / "결과.json").exists()}
    steps = {(k, r): json.loads((RUNS / step_name(k, r) / "결과.json").read_text(encoding="utf-8"))
             for k, r in BV_STEPS if (RUNS / step_name(k, r) / "결과.json").exists()}
    return combos, steps


def report():
    OUT.mkdir(exist_ok=True)
    combos, steps = load_all()
    p = prior()
    y0, sig = p["base"], ng.sigma_analysis()
    L = ["# 6-C 소량 보강 시험 결과", "",
         f"- 합성 오차 = (실측 변화) − (노브를 하나씩 틀었을 때 변화의 합). 오차를 가정 측정 잡음 σ로 나눠 판정: ≤ {PASS_SIGMA}σ 통과, ≤ {WARN_SIGMA}σ 주의, 그 위는 가산 불가.",
         f"- 가정 잡음(`노이즈가정.py`): {ng.describe()}. **판정 기준은 가정이다.**", "", "## 1. 조합 시험 (가산성)", ""]
    rows, csv_rows = [], []
    for name, r in combos.items():
        if r.get("status") != "ok":
            rows.append(f"| {name} | IV 실패 | | | | |")
            continue
        meas_bv = (r.get("bvt_levels") or {}).get("1e-09")
        y = np.array([r["vth"], r["gm"], r["id4v"], np.nan, meas_bv if meas_bv is not None else np.nan])
        y[3] = y0[3]                                            # Id(Vd=4V)는 이번에 안 돌림: 비교에서 제외
        d_meas = delta(y, y0)
        d_pred = sum(delta(p[(k, rt)], y0) for k, rt in ((k, v) for k, v in r["ratios"].items()))
        for i in IDX:
            if np.isnan(d_meas[i]):
                rows.append(f"| {name} | {LABEL[i]} | {d_pred[i]:+.2f} | 측정 없음 | | |")
                continue
            e = d_meas[i] - d_pred[i]
            v = judge_add(e / sig[i])
            rows.append(f"| {name} | {LABEL[i]} | {d_pred[i]:+.2f} | {d_meas[i]:+.2f} | {e:+.2f} ({e / sig[i]:+.2f}σ) | {v} |")
            csv_rows.append([name, LABEL[i], round(d_pred[i], 3), round(d_meas[i], 3), round(e, 3), round(e / sig[i], 3), v])
    L += ["| 조합 | 출력 | 예측 (합) | 실측 | 오차 | 판정 |", "|---|---|---|---|---|---|"] + rows
    verdicts = [c[-1] for c in csv_rows]
    if verdicts:
        L += ["", f"- 합계: 통과 {verdicts.count('통과')}, 주의 {verdicts.count('주의')}, 가산 불가 {verdicts.count('가산 불가')} (총 {len(verdicts)}칸)."]
    L += ["", "## 2. BV 단계 (에피, 산화막)", ""]
    bvtab, b_rules = {}, []
    for (k, rt), r in steps.items():
        bvtab[(k, rt)] = (r.get("bvt_levels") or {}).get("1e-09")
        b_rules.append((step_name(k, rt), *check_bv_rules(r)))
    for k in ("epi", "tox"):
        for rt in (0.9, 1.0, 1.1):
            bvtab.setdefault((k, rt), prior_bv(k, rt))
    L += ["| 노브 | 비율 | BV (V, 1e-9 A/μm 기준) |", "|---|---|---|"]
    for k in ("epi", "tox"):
        for rt in sorted(rt for kk, rt in bvtab if kk == k):
            L.append(f"| {KO[k]} | {round((rt - 1) * 100):+d} % | {'-' if bvtab[(k, rt)] is None else format(bvtab[(k, rt)], '.2f')} |")
    ep = [bvtab.get(("epi", rt)) for rt in (0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3)]
    tx = [bvtab.get(("tox", rt)) for rt in (0.8, 0.9, 1.0, 1.1, 1.2)]
    m_ep, m_tx = monotonic(ep, -1), monotonic(tx, +1)
    fmt = lambda m: "확인 불가 (점이 모자람)" if m is None else ("통과" if m else "**의심**")
    L += ["", f"- 규칙 B2 (에피 −30 % → +30 % 에서 BV 단조 감소): {fmt(m_ep)}",
          f"- 참고 (산화막 −20 % → +20 % 에서 BV 단조 증가): {fmt(m_tx)}"]
    for n, b1, b3 in b_rules:
        L.append(f"- {n}: B1 {'통과' if b1 else '**실패**'}, B3 {'통과' if b3 else '**의심**'}")
    for name, r in combos.items():
        if r.get("bvt_levels"):
            b1, b3 = check_bv_rules(r)
            L.append(f"- {name}: B1 {'통과' if b1 else '**실패**'}, B3 {'통과' if b3 else '**의심**'}")
    L += ["", "## 한계", "- 조합 5점, 모두 ±10 % 한 가지 크기다. 상호작용이 더 큰 구간(±20 % 이상)은 보지 않았다.",
          "- 판정 기준(0.5σ, 1σ)은 가정이다. 예측은 노브별 ±10 % 실측의 합이며 곱셈 효과(교차항)는 무시했다.",
          "- Id(Vd=4V)와 온저항은 이번에 돌리지 않아 비교하지 않았다 (구분 가능성 분석에서 추가 정보가 없음)."]
    (OUT / "조합시험_요약.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    with open(OUT / "조합시험_결과표.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["조합", "출력", "예측(합)", "실측", "오차", "오차/σ", "판정"])
        w.writerows(csv_rows)
    print("\n".join(L))


# ---------------------------------------------------------------- 점검
def selftest():
    for n, ratios in COMBOS.items():                             # 다중 노브 deck 치환
        tag = tag_of(n)
        deck = st.make_deck(tag, ratios)
        assert "{" not in deck and f"structure outfile={tag}.str" in deck
        for k, v in ratios.items():
            key = {"dose": "DOSE", "epi": "N_DRIFT", "tox": "TOX"}[k]
            assert f"set {key} = {st.BASE[k] * v:.8g}" in deck, (n, k)
        others = [k for k in st.BASE if k not in ratios]
        assert all(f"set {k} = {st.BASE[kk]:.8g}" in deck for k, kk in (("DIFF_TIME", "diff"),)) and others
    assert len({tag_of(n) for n in COMBOS}) == len(COMBOS)
    for k, r in BV_STEPS:                                        # BV 단계의 입력 구조가 있는지
        assert (STEP_RUNS / st.name_of(k, r) / "소자구조.str").exists(), (k, r)
    assert [step_name("epi", 0.7), step_name("tox", 1.2)] == ["BV단계_에피도핑_감소30퍼", "BV단계_산화막두께_증가20퍼"]
    # 기존 결과를 읽어서 기준값과 BV 파서 재현
    p = prior()
    assert abs(p["base"][0] - 2.25829) < 1e-3 and abs(p["base"][4] - 41.117) < 1e-2
    bvlog = ROOT / "TCAD_BV_Ron분석" / "BV_온저항" / "runs" / "1_기준값" / "실행기록_진짜항복전압.log"
    pts = bvr.parse_rows(bvlog.read_text(errors="ignore"))
    assert abs(bvr.bv_at(pts, 1e-9) - 41.117) < 1e-2, "BV 파서 불일치"
    # 판정 규칙
    assert judge_add(0.3) == "통과" and judge_add(-0.8) == "주의" and judge_add(1.5) == "가산 불가"
    assert monotonic([44, 43, 41, 39], -1) and monotonic([44, 43.5, 43.6], -1) is False and monotonic([1, None, 2], -1) is None
    ok = {"bvt_status": "ok", "bvt_levels": {"1e-09": 41.1, "1e-06": 40.8}}
    assert check_bv_rules(ok) == (True, True)
    assert check_bv_rules({**ok, "bvt_levels": {"1e-09": 41.1, "1e-06": 40.3}}) == (True, False)       # B3: 차이 0.8 V
    assert check_bv_rules({"bvt_status": "ok", "bvt_levels": {"1e-09": None, "1e-06": None}}) == (False, False)   # B1
    # 가산 예측: TCAD_BV_Ron분석 의 ±10 % 실측 합이 단일 노브와 같은 단위로 계산되는지
    d = delta(p[("dose", 0.9)], p["base"])
    assert abs(d[0] + 196.2) < 0.2 and abs(d[4] + 0.11) < 0.02
    print("selftest ok")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "run":
        run_all()
        report()
    elif cmd == "report":
        report()
    else:
        print(__doc__)
