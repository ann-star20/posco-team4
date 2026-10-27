"""대량 TCAD 실행: 샘플링 계획표(TCAD_배치실행/샘플링계획/결과/샘플링계획_N{N}.csv)를 읽어 샘플마다 IV(보통 격자)를 계산하고,
계획표에서 BV 계산이 Y 인 샘플은 같은 구조로 BV(곡선 추적)까지 계산한다. 실패는 지우지 않고 상태로 기록한다.
기존 코드(단계시험.py, 조합시험.py)는 가져다 쓰기만 하고 기존 폴더에는 아무것도 쓰지 않는다. 온저항 단계는 돌리지 않는다.

재시도 규칙(결과를 보기 전에 정해 둔 것):
  - 계산이 실패하면(Vth 를 못 구함) 격자를 x0.97 로 바꿔 1회 다시 계산한다 (산화막 +50 % 에서 격자 x0.8 이 실패한 사례 때문).
  - 성공했지만 Vth 추출이 스윕 끝에 막혔으면(규칙 I6) 게이트 스윕을 6 V 로 올려 1회 다시 계산한다.
  - 두 재시도 모두 시도 내역을 결과에 남긴다. 그래도 실패하면 상태 failed 로 남기고 학습에서 뺀다.
  - Vg=0 누설이 1e-10 A/μm 이상이면(규칙 B4) 소자가 꺼지지 않은 것이라 BV 를 계산하지 않는다.

  python 대량실행.py selftest         # TCAD 없이 계획 읽기, deck, 규칙 점검 (몇 초)
  python 대량실행.py status [N]       # 진행 상황 (기본 N = 120)
  python 대량실행.py run [N]          # 계획표 순서대로 실행. 끝난 샘플은 건너뛰므로 끊겨도 같은 명령으로 이어서 실행
  python 대량실행.py collect [N]      # 저장된 결과로 표(csv)와 요약(md)만 다시 만듦
  python 대량실행.py redo [N]         # 실패로 기록된 샘플만 지우고 다시 계산 (실패는 기본적으로 다시 안 돌리므로, 환경 문제였을 때 쓴다)
환경변수: DBASCII, TCAD_WORKERS(기본 3), TCAD_TIMEOUT(초, 기본 3600). BV 가 오래 걸리면 TCAD_TIMEOUT=5400.
"""
import csv
import importlib.util
import json
import re
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = next(p for p in (HERE, *HERE.parents) if (p / "최종_trench_template.in").exists())


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


st = _load(ROOT / "TCAD_단계실행" / "단계시험" / "단계시험.py", "stage_test")           # deck 만들기, IV 파서, 실행
cb = _load(ROOT / "TCAD_BV판정" / "조합시험" / "조합시험.py", "combo_test")         # BV 실행(run_bv), B1·B3 판정
PLAN_DIR = ROOT / "TCAD_배치실행" / "샘플링계획" / "결과"
RUNS, OUT = HERE / "runs", HERE / "결과"
WORK = ROOT / "_work"
LEAK_MAX = 1e-10                                                # 규칙 B4
RETRY_MESH = 0.97
MESH_RE = re.compile(r"(?m)^(line\s+[xy]\s+loc=\S+\s+spac=)(\S+)")
BASE_VTH, BASE_BV = 2.25829, 41.117                             # 기준값(번호 1)이 재현해야 하는 이전 결과


def scale_mesh(deck, f):
    return MESH_RE.sub(lambda m: f"{m.group(1)}{float(m.group(2)) * f:.6g}", deck)


def _rd(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def load_plan(n):
    return list(csv.DictReader(open(PLAN_DIR / f"샘플링계획_N{n}.csv", encoding="utf-8-sig")))


def ratios_of(row):
    return {"dose": float(row["바디도즈비율"]), "epi": float(row["에피도핑비율"]), "tox": float(row["산화막비율"])}


# ---------------------------------------------------------------- 규칙
def checks(r):
    """IV 규칙: I1 계산 성공, I2 모든 전류 > 0, I5 수렴 경고 0개, I6 Vth 추출이 유효(최대 기울기 점 뒤에 점이 5개 이상)."""
    pts = r.get("points") or []
    sl = [((b - a) / (v1 - v0), k) for k, ((v0, a), (v1, b)) in enumerate(zip(pts, pts[1:]), 1) if v1 > v0]
    return {"I1": r.get("status") == "ok", "I2": bool(pts) and all(i > 0 for _, i in pts), "I5": r.get("warnings", 1) == 0,
            "I6": bool(sl) and len(pts) - 1 - max(sl)[1] >= 5}


def b4_ok(r):
    return r.get("i_leak") is not None and r["i_leak"] < LEAK_MAX


# ---------------------------------------------------------------- 실행
def run_iv(ratios, sweep, mesh_f, tag):
    d = WORK / tag
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
    deck = st.make_deck(tag, ratios, sweep)
    if mesh_f != 1.0:
        deck = scale_mesh(deck, mesh_f)
    (d / "deck.in").write_text(deck, encoding="utf-8")
    t0 = time.time()
    status = st.run_deck_retry(d, "deck.in", "console.log")
    text = (d / "console.log").read_text(errors="ignore") if (d / "console.log").exists() else ""
    pts = st.parse_iv(text)
    f = st.features(pts)
    r = {"iv_status": status, "points": pts, "warnings": len(st.WARN_RE.findall(text)), **f, "sweep": sweep, "mesh": mesh_f,
         "status": "ok" if f and (d / f"{tag}.str").exists() else "failed", "seconds": round(time.time() - t0, 1)}
    return d, r


def process(row):
    no = int(row["번호"])
    final = RUNS / f"{no:03d}"
    cache = final / "결과.json"
    tag = f"b{no:03d}"
    r = _rd(cache) or {}
    if r.get("status") not in ("ok", "failed"):
        queue, attempts = [(float(row["스윕(V)"]), 1.0)], []
        while queue:
            sw, mf = queue.pop(0)
            d, res = run_iv(ratios_of(row), sw, mf, tag)
            ck = checks(res)
            attempts.append({"스윕": sw, "격자": mf, "상태": res["status"], "I6": ck["I6"]})
            r = res
            if len(attempts) < 3:
                if res["status"] != "ok" and mf == 1.0:
                    queue.append((sw, RETRY_MESH))
                elif res["status"] == "ok" and not ck["I6"] and sw == 4.0:
                    queue.append((6.0, mf))
            if queue:
                shutil.rmtree(d, ignore_errors=True)                    # 다음 시도가 있으면 이번 시도 파일은 버린다 (마지막 시도만 보관)
        final.mkdir(parents=True, exist_ok=True)
        for src, new in (("deck.in", "입력deck.in"), ("console.log", "실행기록.log"), (f"{tag}.str", "소자구조.str")):
            if (d / src).exists():
                shutil.move(str(d / src), str(final / new))
        shutil.rmtree(d, ignore_errors=True)
        r.update(번호=no, 층=row["층"], 확장축=row["확장축"], ratios=ratios_of(row), 시도=attempts)
        cache.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    if row["BV계산"] == "Y" and r["status"] == "ok" and "bvt_levels" not in r and "bv_skipped" not in r:
        if b4_ok(r):
            r.update(cb.run_bv(final, tag))
        else:
            r["bv_skipped"] = "B4 불통과(Vg=0 누설 큼)"
        cache.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    lv = r.get("bvt_levels") or {}
    print(f"{no:3d} {row['층']}/{row['확장축']:6s} IV {r['status']:6s} Vth={r.get('vth')} BV={lv.get('1e-09', r.get('bv_skipped', '-'))} 시도 {len(r.get('시도', []))}회", flush=True)
    return r


def run_all(n):
    t0 = time.time()
    plan = load_plan(n)

    def safe(row):
        try:
            return process(row)
        except Exception as e:                                          # 한 샘플의 오류가 전체를 멈추지 않게 한다. 기록만 남기고 다음으로
            print(f"{row['번호']:>3s} 오류: {e}", flush=True)
            (RUNS / f"{int(row['번호']):03d}").mkdir(parents=True, exist_ok=True)
            (RUNS / f"{int(row['번호']):03d}" / "오류.txt").write_text(str(e), encoding="utf-8")
    with ThreadPoolExecutor(st.WORKERS) as ex:
        list(ex.map(safe, plan))
    print(f"전체 {time.time() - t0:.0f}초")
    collect(n)


# ---------------------------------------------------------------- 정리
def status_rows(n):
    plan = load_plan(n)
    res = {int(r["번호"]): _rd(RUNS / f"{int(r['번호']):03d}" / "결과.json") for r in plan}
    return plan, res


def collect(n):
    OUT.mkdir(exist_ok=True)
    plan, res = status_rows(n)
    cols = ["번호", "층", "확장축", "바디도즈비율", "에피도핑비율", "산화막비율", "상태", "시도횟수", "스윕V", "격자", "Vth", "gm", "Id4V", "누설", "BV_1e-9", "BV_1e-6",
            "I1", "I2", "I5", "I6", "B1", "B3", "B4", "IV초", "BV초", "BV건너뜀"]
    rows, cnt = [], {"ok": 0, "failed": 0, "대기": 0, "BV끝": 0, "BV대상": 0, "재시도": 0}
    for p in plan:
        r = res[int(p["번호"])]
        if r is None:
            cnt["대기"] += 1
            continue
        ck, lv = checks(r), r.get("bvt_levels") or {}
        b1, b3 = cb.check_bv_rules(r) if lv else (None, None)
        cnt[r["status"]] = cnt.get(r["status"], 0) + 1
        cnt["BV끝"] += bool(lv)
        cnt["재시도"] += len(r.get("시도", [])) > 1
        rows.append([p["번호"], p["층"], p["확장축"], p["바디도즈비율"], p["에피도핑비율"], p["산화막비율"], r["status"], len(r.get("시도", [])), r.get("sweep"), r.get("mesh"),
                     r.get("vth"), r.get("gm"), r.get("id4v"), r.get("i_leak"), lv.get("1e-09"), lv.get("1e-06"),
                     ck["I1"], ck["I2"], ck["I5"], ck["I6"], b1, b3, b4_ok(r) if r["status"] == "ok" else None, r.get("seconds"), r.get("bvt_seconds"), r.get("bv_skipped", "")])
    cnt["BV대상"] = sum(p["BV계산"] == "Y" for p in plan)
    with open(OUT / f"대량실행_결과_N{n}.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(cols)
        w.writerows(rows)
    L = [f"# 대량 실행 결과 (N = {n})", "",
         f"- 완료 {cnt['ok'] + cnt['failed']}/{len(plan)} (성공 {cnt['ok']}, 실패 {cnt['failed']}), 대기 {cnt['대기']}. BV {cnt['BV끝']}/{cnt['BV대상']}. 재시도한 샘플 {cnt['재시도']}개."]
    base = res.get(1)
    if base and base["status"] == "ok":
        bv = (base.get("bvt_levels") or {}).get("1e-09")
        L.append(f"- 기준값 재현(번호 1): Vth {base['vth']:.5f} V (이전 {BASE_VTH}, 차이 {abs(base['vth'] - BASE_VTH) * 1000:.2f} mV)" +
                 (f", BV {bv:.3f} V (이전 {BASE_BV})" if bv else ""))
    bad = [(int(p["번호"]), res[int(p["번호"])]) for p in plan if res[int(p["번호"])] and res[int(p["번호"])]["status"] == "failed"]
    if bad:
        L += ["", "## 실패한 샘플 (학습에서 제외)", "", "| 번호 | 층/확장축 | 비율(도즈, 에피, 산화막) | 시도 |", "|---|---|---|---|"]
        for no, r in bad:
            x = r["ratios"]
            L.append(f"| {no} | {r['층']}/{r['확장축']} | {x['dose']:.3f}, {x['epi']:.3f}, {x['tox']:.3f} | {', '.join(f'{a['스윕']:g}V ×{a['격자']:g} {a['상태']}' for a in r['시도'])} |")
    weak = [(int(p["번호"]), res[int(p["번호"])]) for p in plan if res[int(p["번호"])] and res[int(p["번호"])]["status"] == "ok" and not all(checks(res[int(p["번호"])]).values())]
    if weak:
        L += ["", "## 규칙 I2·I5·I6 위반 (값은 있으나 의심, 확인 필요)", "", "- 번호: " + ", ".join(f"{no}({','.join(k for k, v in checks(r).items() if not v)})" for no, r in weak)]
    skipped = [no for no, r in ((int(p['번호']), res[int(p['번호'])]) for p in plan) if r and r.get("bv_skipped")]
    if skipped:
        L += ["", f"- BV 를 건너뛴 샘플(B4 불통과): {skipped}"]
    (OUT / f"대량실행_요약_N{n}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))


def status(n):
    plan, res = status_rows(n)
    done = [int(p["번호"]) for p in plan if res[int(p["번호"])] and res[int(p["번호"])]["status"] in ("ok", "failed")]
    bv_done = sum(bool((res[int(p["번호"])] or {}).get("bvt_levels") or (res[int(p["번호"])] or {}).get("bv_skipped")) for p in plan if p["BV계산"] == "Y")
    bv_tot = sum(p["BV계산"] == "Y" for p in plan)
    failed = [int(p["번호"]) for p in plan if (res[int(p["번호"])] or {}).get("status") == "failed"]
    print(f"IV 완료 {len(done)}/{len(plan)}, BV 완료 {bv_done}/{bv_tot}, 실패 {len(failed)}개 {failed}")
    ivs = [r["seconds"] for r in res.values() if r and r.get("seconds")]
    bvs = [r["bvt_seconds"] for r in res.values() if r and r.get("bvt_seconds")]
    if ivs:
        left = (len(plan) - len(done)) * (sum(ivs) / len(ivs)) + (bv_tot - bv_done) * (sum(bvs) / len(bvs) if bvs else 1500)
        print(f"남은 시간 추정(병렬 {st.WORKERS}개, 지금까지 평균 기준): 약 {left / st.WORKERS / 3600:.1f}시간")


# ---------------------------------------------------------------- 점검
def selftest():
    plan = load_plan(120)
    assert len(plan) == 120 and plan[0]["확장축"] == "기준값" and [int(r["번호"]) for r in plan] == list(range(1, 121))
    d1 = st.make_deck("b001", ratios_of(plan[0]), float(plan[0]["스윕(V)"]))
    assert "{" not in d1 and "set DOSE = 7.7e+12" in d1 and "set TOX = 0.06" in d1 and "structure outfile=b001.str" in d1 and "vfinal=4.0 name=gate" in d1
    six = next(r for r in plan if r["스윕(V)"] == "6")
    d6 = st.make_deck("b999", ratios_of(six), 6.0)
    assert "vfinal=6 name=gate" in d6 and "vfinal=4.0 name=gate" not in d6
    assert "line x loc=0.0 spac=0.0194" in scale_mesh(d1, RETRY_MESH) and "set TOX = 0.06" in scale_mesh(d1, RETRY_MESH)      # 격자만 바뀐다
    import math
    def curve(center, n=41):                                                                                          # 시그모이드 Id-Vg
        return [(round(0.1 * k, 1), 5e-6 / (1 + math.exp(-(0.1 * k - center) * 3)) + 1e-15) for k in range(n)]
    ok = {"status": "ok", "points": curve(2.5), "warnings": 0}
    assert all(checks(ok).values())
    assert not checks({**ok, "points": curve(3.9)})["I6"]                                                             # 추출이 스윕 끝에 막힘
    assert not checks({**ok, "warnings": 2})["I5"] and not checks({**ok, "points": [(0, -1e-15), (4, 1e-5)]})["I2"]
    assert not checks({"status": "failed", "points": [(k / 10, 5e-16) for k in range(60)], "warnings": 0})["I1"]          # 산화막 +50 % 촘촘한 격자 같은 평평한 곡선
    assert b4_ok({"i_leak": 6e-16}) and not b4_ok({"i_leak": 9e-8}) and not b4_ok({})
    f = st.features([(k / 10, 5e-16) for k in range(60)])
    assert f == {}                                                                                                    # 평평한 곡선은 Vth 를 못 구해 실패로 처리됨
    # 계획표 규칙: BV 대상은 확장 전부 + 기준값 + 바디 도즈 -20 % 이하
    assert all(r["BV계산"] == "Y" for r in plan if r["층"] == "확장" or r["확장축"] == "기준값")
    assert sum(r["BV계산"] == "Y" for r in plan) == 41
    print("selftest ok")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    if cmd == "selftest":
        selftest()
    elif cmd == "status":
        status(n)
    elif cmd == "run":
        run_all(n)
    elif cmd == "collect":
        collect(n)
    elif cmd == "redo":                                              # 실패로 기록된 샘플의 결과를 지우고 다시 계산 (메모리·디스크 부족 같은 환경 문제로 실패한 경우)
        plan, res = status_rows(n)
        todo = [int(p["번호"]) for p in plan if (res[int(p["번호"])] or {}).get("status") == "failed"]
        print("다시 계산할 샘플:", todo)
        for no in todo:
            for name in ("결과.json", "오류.txt"):
                (RUNS / f"{no:03d}" / name).unlink(missing_ok=True)
        run_all(n)
    else:
        print(__doc__)
