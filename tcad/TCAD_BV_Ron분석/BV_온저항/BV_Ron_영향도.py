"""이미 만든 소자 구조(노브 4개 x 기준/±10%, 9개)에 대해 온저항(Ron)과 진짜 항복전압(BV)을 계산한다.
구조는 다시 만들지 않고, 앞 실험의 소자구조.str 을 읽어서 Atlas 만 돌린다.

  python bv_ron.py selftest       # TCAD 없이 파서와 deck 점검 (몇 초)
  python bv_ron.py run            # 온저항과 높은 Vd 전류 (9개, 구조당 약 5분). 끝난 실행은 건너뜀
  python bv_ron.py truebv [태그]  # 애벌런치를 통과하는 진짜 BV (곡선 추적, 구조당 약 15~25분). 기본은 기준값(base)
  python bv_ron.py reparse [태그] # 저장된 곡선 추적 로그에서 BV 를 다시 계산 (TCAD 재실행 없음)
  python bv_ron.py report         # 저장된 결과로 표와 그림을 만듦 (9개 모두 run 과 truebv 가 끝나 있어야 함)
환경변수: DBASCII, TCAD_WORKERS(기본 3), TCAD_TIMEOUT(초, 기본 5400)
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
RUNS, OUT = HERE / "runs", HERE / "결과"
WORK = HERE.parent / "_work"                      # Silvaco 는 영문 경로에서 실행 (한글 경로 문제 예방)
PREV = HERE.parent / "고칠것1" / "고칠것1_TCAD 설정" / "TCAD"   # 앞 실험의 구조와 결과 (읽기만 함)
DBASCII = os.environ.get("DBASCII", r"C:\sedatools\lib\deckbuild\5.0.10.R\x86_64-windows\dbascii.exe")
SUPPORT = r"C:\sedatools\lib\support\x86_64-windows"
WORKERS = int(os.environ.get("TCAD_WORKERS", "3"))
TIMEOUT = int(os.environ.get("TCAD_TIMEOUT", "5400"))

# 실험: (태그, 한글 폴더 이름, 앞 실험의 그룹 폴더, 앞 실험의 폴더 이름)
EXPS = [
    ("base",   "1_기준값",            "같은값",   "1_기준값_1회"),
    ("dose_m", "2_바디도즈_감소10퍼",   "다른 값", "3_바디도즈_감소10퍼"),
    ("dose_p", "3_바디도즈_증가10퍼",   "다른 값", "4_바디도즈_증가10퍼"),
    ("epi_m",  "4_에피도핑_감소10퍼",   "다른 값", "5_에피도핑_감소10퍼"),
    ("epi_p",  "5_에피도핑_증가10퍼",   "다른 값", "6_에피도핑_증가10퍼"),
    ("diff_m", "6_확산시간_감소10퍼",   "다른 값", "7_확산시간_감소10퍼"),
    ("diff_p", "7_확산시간_증가10퍼",   "다른 값", "8_확산시간_증가10퍼"),
    ("tox_m",  "8_산화막두께_감소10퍼", "다른 값", "9_산화막두께_감소10퍼"),
    ("tox_p",  "9_산화막두께_증가10퍼", "다른 값", "10_산화막두께_증가10퍼"),
]
KO = {t: ko for t, ko, _, _ in EXPS}
KNOB_KO = {"dose": "바디 도즈", "epi": "에피 도핑", "diff": "확산 시간", "tox": "산화막 두께"}

# Atlas 공통 부분 (앞 실험 deck 의 Atlas 부분과 같은 전극·도핑·모델)
COMMON = """go atlas

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
"""
# 온저항: 게이트를 4 V 로 켜 놓고(드레인 0 V) 드레인을 0 -> 0.5 V 로 올린다. Ron = Vd / Id (작은 Vd 에서)
RON_DECK = COMMON + """
solve vgate=0.5 vstep=0.5 vfinal=4.0 name=gate

log outf={tag}_ron.log

solve vdrain=0.05 vstep=0.05 vfinal=0.5 name=drain
solve vdrain=0.5 vstep=0.25 vfinal=4.0 name=drain

quit
"""
# ---------------------------------------------------------------- 콘솔 로그 파싱
def parse_sweep(text, var):
    """콘솔 로그에서 (스윕 전압, 드레인 전류) 점들. var = 'gate' 또는 'drain'. 같은 전압이 반복되면 마지막 값."""
    rx = re.compile(r"V\(\s*%s\s*\)\s*=\s*([\-\d.eE+]+).*?"
                    r"drain\s+[\d.eE+-]+\s+[\d.eE+-]+\s+[\d.eE+-]+\s+[\d.eE+-]+\s+([\-\d.eE+]+)" % var, re.DOTALL)
    d = {round(float(m.group(1)), 4): float(m.group(2)) for m in rx.finditer(text)}
    return sorted(d.items())


def ron_from(points):
    """(Vd, Id) 점들 -> Ron (옴·um) = Vd/Id (Vd=0.05 V, 선형 영역), Id(Vd=0.1 V)."""
    p = {round(v, 3): i for v, i in points}
    if 0.05 not in p or p[0.05] <= 0:
        return {}
    return {"ron": 0.05 / p[0.05], "id_vd01": p.get(0.1), "id_vd05": p.get(0.5), "id_vd4": p.get(4.0)}


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


def src_str(tag):
    _, ko, grp, name = next(e for e in EXPS if e[0] == tag)
    return PREV / grp / name / "소자구조.str"


def run_one(tag):
    """온저항과 높은 Vd 전류를 계산해 결과.json 에 합친다. 이미 결과가 있으면 건너뛰고, 진짜 BV 결과(bvt_*)는 건드리지 않는다."""
    final = RUNS / KO[tag]
    cache = final / "결과.json"
    old = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    if old.get("ron"):
        return old
    d = WORK / tag
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(src_str(tag), d / f"{tag}.str")
    t0 = time.time()
    (d / "ron.in").write_text(RON_DECK.format(tag=tag), encoding="utf-8")
    st = run_deck(d, "ron.in", "ron_console.log")
    pts = parse_sweep((d / "ron_console.log").read_text(errors="ignore"), "drain") if (d / "ron_console.log").exists() else []
    r = {**old, "tag": tag}
    r.update(ron_from(pts), ron_points=pts, ron_status=st)
    r["status"] = "ok" if r.get("ron") else "failed"
    r["seconds"] = round(time.time() - t0, 1)
    final.mkdir(parents=True, exist_ok=True)
    for src, new in (("ron.in", "입력deck_온저항.in"), ("ron_console.log", "실행기록_온저항.log")):
        if (d / src).exists():
            shutil.copy(d / src, final / new)
    cache.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    shutil.rmtree(d, ignore_errors=True)               # 구조 복사본과 Silvaco 임시 파일은 지움 (원본 구조는 앞 실험 폴더에 있음)
    return r


# 진짜 BV: 애벌런치를 통과하도록 곡선 추적(curvetrace)으로 계산한다 (Silvaco 예제 mos2ex07 의 방식).
# 30 V 까지는 전압을 올리고, 그 뒤는 전압 제어 -> 전류 제어로 바꿔 가며 전류를 키워 간다.
TRUEBV_DECK = COMMON + """
solve vdrain=0 vstep=5 vfinal=30 name=drain

method newton trap ir.tol=1e-25 ix.tol=1e-25 clim.dd=1e8
curvetrace contr.name=drain curr.cont step.init=0.5 mincur=2e-13 nextst.ratio=1.5 end.val=1e-5

log outf={tag}_bvtrace.log

solve curvetrace

quit
"""
TRUEBV_LEVELS = (1e-9, 1e-8, 1e-7, 1e-6, 1e-5)      # A/μm. 곡선이 거의 수직이면 기준을 바꿔도 BV 가 거의 안 변한다
_NUM = r"-?\d+\.\d+[eE][+\-]\d+"                    # 바이어스 표의 숫자는 모두 지수 표기다 (접촉 안내표의 "4  0.000 ..." 같은 줄은 제외)
_ROW = re.compile(rf"^\s*drain((?:\s+{_NUM}){{5,6}})\s*$", re.M)


def parse_rows(text):
    """콘솔 로그의 전극 표에서 (드레인 전압, 드레인 전류)를 계산된 순서대로. 마지막 숫자 = 전체 전류.
    숫자 6개짜리 표는 [Va(걸어 준 전압), Vi(소자 안쪽 전압), Jn, Jp, Jc, Jt] 이다. 전류 제어 구간에서는 Atlas 가 드레인에
    큰 직렬 저항을 붙여서 Va 가 수천 V 로 치솟으므로, 소자의 실제 전압인 Vi 를 쓴다. 5개짜리(전압 제어)는 첫 숫자가 전압이다."""
    out = []
    for m in _ROW.findall(text):
        nums = m.split()
        out.append((float(nums[1] if len(nums) == 6 else nums[0]), float(nums[-1])))
    return out


def reparse_truebv(tag):
    """저장된 곡선 추적 로그에서 점과 기준별 BV 를 다시 계산한다 (TCAD 재실행 없음)."""
    final = RUNS / KO[tag]
    p = final / "결과.json"
    r = json.loads(p.read_text(encoding="utf-8"))
    pts = parse_rows((final / "실행기록_진짜항복전압.log").read_text(errors="ignore"))
    r.update(bvt_points=pts, bvt_levels={f"{lv:g}": bv_at(pts, lv) for lv in TRUEBV_LEVELS})
    p.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    return r


def bv_at(points, level):
    """전류가 level 에 처음 닿는 Vd (로그 보간). 닿지 못하면 None."""
    for (v0, i0), (v1, i1) in zip(points, points[1:]):
        if 0 < i0 < level <= i1:
            return v0 + (v1 - v0) * math.log(level / i0) / math.log(i1 / i0)
    return None


def run_truebv(tag):
    final = RUNS / KO[tag]
    p = final / "결과.json"
    r = json.loads(p.read_text(encoding="utf-8"))
    d = WORK / f"{tag}_t"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(src_str(tag), d / f"{tag}.str")
    (d / "bvt.in").write_text(TRUEBV_DECK.format(tag=tag), encoding="utf-8")
    t0 = time.time()
    st = run_deck(d, "bvt.in", "bvt_console.log")
    pts = parse_rows((d / "bvt_console.log").read_text(errors="ignore")) if (d / "bvt_console.log").exists() else []
    r.update(bvt_points=pts, bvt_status=st, bvt_seconds=round(time.time() - t0, 1),
             bvt_levels={f"{lv:g}": bv_at(pts, lv) for lv in TRUEBV_LEVELS})
    p.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    for src, new in (("bvt.in", "입력deck_진짜항복전압.in"), ("bvt_console.log", "실행기록_진짜항복전압.log")):
        if (d / src).exists():
            shutil.copy(d / src, final / new)
    shutil.rmtree(d, ignore_errors=True)
    print(f"{KO[tag]}: 진짜 BV 점 {len(pts)}개, 기준별 BV = {r['bvt_levels']}  ({r['bvt_seconds']:.0f}초)", flush=True)
    return r


def run_all():
    t0 = time.time()
    with ThreadPoolExecutor(WORKERS) as ex:
        res = []
        for fu in [ex.submit(run_one, t) for t, *_ in EXPS]:
            r = fu.result()
            res.append(r)
            print(f"{KO[r['tag']]:24s} {r['status']:7s} {r['seconds']:7.1f}s  Ron={r.get('ron')}", flush=True)
    print(f"전체 {time.time() - t0:.0f}초")
    return res


# ---------------------------------------------------------------- 표와 그림
def load_prev(tag):
    _, _, grp, name = next(e for e in EXPS if e[0] == tag)
    return json.loads((PREV / grp / name / "결과.json").read_text(encoding="utf-8"))


def load_results():
    out = []
    for t, *_ in EXPS:
        p = RUNS / KO[t] / "결과.json"
        if p.exists():
            out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def pct(a, b):
    return 100 * (a - b) / b


VGS_TEST, VGS_MAX_ASSUMED = 4.0, 20.0     # 실험 게이트 전압, 게이트 최대 전압 가정(데이터시트로 확인 필요)


def ox_field(tox_um, vg):
    """산화막 평균 전계 (MV/cm) ~ 게이트 전압 / 산화막 두께. 신뢰성 참고용 지표이며 TCAD 계산이 아님."""
    return vg / (tox_um * 100)


LEVELS_SHOW = ("1e-09", "1e-08", "1e-07", "1e-06")      # BV 판정 전류 기준(A/μm). 곡선이 거의 수직이라 기준을 바꿔도 BV 가 거의 안 변한다
THRESH = {"dvth": 50.0, "dgm": 5.0, "did": 5.0, "dron": 5.0, "dsat": 5.0, "dbv": 1.0}     # 영향 있음의 기준 (mV, %, %, %, %, V)
IND_KO = {"dvth": "Vth", "dgm": "gm", "did": "Id(4V)", "dron": "Ron", "dsat": "Id(Vd=4V)", "dbv": "BV"}


def true_bv(r, level="1e-09"):
    return (r.get("bvt_levels") or {}).get(level)


def write_outputs(results):
    OUT.mkdir(exist_ok=True)
    by = {r["tag"]: r for r in results if r["status"] == "ok"}
    base, pbase = by["base"], load_prev("base")
    bv0 = true_bv(base)
    rows = []
    for k in KNOB_KO:
        for lab, s in (("-10%", "m"), ("+10%", "p")):
            r = by.get(f"{k}_{s}")
            if not r:
                continue
            p = load_prev(f"{k}_{s}")
            bv = true_bv(r)
            rows.append({"knob": k, "dir": lab, "dvth": 1000 * (p["vth"] - pbase["vth"]), "dgm": pct(p["gm"], pbase["gm"]),
                         "did": pct(p["id4v"], pbase["id4v"]), "dron": pct(r["ron"], base["ron"]),
                         "dsat": pct(r["id_vd4"], base["id_vd4"]) if r.get("id_vd4") and base.get("id_vd4") else None,
                         "bv": bv, "dbv": (bv - bv0) if bv and bv0 else None, "dbv_pct": pct(bv, bv0) if bv and bv0 else None})
    with open(OUT / "BV_온저항_결과표.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["실험", "상태", "온저항 Ron(Ω·μm)", "Id(Vd=0.1V,Vg=4V)(A/μm)", "Id(Vd=4V,Vg=4V)(A/μm)", "BV(V) 판정기준 1e-9 A/μm",
                    "BV(V) 1e-8", "BV(V) 1e-7", "BV(V) 1e-6", "BV(V) 1e-5", "산화막 두께(nm)", "산화막 전계 Vg=4V(MV/cm)",
                    f"산화막 전계 Vg={VGS_MAX_ASSUMED:g}V 가정(MV/cm)"])
        for r in results:
            tox = load_prev(r["tag"])["values"]["tox"]
            lv = r.get("bvt_levels") or {}
            w.writerow([KO[r["tag"]], r["status"], r.get("ron"), r.get("id_vd01"), r.get("id_vd4"), lv.get("1e-09"), lv.get("1e-08"),
                        lv.get("1e-07"), lv.get("1e-06"), lv.get("1e-05"), tox * 1000,
                        round(ox_field(tox, VGS_TEST), 3), round(ox_field(tox, VGS_MAX_ASSUMED), 3)])
    with open(OUT / "곡선_원자료_BV_온저항.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["실험", "종류", "전압(V)", "드레인전류(A/μm)"])
        for r in results:
            for kind, key in (("온저항(Vg=4V)", "ron_points"), ("항복전압(Vg=0V, 소자 안쪽 전압)", "bvt_points")):
                w.writerows([(KO[r["tag"]], kind, v, i) for v, i in r.get(key, [])])
    f = lambda x, fmt: "-" if x is None else format(x, fmt)
    lo = min(true_bv(base, l) for l in LEVELS_SHOW)
    hi = max(true_bv(base, l) for l in LEVELS_SHOW)
    L = ["# 노브 지문표: BV(진짜)와 온저항까지 포함", "",
         f"- 기준값: **BV = {f(bv0, '.2f')} V**, Ron = {base['ron']:.4g} Ω·μm (Vg = 4 V, Vd = 0.05 V), Vth = {pbase['vth']:.4f} V (앞 실험 값)",
         "- **BV 정의**: 게이트 0 V(꺼짐)에서 드레인 전압을 올리며, 곡선 추적(curvetrace)으로 **애벌런치를 통과**시켜 "
         "드레인 전류가 1e-9 A/μm 에 닿는 소자 안쪽 전압(Vi). 판정 전류를 1e-9 ~ 1e-6 으로 바꿔도 기준값의 BV 는 "
         f"{lo:.2f} ~ {hi:.2f} V 로 거의 같다.",
         "- 영향 있음의 기준(**가정**): Vth 50 mV, gm·전류·온저항 5 %, BV 1 V 이상 (노브 ±10 % 기준).", "",
         "## 노브를 10 % 바꿨을 때 기준 대비 변화", "",
         "| 노브 | 방향 | ΔVth (mV) | Δgm (%) | ΔId(4V) (%) | ΔRon (%) | ΔId(Vd=4V) (%) | BV (V) | ΔBV (V) | ΔBV (%) |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {KNOB_KO[r['knob']]} | {r['dir']} | {r['dvth']:+.1f} | {r['dgm']:+.2f} | {r['did']:+.2f} | {r['dron']:+.2f} | "
                 f"{f(r['dsat'], '+.2f')} | {f(r['bv'], '.2f')} | {f(r['dbv'], '+.2f')} | {f(r['dbv_pct'], '+.2f')} |")
    L += ["", "## 노브가 어디에 영향을 주는가 (O = 기준 이상, X = 기준 미만, 괄호 = ±10 % 중 큰 쪽의 변화)", "",
          "| 노브 | " + " | ".join(IND_KO.values()) + " |", "|---|" + "---|" * len(IND_KO)]
    for k in KNOB_KO:
        cells = []
        for key in IND_KO:
            vals = [abs(r[key]) for r in rows if r["knob"] == k and r[key] is not None]
            if not vals:
                cells.append("-")
                continue
            v = max(vals)
            unit = {"dvth": " mV", "dbv": " V"}.get(key, " %")
            cells.append(f"{'O' if v >= THRESH[key] else 'X'} ({v:.1f}{unit})")
        L.append(f"| {KNOB_KO[k]} | " + " | ".join(cells) + " |")
    L += ["", "## 산화막 전계 지표 (신뢰성 참고용, TCAD 계산이 아님)", "",
          "전계 ≈ 게이트 전압 ÷ 산화막 두께. 절연 파괴와 게이트 누설은 계산에 반영되지 않아서, 산화막이 얇아질 때의 위험을 이 숫자로 가늠한다. "
          "다른 노브는 산화막 두께를 바꾸지 않으므로 기준과 같다.", "",
          f"| 산화막 | 두께 (nm) | 전계, Vg = {VGS_TEST:g} V (MV/cm) | 전계, Vg = {VGS_MAX_ASSUMED:g} V 가정 (MV/cm) |", "|---|---|---|---|"]
    for lab, tag in (("-10%", "tox_m"), ("기준", "base"), ("+10%", "tox_p")):
        if tag in by:
            tox = load_prev(tag)["values"]["tox"]
            L.append(f"| {lab} | {tox * 1000:.0f} | {ox_field(tox, VGS_TEST):.2f} | {ox_field(tox, VGS_MAX_ASSUMED):.2f} |")
    L += ["", "## 한계", "",
          "- **기준 구조는 BV 가 40 V 대가 되도록 에피층을 설계했으므로, 기준 BV 약 41 V 는 설계 확인일 뿐 실제 소자와의 일치를 뜻하지 않는다. "
          "본 연구에서 사용하는 것은 노브 변동에 따른 BV 의 상대 변화이다.**",
          "- 모두 TCAD 계산 결과이고, 노브 하나씩 ±10 % 한 가지 크기만 본 결과다. 여러 노브가 동시에 틀어지는 경우는 보지 않았다.",
          f"- 게이트 최대 전압 {VGS_MAX_ASSUMED:g} V 는 **가정**이고(데이터시트로 확인 필요), 산화막 전계는 평균값이라 트렌치 모서리의 집중은 반영되지 않았다. 위험 전계의 기준값은 문헌으로 확인한 뒤 채운다.",
          "- 영향 있음의 기준값(50 mV, 5 %, 1 V)은 가정이다. 온저항 ±4 % 와 Id(Vd=4V) ±5.4 % 처럼 기준 근처의 값은 기준을 조금만 바꿔도 판정이 뒤집힌다.",
          "", "그림: `그림4_항복전압_곡선.png`, `그림5_노브별_BV_온저항_변화량.png`, `그림6_지문표_히트맵.png`. "
          "원자료: `BV_온저항_결과표.csv`, `곡선_원자료_BV_온저항.csv`."]
    (OUT / "지문표.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    figs(by, rows)


def _plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    return plt


def figs(by, rows):
    plt = _plt()
    from matplotlib.ticker import FuncFormatter
    # 그림 4: 진짜 BV 곡선 (곡선 추적으로 애벌런치를 통과한 곡선, 가로축은 소자 안쪽 전압)
    fig, axs = plt.subplots(2, 2, figsize=(10, 7), sharex=True, sharey=True)
    for ax, k in zip(axs.flat, KNOB_KO):
        for tag, col, lab in ((f"{k}_m", "tab:blue", "-10%"), ("base", "k", "기준"), (f"{k}_p", "tab:red", "+10%")):
            pts = [(v, i) for v, i in by[tag].get("bvt_points", []) if i > 0 and v >= 30]
            if pts:
                ax.semilogy(*zip(*pts), color=col, label=lab, lw=1.6)
        ax.axhline(1e-9, color="gray", ls=":", lw=1)
        ax.set_title(KNOB_KO[k]); ax.grid(alpha=.3); ax.legend(loc="upper left")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"1e{round(math.log10(v))}"))
    for ax in axs[1]:
        ax.set_xlabel("드레인 전압 Vd (V, 소자 안쪽)")
    for ax in axs[:, 0]:
        ax.set_ylabel("드레인 전류 Id (A/μm)")
    fig.suptitle("꺼진 상태(Vg = 0 V)에서 항복을 통과하는 곡선 (점선 = BV 판정 기준 1e-9 A/μm)")
    fig.tight_layout(); fig.savefig(OUT / "그림4_항복전압_곡선.png", dpi=150)
    # 그림 5: BV 와 Ron 변화량
    fig, axs = plt.subplots(1, 2, figsize=(10, 4))
    for ax, key, title in zip(axs, ("dbv", "dron"), ("ΔBV (V)", "ΔRon (%)")):
        for j, (lab, col) in enumerate((("-10%", "tab:blue"), ("+10%", "tab:red"))):
            vals = [next((r[key] for r in rows if r["knob"] == k and r["dir"] == lab and r[key] is not None), 0) for k in KNOB_KO]
            ax.bar([x + (j - .5) * .38 for x in range(4)], vals, .38, color=col, label=f"노브 {lab}")
        ax.set_xticks(range(4)); ax.set_xticklabels(list(KNOB_KO.values()))
        ax.axhline(0, color="k", lw=.8); ax.set_title(title); ax.grid(alpha=.3, axis="y")
    axs[0].legend(); fig.suptitle("노브 하나씩 ±10% 바꿨을 때 BV 와 온저항의 변화")
    fig.tight_layout(); fig.savefig(OUT / "그림5_노브별_BV_온저항_변화량.png", dpi=150)
    # 그림 6: 지문표 히트맵 (노브 +10% 일 때 기준 대비 % 변화)
    import numpy as np
    cols = [("dvth", "Vth (mV→%)"), ("dgm", "gm (%)"), ("did", "Id 4V (%)"), ("dron", "Ron (%)"), ("dsat", "Id Vd=4V (%)"), ("dbv_pct", "BV (%)")]
    pbase = load_prev("base")
    nan = lambda x: np.nan if x is None else x
    M = []
    for k in KNOB_KO:
        r = next(x for x in rows if x["knob"] == k and x["dir"] == "+10%")
        M.append([r["dvth"] / 1000 / pbase["vth"] * 100, r["dgm"], r["did"], r["dron"], nan(r["dsat"]), nan(r["dbv_pct"])])
    M = np.array(M)
    fig, ax = plt.subplots(figsize=(9, 4))
    lim = np.nanmax(np.abs(M))
    im = ax.imshow(M, cmap="RdBu_r", vmin=-lim, vmax=lim, aspect="auto")
    ax.set_xticks(range(len(cols))); ax.set_xticklabels([c[1] for c in cols]); ax.set_yticks(range(4)); ax.set_yticklabels(list(KNOB_KO.values()))
    for i in range(4):
        for j in range(len(cols)):
            ax.text(j, i, "-" if np.isnan(M[i, j]) else f"{M[i, j]:+.1f}", ha="center", va="center", fontsize=11)
    fig.colorbar(im, label="노브 +10% 일 때 기준 대비 변화 (%)")
    ax.set_title("노브별 지문표 (빨강 = 증가, 파랑 = 감소)")
    fig.tight_layout(); fig.savefig(OUT / "그림6_지문표_히트맵.png", dpi=150)


def selftest():
    # 파서: 앞 실험의 실제 콘솔 로그에서 40개 점과 마지막 전류(Id 4V = 5.207e-6)를 읽어야 함
    t = (PREV / "같은값" / "1_기준값_1회" / "실행기록.log").read_text(errors="ignore")
    pts = parse_sweep(t, "gate")
    assert len(pts) == 40 and abs(pts[-1][1] - 5.207e-6) < 1e-9, f"게이트 스윕 파싱 실패: {len(pts)}개"
    assert "{" not in RON_DECK.format(tag="x") and "}" not in RON_DECK.format(tag="x")
    assert ron_from([(0.05, 1e-6), (0.1, 2e-6)])["ron"] == 0.05 / 1e-6
    assert abs(ox_field(0.06, 4) - 0.6667) < 1e-3 and abs(ox_field(0.054, 20) - 3.7037) < 1e-3, "산화막 전계 계산 오류"
    log = (RUNS / KO["base"] / "실행기록_진짜항복전압.log").read_text(errors="ignore")
    rows = parse_rows(log)                                     # 곡선 추적 로그에서 항복을 통과한 곡선이 읽히는지
    assert len(rows) >= 30 and max(i for _, i in rows) > 1e-6 and 40 < bv_at(rows, 1e-9) < 42, "곡선 추적 파싱 실패"
    assert (4.0, 0.0) not in rows, "접촉 안내표가 바이어스 점으로 읽힘"
    assert abs(bv_at([(40, 1e-13), (41, 1e-11), (41.2, 1e-7)], 1e-9) - 41.1) < 1e-9 and bv_at([(40, 1e-13)], 1e-9) is None
    assert "{" not in TRUEBV_DECK.format(tag="x") and "curvetrace" in TRUEBV_DECK
    for t_, *_ in EXPS:
        assert src_str(t_).exists(), f"구조 파일 없음: {src_str(t_)}"
    print("selftest ok")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "selftest":
        selftest()
    elif cmd == "run":
        run_all()
    elif cmd == "report":
        write_outputs(load_results())
    elif cmd == "reparse":                      # 저장된 곡선 추적 로그에서 점과 BV 를 다시 계산
        for t in (sys.argv[2:] or ["base"]):
            print(KO[t], reparse_truebv(t)["bvt_levels"])
    elif cmd == "truebv":                       # python bv_ron.py truebv [태그 ...]   (기본: base)
        tags = sys.argv[2:] or ["base"]
        # 동시에 시작하면 Atlas 가 구조를 못 읽는 경우가 있어서 시작 시각을 25초씩 어긋나게 한다
        with ThreadPoolExecutor(WORKERS) as ex:
            list(ex.map(lambda a: (time.sleep(a[0] % WORKERS * 25), run_truebv(a[1]))[1], enumerate(tags)))
    else:
        print(__doc__)
