"""Jetson(또는 아무 PC)에서 서로게이트 추론 속도를 잰다. NumPy 만 필요하다.
  python jetson_벤치.py
복사할 파일: 서로게이트.py, jetson_벤치.py, 모델/ (gp.npz, 영역.json, 모델정보.json)
"""
import os
import platform
import time

import numpy as np

import re
import importlib.util as _u
from pathlib import Path

_f = next(p for p in Path(__file__).resolve().parent.glob("*.py") if re.search(r"^class Surrogate\b", p.read_text(encoding="utf-8"), re.M) and p.name != Path(__file__).name)
_s = _u.spec_from_file_location("surrogate_runtime", _f)
_m = _u.module_from_spec(_s)
_s.loader.exec_module(_m)
Surrogate = _m.Surrogate

s = Surrogate()
print("장치:", platform.machine(), platform.processor() or "-", "| CPU 코어", os.cpu_count(), "| NumPy", np.__version__, "| Python", platform.python_version())
rng = np.random.default_rng(0)
X = rng.uniform(0.7, 1.3, (100_000, 3))
s.predict(X[:100])                                                    # 예열
t = time.perf_counter()
for i in range(300):
    s.predict(X[i:i + 1])
print(f"1점 예측 지연: {(time.perf_counter() - t) / 300 * 1000:.2f} ms")
for n in (1_000, 10_000, 100_000):
    t = time.perf_counter()
    s.predict(X[:n])
    dt = time.perf_counter() - t
    print(f"{n:>7}점: {dt:.2f} 초 ({dt / n * 1e6:.1f} μs/점)")
r = s.predict([[1, 1, 1]])
ref = s.info["기준값"]
print("기준값 예측:", {k: float(r[k][0]) for k in ("vth", "gm", "id4v", "bv")}, "| TCAD 기준값:", ref)
print("진단에서 후보 7만 개를 평가한다면 위 10만 점 시간의 약 0.7배.")
