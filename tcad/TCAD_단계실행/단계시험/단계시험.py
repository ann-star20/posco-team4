"""노브 하나씩 기준값에서 -30/-20/+20/+30 % 바꿔 IV와 온저항을 계산하고, 판정 규칙(I1~I5)으로 분류한다.
±10 % 와 기준값은 고칠것1 의 결과를 그대로 쓴다 (다시 돌리지 않음). 구조 deck 은 TCAD_ML/최종_trench_template.in 그대로.

  python 단계시험.py selftest     # TCAD 없이 deck 치환, 파서, 판정 규칙 점검 (몇 초)
  python 단계시험.py test         # 1개만 실행 (산화막 +20 %) 해서 연결과 판정을 확인
  python 단계시험.py run          # ±20, ±30 % 실행. 같은 방향은 안쪽부터, 실패나 의심이 나오면 바깥은 건너뜀. 끝난 실행은 건너뜀
  python 단계시험.py extend       # 위에 이어 ±40, ±50 % 까지 (실패나 의심이 나오면 거기서 멈춤)
  python 단계시험.py report       # 저장된 결과로 표와 요약만 다시 만듦
환경변수: DBASCII, TCAD_WORKERS(기본 3), TCAD_TIMEOUT(초, 기본 3600)
"""
import csv
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]                                   # TCAD_ML
RUNS, OUT = HERE / "runs", HERE / "결과"
WORK = ROOT / "_work"                                    # Silvaco 는 영문 경로에서 실행
TEMPLATE = (ROOT / "최종_trench_template.in").read_text(encoding="utf-8")
PREV1 = ROOT / "고칠것1" / "고칠것1_TCAD 설정" / "연결확인 결과" / "노브연결_결과표.csv"
PREV2 = ROOT / "고칠것1" / "BV_온저항" / "결과" / "BV_온저항_결과표.csv"
DBASCII = os.environ.get("DBASCII", r"C:\sedatools\lib\deckbuild\5.0.10.R\x86_64-windows\dbascii.exe")
SUPPORT = r"C:\sedatools\lib\support\x86_64-windows"
WORKERS = int(os.environ.get("TCAD_WORKERS", "3"))
TIMEOUT = int(os.environ.get("TCAD_TIMEOUT", "3600"))

BASE = {"dose": 7.7e12, "epi": 1.7e16, "diff": 30.0, "tox": 0.06}
KNOBS = os.environ.get("KNOBS", "dose,epi,tox").split(",")   # 프로젝트 노브 3개. 확산시간은 30분 고정 (이미 돌린 결과는 runs/ 에 보존)
KO = {"dose": "바디도즈", "epi": "에피도핑", "diff": "확산시간", "tox": "산화막두께"}
EXPECT = {"dose": +1, "tox": +1, "diff": -1, "epi": -1}   # 노브 +10% 때 Vth 와 Ron 이 움직이는 부호 (고칠것1 결과)
LEVELS = {"감소": (0.8, 0.7, 0.6, 0.5, 0.4, 0.3), "증가": (1.2, 1.3, 1.4, 1.5, 1.6, 1.7)}   # 방향별로 안쪽부터 바깥으로. run 은 앞 2개, extend 는 4개, extend2 는 6개


def sweep_for(knob, ratio):
    """Vth 가 3 V 를 넘어 4 V 스윕으로는 추출이 막히는 조건(산화막 +40 % 이상, 바디 도즈 +60 % 이상)은 게이트를 6 V 까지 스윕한다."""
    return 6.0 if (knob == "tox" and ratio >= 1.4) or (knob == "dose" and ratio >= 1.6) else 4.0
WARN_RE = re.compile(r"did not converge|cut back|cannot reduce residual|Convergence problem")

RON_DECK = """go atlas

mesh infile={tag}.str

electrode name=gate x.min=0.0 x.max=0.90 y.min=-1.0 y.max=1.2
electrode name=source x.min=1.05 x.max=2 y.min=-0.4 y.max=-0.29
electrode name=source x.min=2 x.max=2 y.min=-0.15 y.max=0.25
electrode name=drain bottom

contact name=gate n.poly

doping uniform n.type conc=1e20 region=3

models cvt srh auger bgn print
impact selberherr

method newton trap

solve init

solve vgate=0.5 vstep=0.5 vfinal=4.0 name=gate

log outf={tag}_ron.log

solve vdrain=0.05 vstep=0.05 vfinal=0.5 name=drain
solve vdrain=0.5 vstep=0.25 vfinal=4.0 name=drain

quit
"""


def name_of(knob, ratio, sweep=4.0):
    return f"{KO[knob]}_{'감소' if ratio < 1 else '증가'}{round(abs(ratio - 1) * 100)}퍼" + ("" if sweep == 4.0 else f"_스윕{sweep:g}V")


def tag_of(knob, ratio, sweep=4.0):
    return f"{knob}_{'m' if ratio < 1 else 'p'}{round(abs(ratio - 1) * 100)}" + ("" if sweep == 4.0 else f"_s{sweep:g}")


def make_deck(tag, ratio_by_knob, sweep=4.0):
    v = {k: f"{BASE[k] * ratio_by_knob.get(k, 1.0):.8g}" for k in BASE}
    deck = TEMPLATE.format(tag=tag, **v)
    if sweep != 4.0:                              # 구조는 그대로이고 게이트 스윕 상한만 바꾼다
        old = "solve vgate=0.0 vstep=0.1 vfinal=4.0 name=gate"
        assert old in deck, "스윕 줄을 찾지 못함"
        deck = deck.replace(old, f"solve vgate=0.0 vstep=0.1 vfinal={sweep:g} name=gate")
    return deck


# ---------------------------------------------------------------- 파서 (고칠것1 과 같은 방식)
_IV_RE = re.compile(r"V\(\s*gate\s*\)\s*=\s*([\d.]+).*?"
                    r"drain\s+[\d.eE+-]+\s+[\d.eE+-]+\s+[\d.eE+-]+\s+[\d.eE+-]+\s+([\-\d.eE+]+)", re.DOTALL)
_DR_RE = re.compile(r"V\(\s*drain\s*\)\s*=\s*([\-\d.eE+]+).*?"
                    r"drain\s+[\d.eE+-]+\s+[\d.eE+-]+\s+[\d.eE+-]+\s+[\d.eE+-]+\s+([\-\d.eE+]+)", re.DOTALL)


def parse_iv(text):
    return sorted({round(float(m.group(1)), 4): float(m.group(2)) for m in _IV_RE.finditer(text)}.items())


def parse_drain(text):
    return sorted({round(float(m.group(1)), 4): float(m.group(2)) for m in _DR_RE.finditer(text)}.items())


def features(points):
    if len(points) < 5:
        return {}
    vg, i = [p[0] for p in points], [p[1] for p in points]
    slopes = [((i[k] - i[k - 1]) / (vg[k] - vg[k - 1]), k) for k in range(1, len(vg)) if vg[k] > vg[k - 1]]
    gm, k = max(slopes)
    if gm <= 0:
        return {}
    id4v = {round(a, 3): b for a, b in points}.get(4.0, i[-1])        # 스윕이 6 V 까지여도 Id(4V)는 4 V 점의 전류
    return {"vth": vg[k] - i[k] / gm - 0.05, "gm": gm, "id4v": id4v, "i_leak": i[0]}


def ron_from(points):
    p = {round(v, 3): i for v, i in points}
    if 0.05 not in p or p[0.05] <= 0:
        return {}
    return {"ron": 0.05 / p[0.05], "id_vd4": p.get(4.0)}


# ---------------------------------------------------------------- 실행
def run_deck(d, deck, log):
    env = {**os.environ, "SILVACO": r"C:\sedatools", "SILVACOCORP": r"C:\sedatools",
           "PATH": SUPPORT + os.pathsep + os.environ.get("PATH", "")}
    try:
        subprocess.run([DBASCII, "-run", deck, "-outfile", log], cwd=d, env=env,
                       capture_output=True, text=True, timeout=TIMEOUT)
        return "ok"
    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception as e:
        return f"error:{e}"


def run_deck_retry(d, deck, log, tries=3):
    """Atlas 동시 기동이 겹치면 시작 직후 'File system error' 로 죽는 일이 있다 (계산 실패가 아님). 그 경우만 기다렸다 다시 돌린다."""
    for n in range(tries):
        st = run_deck(d, deck, log)
        text = (d / log).read_text(errors="ignore") if (d / log).exists() else ""
        if "File system error" not in text or n == tries - 1:
            return st
        time.sleep(30 + 30 * n)


def run_one(knob, ratio, sweep=4.0):
    final = RUNS / name_of(knob, ratio, sweep)
    cache = final / "결과.json"
    if cache.exists():
        r = json.loads(cache.read_text(encoding="utf-8"))
        if r.get("status") == "ok":
            return r
    tag = tag_of(knob, ratio, sweep)
    d = WORK / f"st_{tag}"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    (d / "deck.in").write_text(make_deck(tag, {knob: ratio}, sweep), encoding="utf-8")
    t0 = time.time()
    st = run_deck_retry(d, "deck.in", "console.log")
    iv_text = (d / "console.log").read_text(errors="ignore") if (d / "console.log").exists() else ""
    pts = parse_iv(iv_text)
    f = features(pts)
    r = {"knob": knob, "ratio": ratio, "sweep": sweep, "tag": tag, "values": {k: BASE[k] * (ratio if k == knob else 1) for k in BASE},
         "iv_status": st, "points": pts, "warnings": len(WARN_RE.findall(iv_text)), **f}
    if f and (d / f"{tag}.str").exists():                        # 같은 구조로 온저항 계산 (공정은 다시 안 돌림)
        (d / "ron.in").write_text(RON_DECK.format(tag=tag), encoding="utf-8")
        rst = run_deck_retry(d, "ron.in", "ron_console.log")
        rp = parse_drain((d / "ron_console.log").read_text(errors="ignore")) if (d / "ron_console.log").exists() else []
        r.update(ron_status=rst, ron_points=rp, **ron_from(rp))
    r["status"] = "ok" if (f and r.get("ron")) else "failed"
    if r["status"] != "ok" and "File system error" in iv_text:
        r["infra_error"] = True                 # 시작 오류가 재시도 후에도 남음: 경계가 아니라 다시 돌릴 대상
    r["seconds"] = round(time.time() - t0, 1)
    final.mkdir(parents=True, exist_ok=True)
    for src, new in (("deck.in", "입력deck.in"), ("console.log", "실행기록.log"), ("ron.in", "입력deck_온저항.in"),
                     ("ron_console.log", "실행기록_온저항.log"), (f"{tag}.str", "소자구조.str")):
        if (d / src).exists():
            shutil.move(str(d / src), str(final / new))
    cache.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(d, ignore_errors=True)
    return r


# ---------------------------------------------------------------- 기준값과 ±10% (고칠것1 결과 읽기)
def load_refs():
    """{(knob, ratio): {"vth":..., "ron":...}} 와 기준값. ±10% 는 고칠것1 의 표에서 읽는다."""
    def rows(path):
        return list(csv.DictReader(open(path, encoding="utf-8-sig")))
    r1, r2 = rows(PREV1), rows(PREV2)
    refs = {}
    base_vth = float(next(r for r in r1 if "기준값_1회" in r["실험"])["Vth(V)"])
    base_ron = float(next(r for r in r2 if "기준값" in r["실험"])["온저항 Ron(Ω·μm)"])
    refs[(None, 1.0)] = {"vth": base_vth, "ron": base_ron}
    for k in KNOBS:
        for word, ratio in (("감소", 0.9), ("증가", 1.1)):
            key = f"{KO[k]}_{word}10퍼"
            refs[(k, ratio)] = {"vth": float(next(r for r in r1 if key in r["실험"])["Vth(V)"]),
                                "ron": float(next(r for r in r2 if key in r["실험"])["온저항 Ron(Ω·μm)"])}
    return refs


# ---------------------------------------------------------------- 판정 규칙
def judge(res, refs, inner):
    """res: 실행 결과, inner: 같은 방향 바로 안쪽 점의 {"vth","ron"}. -> (판정, 위반한 규칙 목록)"""
    fail, doubt = [], []
    if res.get("infra_error"):
        return "재시도", ["시작오류"]                 # TCAD 계산 실패가 아니므로 경계로 보지 않는다
    pts = res.get("points") or []
    if res.get("status") != "ok":
        fail.append("I1")
    else:
        currents = [i for _, i in pts] + [i for _, i in res.get("ron_points", [])]
        if any(i <= 0 for i in currents) or res["ron"] <= 0 or not (res.get("id_vd4") or 0) > 0:
            fail.append("I2")
    if fail:
        return "실패", fail
    base, k, sgn = refs[(None, 1.0)], res["knob"], 1 if res["ratio"] > 1 else -1
    want = EXPECT[k] * sgn
    if (res["vth"] - base["vth"]) * want <= 0 or (res["ron"] - base["ron"]) * want <= 0:
        doubt.append("I3")
    if (res["vth"] - inner["vth"]) * want <= 0:
        doubt.append("I4")
    if res["warnings"] > 0:
        doubt.append("I5")
    sl = [((b - a) / (v1 - v0), k) for k, ((v0, a), (v1, b)) in enumerate(zip(pts, pts[1:]), 1) if v1 > v0]
    if len(pts) - 1 - max(sl)[1] < 5:            # I6: 최대 기울기 점 뒤에 점이 5개(0.5 V) 이상 있어야 Vth·gm 추출이 유효
        doubt.append("I6")
    return ("의심" if doubt else "정상"), doubt


def classify(results, refs):
    """안쪽(±10% 기준값)부터 바깥으로 이웃과 비교해 각 실행을 판정한다. 실패한 점의 바깥은 '건너뜀'. 실행하지 않은 바깥 단계는 표에 넣지 않는다."""
    out = {}
    for k in KNOBS:
        for word, ratios in LEVELS.items():
            inner = refs[(k, 0.9 if word == "감소" else 1.1)]
            dead = False
            for idx, r in enumerate(ratios):
                key = (k, r)
                cands = [x for x in results if x["knob"] == k and abs(x["ratio"] - r) < 1e-9]
                res = max(cands, key=lambda x: x.get("sweep", 4.0), default=None)      # 스윕을 늘려 다시 돌린 결과가 있으면 그것을 씀
                if dead:
                    if idx < 2:
                        out[key] = ("건너뜀", ["안쪽 실패"], None)
                elif res is None:
                    if idx < 2:
                        out[key] = ("미실행", [], None)
                else:
                    v, why = judge(res, refs, inner)
                    out[key] = (v, why, res)
                    dead = v == "실패"
                    inner = {"vth": res.get("vth"), "ron": res.get("ron")}
    return out


# ---------------------------------------------------------------- 실행 흐름과 보고서
def run_chain(knob, word, n, refs):
    """방향 하나를 안쪽부터 n 단계까지. 실패나 의심이 나오면 거기서 멈춘다 (바깥은 돌리지 않음)."""
    done = []
    inner = refs[(knob, 0.9 if word == "감소" else 1.1)]
    for r in LEVELS[word][:n]:
        sw = sweep_for(knob, r)
        res = run_one(knob, r, sw)
        done.append(res)
        v, why = judge(res, refs, inner)
        print(f"{name_of(knob, r, sw):24s} {res['status']:7s} {res['seconds']:7.1f}s  vth={res.get('vth')}  "
              f"ron={res.get('ron')}  경고={res.get('warnings')}  판정={v} {','.join(why)}", flush=True)
        if v != "정상":
            break
        inner = {"vth": res["vth"], "ron": res["ron"]}
    return done


def run_all(n):
    t0 = time.time()
    refs = load_refs()
    with ThreadPoolExecutor(WORKERS) as ex:
        futs = [ex.submit(run_chain, k, w, n, refs) for k in KNOBS for w in LEVELS]
        results = [r for fu in futs for r in fu.result()]
    print(f"전체 {time.time() - t0:.0f}초")
    return results


def load_results():
    out = []
    for k in KNOBS:
        for ratios in LEVELS.values():
            for r in ratios:
                for sw in (4.0, 6.0):
                    p = RUNS / name_of(k, r, sw) / "결과.json"
                    if p.exists():
                        out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def report(results):
    OUT.mkdir(exist_ok=True)
    refs = load_refs()
    cl = classify(results, refs)
    b = refs[(None, 1.0)]
    rows = []
    for (k, r), (v, why, res) in sorted(cl.items(), key=lambda x: (KNOBS.index(x[0][0]), x[0][1])):
        rows.append([name_of(k, r, res.get("sweep", 4.0) if res else 4.0), v, ",".join(why), r, *(res.get(x) if res else None for x in
                     ("vth", "gm", "id4v", "ron", "id_vd4", "warnings", "seconds"))])
    with open(OUT / "단계시험_결과표.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["실험", "판정", "위반규칙", "비율", "Vth(V)", "gm", "Id_4V", "Ron(옴·um)", "Id(Vd=4V)", "IV수렴경고", "소요(초)"])
        w.writerows(rows)
    L = ["# 노브 단계 시험 결과 (IV 규칙 I1~I5)", "",
         f"- 기준 Vth = {b['vth']:.4f} V, Ron = {b['ron']:.4g} Ω·μm. ±10% 는 고칠것1 결과 사용.", "",
         "| 노브 | 방향 | 단계 | 판정 | 위반 규칙 | Vth (V) | Ron (Ω·μm) | IV 경고 |", "|---|---|---|---|---|---|---|---|"]
    for (k, r), (v, why, res) in sorted(cl.items(), key=lambda x: (KNOBS.index(x[0][0]), x[0][1])):
        vth = f"{res['vth']:.4f}" if res and res.get("vth") is not None else "-"
        ron = f"{res['ron']:.4g}" if res and res.get("ron") else "-"
        sw = " (스윕 6V)" if res and res.get("sweep", 4.0) != 4.0 else ""
        L.append(f"| {KO[k]} | {'감소' if r < 1 else '증가'} | {round(abs(r - 1) * 100)}%{sw} | {v} | {','.join(why) or '-'} | "
                 f"{vth} | {ron} | {res['warnings'] if res else '-'} |")
    L += ["", "판정: 정상 = 위반 없음, 의심 = I3~I6 위반(확인 필요), 실패 = I1·I2 위반(범위에서 제외, 바깥 단계는 건너뜀).",
          "I6 (추가 규칙): 최대 기울기 점 뒤에 점이 5개(0.5 V) 이상 있어야 Vth·gm 추출이 유효. 확장 시험에서 산화막 +40/+50 % 의 "
          "추출이 스윕 상한(4 V)에 막힌 것을 발견해 추가했다. '5개'는 가정이고, 추출이 유효했던 가장 바깥 점(바디 도즈 +50 %)이 5개였다.",
          "한계: 임계값이 있는 규칙(I5 경고 0개)의 근거는 ±10% 범위의 10개 IV 이다."]
    (OUT / "단계시험_요약.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


# ---------------------------------------------------------------- 점검
def selftest():
    deck = make_deck("t", {"tox": 1.2})
    assert "{" not in deck and "}" not in deck, "채우지 못한 빈칸"
    assert "set TOX = 0.072" in deck and "set DOSE = 7.7e+12" in deck and "set DIFF_TIME = 30" in deck, "치환 값 불일치"
    assert "structure outfile=t.str" in deck and "mesh infile=t.str" in deck
    assert name_of("tox", 1.2) == "산화막두께_증가20퍼" and tag_of("diff", 0.7) == "diff_m30"
    # 고칠것1 의 기준값 로그로 파서 검증 (Vth 2.25829, Ron 1.899e4 가 재현되어야 함)
    iv = next((ROOT / "고칠것1" / "고칠것1_TCAD 설정" / "TCAD" / "같은값" / "1_기준값_1회").glob("실행기록.log"))
    f = features(parse_iv(iv.read_text(errors="ignore")))
    assert abs(f["vth"] - 2.25829) < 1e-3, f"Vth 파서 불일치 {f}"
    rn = ROOT / "고칠것1" / "BV_온저항" / "runs" / "1_기준값" / "실행기록_온저항.log"
    ron = ron_from(parse_drain(rn.read_text(errors="ignore")))
    assert abs(ron["ron"] / 18989.7 - 1) < 1e-3, f"Ron 파서 불일치 {ron}"
    refs = load_refs()
    assert abs(refs[(None, 1.0)]["vth"] - 2.25829) < 1e-3 and (("tox", 1.1) in refs)
    # 스윕 6 V 변형: deck 의 스윕 줄만 바뀌고, Id(4V)는 스윕 끝이 아니라 4 V 점의 전류여야 함
    d6 = make_deck("t", {"tox": 1.4}, 6.0)
    assert "vfinal=6 name=gate" in d6 and "vfinal=4.0 name=gate" not in d6 and make_deck("t", {"tox": 1.4}).count("vfinal=4.0 name=gate") == 1
    assert name_of("tox", 1.4, 6.0) == "산화막두께_증가40퍼_스윕6V" and tag_of("tox", 1.4, 6.0) == "tox_p40_s6"
    assert [sweep_for("tox", 1.3), sweep_for("tox", 1.4), sweep_for("dose", 1.5), sweep_for("dose", 1.6), sweep_for("epi", 1.7)] == [4.0, 6.0, 4.0, 6.0, 4.0]
    pts6 = [(round(0.1 * n, 1), 5e-6 / (1 + math.exp(-(0.1 * n - 3.0) * 3)) + 1e-15) for n in range(61)]
    assert features(pts6)["id4v"] == dict(pts6)[4.0] != pts6[-1][1]
    # 판정 규칙: 합성 결과로 각 규칙이 걸리는지
    base = refs[(None, 1.0)]
    def curve(center):                                   # 시그모이드 Id-Vg (0~4 V, 0.1 V 간격), 기울기 최대는 center
        return [(round(0.1 * n, 1), 5e-6 / (1 + math.exp(-(0.1 * n - center) * 3)) + 1e-15) for n in range(41)]
    good = {"knob": "tox", "ratio": 1.2, "status": "ok", "points": curve(2.5), "ron_points": [(0.05, 1e-6)],
            "vth": base["vth"] + 0.4, "ron": base["ron"] * 1.3, "id_vd4": 1e-4, "warnings": 0}
    inner = refs[("tox", 1.1)]
    assert judge(good, refs, inner) == ("정상", [])
    assert judge({**good, "points": curve(3.9)}, refs, inner) == ("의심", ["I6"])                 # I6 (추출 유효성)
    assert judge({**good, "points": [(0, -1e-15), (4, 1e-5)]}, refs, inner)[0] == "실패"          # I2
    assert judge({**good, "status": "failed"}, refs, inner) == ("실패", ["I1"])                   # I1
    assert judge({**good, "status": "failed", "infra_error": True}, refs, inner)[0] == "재시도"    # 시작 오류는 경계 아님
    assert judge({**good, "vth": base["vth"] - 0.1}, refs, inner)[0] == "의심"                    # I3 (방향)
    assert "I4" in judge({**good, "vth": inner["vth"] - 0.01}, refs, inner)[1]                   # I4 (단조성)
    assert judge({**good, "warnings": 2}, refs, inner) == ("의심", ["I5"])                        # I5
    print("selftest ok")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "test":
        r = run_one("tox", 1.2)
        print({k: r.get(k) for k in ("status", "seconds", "vth", "gm", "id4v", "ron", "id_vd4", "warnings")})
        report([r])
    elif cmd == "run":
        report(run_all(2))
    elif cmd == "extend":
        run_all(4)
        report(load_results())
    elif cmd == "extend2":                      # ±60, ±70 %. 산화막 +40 % 이상, 바디 도즈 +60 % 이상은 스윕 6 V
        run_all(6)
        report(load_results())
    elif cmd == "report":
        report(load_results())
    else:
        print(__doc__)
