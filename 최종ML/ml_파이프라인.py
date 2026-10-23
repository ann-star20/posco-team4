"""Jetson 진입점: 기본 모드(2단 GP)와 고정밀 모드(GP+TabPFN)를 한 객체로 묶는다.
  fast_predict(X)  : 기본 모드. NumPy 만, 수만 개 후보도 수 초. 진단의 탐색 단계에 쓴다.
  refine(X)        : 고정밀 모드. 후보를 수십 개로 좁힌 뒤 최종 확인에 쓴다. TabPFN 을 쓸 수 없으면 기본 모드로 되돌리고 이유를 알려 준다.
  python ml_파이프라인.py   # 흐름 시연 (후보 3만 개 -> 상위 20개 -> 고정밀 확인) 과 시간 측정
"""
import re
import importlib.util
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def _load(classname, exclude=()):
    f = next(p for p in HERE.glob("*.py") if re.search(rf"^class {classname}\b", p.read_text(encoding="utf-8"), re.M) and p.name != Path(__file__).name and p.name not in exclude)
    s = importlib.util.spec_from_file_location("mod_" + classname, f)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return getattr(m, classname)


class TwoStagePipeline:
    def __init__(self, high_precision="auto", device="auto"):
        self.fast = _load("Surrogate")()
        self.hp, self.hp_error = None, None
        if high_precision:
            try:
                self.hp = _load("HighPrecision")(self.fast, device=device)
            except Exception as e:                              # torch·tabpfn·가중치가 없는 장치에서는 기본 모드만 쓴다
                self.hp_error = f"{type(e).__name__}: {e}"
                if high_precision is True:
                    raise

    @property
    def high_precision_available(self):
        return self.hp is not None

    def fast_predict(self, X, strict=True):
        r = self.fast.predict(X, strict=strict)
        r["mode"] = "기본(2단 GP)"
        return r

    def refine(self, X, strict=True):
        if self.hp is None:
            r = self.fast.predict(X, strict=strict)
            r["mode"] = f"기본(2단 GP) — 고정밀 사용 불가 ({self.hp_error or '비활성'})"
            return r
        r = self.hp.predict(X, strict=strict)
        r["mode"] = "고정밀(GP+TabPFN)"
        return r


def demo():
    p = TwoStagePipeline()
    print("고정밀 모드:", "사용 가능" if p.high_precision_available else f"사용 불가 ({p.hp_error})")
    rng = np.random.default_rng(1)
    truth = np.array([[0.9, 1.15, 1.12]])                                   # 가상의 실제 노브 (진단은 이것을 모르고 측정값만 안다)
    t = p.fast_predict(truth)
    sig = np.array([0.05, 0.05, 0.05, 0.3])
    y = np.array([t["vth"][0], np.log(t["gm"][0]), np.log(t["id4v"][0]), t["bv"][0]]) + rng.normal(0, sig * np.array([1, 1, 1, 1]))
    # 1) 기본 모드로 후보 3만 개 평가
    C = np.c_[rng.uniform(0.7, 1.3, (30000, 1)), rng.uniform(0.7, 1.3, (30000, 1)), rng.uniform(0.7, 1.3, (30000, 1))]
    t0 = time.perf_counter()
    r = p.fast_predict(C)
    P = np.c_[r["vth"], np.log(r["gm"]), np.log(r["id4v"]), r["bv"]]
    S = np.c_[r["sigma_vth"], r["sigma_gm"], r["sigma_id4v"], r["sigma_bv"]]
    chi2 = np.nansum(((P - y) / np.sqrt(S ** 2 + sig ** 2)) ** 2, axis=1)
    t_fast = time.perf_counter() - t0
    top = np.argsort(chi2)[:20]
    print(f"[기본] 후보 {len(C)}개 평가 {t_fast:.1f}초 -> 측정값과 가장 맞는 상위 {len(top)}개 선택 (최소 χ² {chi2[top[0]]:.2f})")
    # 2) 고정밀 모드로 상위 후보 확인
    t0 = time.perf_counter()
    r2 = p.refine(C[top])
    print(f"[{r2['mode']}] 상위 20개 확인 {time.perf_counter() - t0:.1f}초")
    print("  후보 1 노브:", np.round(C[top[0]], 3), "(가상 실제:", truth[0], ")")
    print("  Vth GP %.3f V → 합친 값 %.3f V (σ %.4f)" % (r["vth"][top[0]], r2["vth"][0], r2["sigma_vth"][0]))
    print("  BV  GP %.2f V → 합친 값 %.2f V (σ %.3f)" % (r["bv"][top[0]], r2["bv"][0], r2["sigma_bv"][0]))


if __name__ == "__main__":
    demo()
