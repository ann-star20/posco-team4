"""후보 모델 전부를 같은 데이터·같은 시험으로 평가해 결과/비교결과.json 에 저장한다 (이미 있는 모델은 건너뜀).
  python 비교실행.py            # 전체 (오래 걸림: MLP·딥GP 가 느림)
  python 비교실행.py 1 2 3      # 번호로 일부만
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from 공통 import Data
from 공통 import evaluate
import 모델들 as M

OUT = Path(__file__).resolve().parent / "결과"
OUT.mkdir(exist_ok=True)
PATH = OUT / "비교결과.json"


def main(pick):
    D = Data()
    for name, (fn, slow) in M.MODELS.items():
        if pick and name.split()[0] not in pick:
            continue
        R = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
        if name in R:
            print(name, "이미 있음")
            continue
        t0 = time.time()
        print("==", name, flush=True)
        R_ = evaluate(fn, D, slow=slow, seeds=(0,) if slow else (0, 1), do_arms=not slow, do_noise=not slow, log=lambda m: print(m, flush=True))
        R_["seconds"] = time.time() - t0
        R = json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}       # 다른 프로세스가 쓴 것을 덮지 않도록 다시 읽는다
        R[name] = R_
        PATH.write_text(json.dumps(R, ensure_ascii=False, indent=1), encoding="utf-8")
        print(name, "끝", round(time.time() - t0), "s", flush=True)


if __name__ == "__main__":
    main(set(sys.argv[1:]))
