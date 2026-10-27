"""최종 학습데이터 만들기: 대량 실행 결과(N행) + 이미 가진 단일 노브 시험 점을 한 표로 합친다. TCAD 는 돌리지 않는다.
  대량 실행: 샘플링 계획표대로 돌린 코어+확장 샘플 (대량작업2/대량실행/결과/대량실행_결과_N{N}.csv)
  단일 노브: 노브 하나만 기준값에서 ±10~70 % 바꾼 시험 점 (고칠것1 ±10 %, 고칠것2 단계시험, BV 는 고칠것1·조합시험·안전범위시험). 기준값 1개는 대량 실행 1번과 같아서 뺀다.
열 이름은 대량 실행 결과표와 같고, 앞에 `출처`, `ID`, 뒤에 `영역안`, `외삽시험용`이 붙는다.

  python 학습데이터_만들기.py selftest        # 점검 (몇 초)
  python 학습데이터_만들기.py N [최종]        # 예: python 학습데이터_만들기.py 146 최종 -> 결과/학습데이터_N146.csv 와 (최종이면) 결과/학습데이터_최종.csv, 학습데이터_설명.md
"""
import csv
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = next(p for p in (HERE, *HERE.parents) if (p / "최종_trench_template.in").exists())
OUT = HERE / "결과"
COLS = ["출처", "ID", "층", "확장축", "바디도즈비율", "에피도핑비율", "산화막비율", "상태", "시도횟수", "스윕V", "격자", "Vth", "gm", "Id4V", "누설", "BV_1e-9", "BV_1e-6",
        "I1", "I2", "I5", "I6", "B1", "B3", "B4", "영역안", "외삽시험용"]
KN = ("dose", "epi", "tox")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ss = _load(ROOT / "대량작업2" / "안전범위시험" / "안전범위시험.py", "safe_range")          # 단일 노브 결과 읽기, BV 규칙
sp = _load(ROOT / "대량작업2" / "샘플링계획" / "샘플링계획.py", "sampling_plan")           # in_domain
bk = _load(ROOT / "대량작업2" / "대량실행" / "대량실행.py", "bulk_run")                    # IV 규칙 checks()


def batch_rows(n):
    rows = list(csv.DictReader(open(ROOT / "대량작업2" / "대량실행" / "결과" / f"대량실행_결과_N{n}.csv", encoding="utf-8-sig")))
    out = []
    for r in rows:
        x = [float(r["바디도즈비율"]), float(r["에피도핑비율"]), float(r["산화막비율"])]
        out.append({"출처": "대량실행", "ID": f"B{int(r['번호']):03d}", "층": r["층"], "확장축": r["확장축"], "바디도즈비율": x[0], "에피도핑비율": x[1], "산화막비율": x[2],
                    "상태": r["상태"], "시도횟수": r["시도횟수"], "스윕V": r["스윕V"], "격자": r["격자"], "Vth": r["Vth"], "gm": r["gm"], "Id4V": r["Id4V"], "누설": r["누설"],
                    "BV_1e-9": r["BV_1e-9"], "BV_1e-6": r["BV_1e-6"], **{k: r[k] for k in ("I1", "I2", "I5", "I6", "B1", "B3", "B4")},
                    "영역안": bool(sp.in_domain(*x)), "외삽시험용": ""})
    return out


def single_rows():
    prior = {}
    for row in csv.DictReader(open(ss.st.PREV1, encoding="utf-8-sig")):                  # 고칠것1 ±10 % (곡선 점은 없음 -> I 규칙은 비워 둔다)
        prior[row["실험"]] = row
    out = []
    for k in KN:
        for r in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7]:
            x = [1.0, 1.0, 1.0]
            x[KN.index(k)] = r
            rule = {c: "" for c in ("I1", "I2", "I5", "I6")}
            if r in (0.9, 1.1):
                key = f"{ss.KO[k]}_{'감소' if r < 1 else '증가'}10퍼"
                row = next(v for n, v in prior.items() if key in n)
                pick = lambda s: float(row[next(c for c in row if s in c)])
                vals = dict(상태="ok", 스윕V="4.0", 격자="1.0", Vth=pick("Vth("), gm=pick("gm("), Id4V=pick("Id_4V"), 누설=pick("누설"))
            else:
                j = ss.step_json(k, r)
                if not j or j.get("vth") is None:
                    continue
                ck = bk.checks(j)
                rule = {c: str(ck[c]) for c in ("I1", "I2", "I5", "I6")}
                vals = dict(상태=j["status"], 스윕V=j.get("sweep", 4.0), 격자=1.0, Vth=j["vth"], gm=j["gm"], Id4V=j["id4v"], 누설=j.get("i_leak", ""))
            res = ss.bv_coarse(k, r)
            has = bool(res and res.get("bvt_levels"))
            b1, b3 = ss.cb.check_bv_rules(res) if has else ("", "")
            lv = (res or {}).get("bvt_levels") or {}
            out.append({"출처": "단일노브", "ID": f"S_{k}_{r:.1f}", "층": "단일노브", "확장축": "-", "바디도즈비율": x[0], "에피도핑비율": x[1], "산화막비율": x[2],
                        "시도횟수": 1, **vals, "BV_1e-9": lv.get("1e-09", "") if lv.get("1e-09") is not None else "", "BV_1e-6": lv.get("1e-06", "") if lv.get("1e-06") is not None else "",
                        **rule, "B1": b1, "B3": b3, "B4": ss.b4_ok(k, r) if has else "", "영역안": bool(sp.in_domain(*x)), "외삽시험용": "Y" if abs(r - 1) > 0.3 + 1e-9 else ""})
    return out


def build(n, final=False):
    OUT.mkdir(exist_ok=True)
    rows = batch_rows(n) + single_rows()
    for r in rows:
        for c in ("Vth", "gm", "Id4V", "누설", "BV_1e-9", "BV_1e-6"):
            if r[c] not in ("", None):
                r[c] = float(r[c])
    names = [OUT / f"학습데이터_N{n}.csv"] + ([OUT / "학습데이터_최종.csv"] if final else [])
    for p in names:
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            w.writerows(rows)
    b = [r for r in rows if r["출처"] == "대량실행"]
    s = [r for r in rows if r["출처"] == "단일노브"]
    nbv = lambda g: sum(r["BV_1e-9"] != "" for r in g)
    md = [f"# 최종 학습데이터 설명 (대량 실행 N = {n})", "",
          f"- 파일: `학습데이터_최종.csv` (행 {len(rows)}개 = 대량 실행 {len(b)}개 + 단일 노브 {len(s)}개). 열 {len(COLS)}개.",
          f"- BV 가 있는 행: 대량 실행 {nbv(b)}개 + 단일 노브 {nbv(s)}개 = {nbv(b) + nbv(s)}개.",
          "- **입력**: `바디도즈비율`, `에피도핑비율`, `산화막비율` (기준값 대비 비율, 확산 시간은 30분 고정). **출력**: `Vth`(V), `gm`(A/V/μm), `Id4V`(A/μm), `BV_1e-9`(V, 판정 전류 1e-9 A/μm).",
          "- `출처`: 대량실행(코어 ±30 % 라틴 하이퍼큐브 + 확장 팔) / 단일노브(노브 하나만 ±10~70 %). `층`: 코어 / 확장 / 단일노브. `확장축`: 어느 노브가 ±30 % 바깥인지.",
          "- 규칙 열 I1·I2·I5·I6(IV), B1·B3·B4(BV): True 면 통과. 단일 노브 ±10 % 점은 곡선 점이 저장돼 있지 않아 I 규칙이 비어 있다 (고칠것1에서 이미 정상으로 확인).",
          "- `영역안`: `샘플링계획.in_domain()` 기준 서로게이트를 신뢰하는 영역 안인가. `외삽시험용`: 단일 노브 ±30 % 바깥 점 (외삽 시험에 쓰고, 학습에 넣을지는 선택).",
          "- 가정·한계: TCAD 합성 데이터이고 노이즈는 학습 단계에서 `노이즈가정.py`로 입힌다 (CSV 에는 없음). 단일 노브 BV 는 영역 안의 점만 학습에 쓰는 것을 권장. 기준값은 대량 실행 번호 1번 하나만 둔다.", ""]
    (OUT / "학습데이터_설명.md").write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))
    return rows


def selftest():
    rows = batch_rows(120)
    assert len(rows) == 120 and rows[0]["ID"] == "B001" and rows[0]["확장축"] == "기준값"
    s = single_rows()
    assert 40 <= len(s) <= 46 and len({r["ID"] for r in s}) == len(s)
    assert not any(abs(r["바디도즈비율"] - 1) < 1e-9 and abs(r["에피도핑비율"] - 1) < 1e-9 and abs(r["산화막비율"] - 1) < 1e-9 for r in s)           # 기준값은 단일 노브에 없다
    assert all(sum(abs(r[k] - 1) > 1e-9 for k in ("바디도즈비율", "에피도핑비율", "산화막비율")) == 1 for r in s)                                       # 정확히 한 노브만 바뀜
    far = [r for r in s if r["외삽시험용"] == "Y"]
    assert far and all(max(abs(r[k] - 1) for k in ("바디도즈비율", "에피도핑비율", "산화막비율")) > 0.3 for r in far)
    sv = {r["ID"]: r for r in s}
    assert abs(float(sv["S_tox_1.2"]["Vth"]) - 2.7526) < 1e-3 and abs(float(sv["S_dose_0.9"]["Vth"]) - 2.0621) < 1e-3     # 단계시험 / 고칠것1 값
    assert sv["S_dose_0.3"]["B4"] is False or sv["S_dose_0.3"]["B4"] == ""                                                    # 바디 도즈 −70 % 는 BV 무효
    assert any(r["BV_1e-9"] not in ("", None) for r in s) and sv["S_epi_1.3"]["영역안"] is True
    assert set(COLS) == set(rows[0]) == set(s[0])
    print("selftest ok")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "selftest":
        selftest()
    elif a and a[0].isdigit():
        build(int(a[0]), final="최종" in a[1:])
    else:
        print(__doc__)
