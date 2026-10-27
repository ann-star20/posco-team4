"""고정밀 모드를 실제 배포 코드(Surrogate + HighPrecision)로 끝까지 점검한다: 5-겹 교차검증에서 접힘마다 GP 를 새로 학습·내보내고,
같은 접힘의 학습 점을 TabPFN 문맥으로 넣어 보지 않은 대량 실행 샘플을 예측한 뒤 기본 모드(GP)와 고정밀 모드를 비교한다 (약 3~5분).
  python 고정밀_점검.py   # 결과/고정밀평가.md
"""
import re
import importlib.util
import json
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")
HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True


def load_file(pred, name):
    f = next(p for p in HERE.glob("*.py") if pred(p) and p.name != Path(__file__).name)
    s = importlib.util.spec_from_file_location(name, f)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


B = load_file(lambda p: re.search(r"^def fit_all\b", p.read_text(encoding="utf-8"), re.M), "builder")
SUR = load_file(lambda p: re.search(r"^class Surrogate\b", p.read_text(encoding="utf-8"), re.M), "sur")
HP = load_file(lambda p: re.search(r"^class HighPrecision\b", p.read_text(encoding="utf-8"), re.M), "hp")
X, Y, kind, rows = B.load(HERE / "데이터" / "학습데이터_최종.csv")
cfg = dict(bv_input=json.loads((HERE / "모델" / "모델정보.json").read_text(encoding="utf-8"))["BV입력"], bv_log=False)
bi, si = np.where(kind == "batch")[0], np.where(kind == "single")[0]
from sklearn.model_selection import KFold

res = {"기본(GP)": [[] for _ in range(4)], "고정밀(GP+TabPFN)": [[] for _ in range(4)]}
zs = {k: [[] for _ in range(4)] for k in res}
for n, (tr, te) in enumerate(KFold(5, shuffle=True, random_state=0).split(bi)):
    trn = np.r_[bi[tr], si]
    m = B.fit_all(X[trn], Y[trn], cfg)
    tmp = Path(tempfile.mkdtemp())
    np.savez(tmp / "gp.npz", **{f"{k}__{kk}": np.asarray(vv, np.float64) for k in ("vth", "log_gm", "log_id4v", "bv") for kk, vv in B.export_gp(m[k]).items()})
    shutil.copy(HERE / "모델" / "영역.json", tmp / "영역.json")
    shutil.copy(HERE / "모델" / "모델정보.json", tmp / "모델정보.json")
    np.savez(tmp / "학습배열.npz", X=X[trn], Y=Y[trn])
    sur = SUR.Surrogate(tmp)
    hp = HP.HighPrecision(sur, train_npz=tmp / "학습배열.npz")
    Xte, Yte = X[bi[te]], Y[bi[te]]
    Pg, Sg = sur.raw_calibrated(Xte)
    r = hp.predict(Xte, strict=False)                                       # (이 안에서 기록된 고정밀 보정배율이 이미 적용돼 있으면 되돌려서 원래 σ 로 비교)
    c0 = sur.info.get("고정밀보정배율", {})
    Pc = np.c_[r["vth"], np.log(r["gm"]), np.log(r["id4v"]), r["bv"]]
    Sc = np.c_[r["sigma_vth"], r["sigma_gm"], r["sigma_id4v"], r["sigma_bv"]] / np.array([c0.get(k, 1.0) for k in ("vth", "gm", "id4v", "bv")])
    for name, P, S in (("기본(GP)", Pg, Sg), ("고정밀(GP+TabPFN)", Pc, Sc)):
        for j in range(4):
            ok = ~np.isnan(Yte[:, j])
            res[name][j] += list(B.err(P[ok, j], Yte[ok, j], j))
            zs[name][j] += list(np.abs(P[ok, j] - Yte[ok, j]) / S[ok, j])
    print(f"접힘 {n} 끝", flush=True)
unit = ["mV", "%", "%", "V"]
L = ["# 고정밀 모드 점검 (배포 코드로, 5-겹 교차검증 1회)", "", "접힘마다 GP 를 새로 학습하고 TabPFN 문맥도 그 접힘의 학습 점만 사용. 불확실도는 GP 보정 배율이 적용된 σ.", "",
     "| 출력 | 기본(GP) RMSE | 고정밀 RMSE | 기본 2σ 포함 / 오차÷σ | 고정밀 2σ 포함 / 오차÷σ (보정 전) | 고정밀 보정배율 → 보정 후 2σ 포함 |", "|---|---|---|---|---|---|"]
cal = {}
for j, k in enumerate(B.OUTS):
    a, b = res["기본(GP)"][j], res["고정밀(GP+TabPFN)"][j]
    za, zb = np.array(zs["기본(GP)"][j]), np.array(zs["고정밀(GP+TabPFN)"][j])
    cal[k] = max(1.0, float(np.sqrt(np.mean(zb ** 2))))
    L.append(f"| {k} ({unit[j]}) | {np.sqrt(np.mean(np.square(a))):.3g} | {np.sqrt(np.mean(np.square(b))):.3g} | {100 * np.mean(za <= 2):.0f} % / {np.sqrt(np.mean(za ** 2)):.2f} | {100 * np.mean(zb <= 2):.0f} % / {np.sqrt(np.mean(zb ** 2)):.2f} | {cal[k]:.2f} → {100 * np.mean(zb / cal[k] <= 2):.0f} % |")
info_path = HERE / "모델" / "모델정보.json"
info = json.loads(info_path.read_text(encoding="utf-8"))
info["고정밀보정배율"] = cal
info_path.write_text(json.dumps(info, ensure_ascii=False, indent=1), encoding="utf-8")
(HERE / "결과" / "고정밀평가.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("\n".join(L))
