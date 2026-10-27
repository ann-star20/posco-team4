"""high_confidence(임계값 AUTO)로 걸린 보정 후보 7개를 실제 TCAD로 직접 돌려 규격 안인지 확정 검증한다.
소이탈평가.py 의 근사(이웃 TCAD로 추정)를 대신해 직접 계산한다. 결과/소이탈평가_보정후공정값.csv 에서 high_confidence=True 인
(번호, 비율) 조합 중 중복(N=25/100 같은 값)을 제거한 7개를 쓴다. 대량실행.py 는 수정하지 않고 process(row) 만 가져다 쓴다.
  python 고신뢰_직접검증.py
"""
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BULK = ROOT / "대량작업2" / "대량실행" / "대량실행.py"
spec = importlib.util.spec_from_file_location("대량실행_검증", BULK)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

SPEC_V = (1.7, 2.6)
BV_MIN = 40.0
OFFSET = 950001                                            # 기존 1~182, TCAD서비스 시험(900001대)과 안 겹치는 번호

candidates = [                                              # 소이탈평가_보정후공정값.csv 의 high_confidence=True, 중복 제거
    {"원샘플": 152, "dose": 0.9908, "epi": 1.0042, "tox": 1.0109},
    {"원샘플": 155, "dose": 1.0738, "epi": 0.9850, "tox": 0.9528},
    {"원샘플": 157, "dose": 0.9441, "epi": 1.0143, "tox": 1.0343},
    {"원샘플": 158, "dose": 1.1045, "epi": 0.9940, "tox": 0.9431},
    {"원샘플": 169, "dose": 0.9374, "epi": 0.9950, "tox": 1.0054},
    {"원샘플": 174, "dose": 0.9949, "epi": 0.9753, "tox": 0.9789},
    {"원샘플": 175, "dose": 1.0087, "epi": 0.9852, "tox": 0.9881},
]

rows = [{"번호": OFFSET + i, "층": "검증", "확장축": "고신뢰검증", "바디도즈비율": c["dose"], "에피도핑비율": c["epi"],
         "산화막비율": c["tox"], "스윕(V)": "4", "BV계산": "Y"} for i, c in enumerate(candidates)]
no_to_sample = {r["번호"]: c["원샘플"] for r, c in zip(rows, candidates)}


def run_one(row):
    return row["번호"], m.process(row)


out = []
with ThreadPoolExecutor(3) as ex:
    for no, r in ex.map(run_one, rows):
        vth, bv = r.get("vth"), (r.get("bvt_levels") or {}).get("1e-09")
        ok = vth is not None and SPEC_V[0] <= vth <= SPEC_V[1] and bv is not None and bv >= BV_MIN
        out.append({"원샘플": no_to_sample[no], "검증번호": no, "vth": vth, "bv": bv, "규격안": bool(ok)})

out.sort(key=lambda x: x["원샘플"])
(HERE / "결과" / "고신뢰_직접검증.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(out, ensure_ascii=False, indent=2))
bad = [o for o in out if not o["규격안"]]
print(f"\n{len(out)}건 중 규격 밖 {len(bad)}건" + (f": 원샘플 {[o['원샘플'] for o in bad]}" if bad else " (오판 없음)"))
