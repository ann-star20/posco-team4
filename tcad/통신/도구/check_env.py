"""Jetson(또는 어떤 장치)에서 모델 서비스를 켜기 전에 환경과 파일을 점검한다.
  python3 check_env.py            # 환경, 파일 목록(manifest), 포트 점검
  python3 check_env.py --smoke    # 위 + 서비스를 메모리에서 실제로 불러 예측과 진단을 한 번씩 시험 (수 초)
실패 항목마다 고치는 방법을 적어 준다. 모두 통과하면 종료 코드 0.
"""
import hashlib
import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ok_all = True


def line(ok, name, detail="", hint=""):
    global ok_all
    ok_all &= bool(ok)
    print(("통과  " if ok else "실패  ") + name + (f"  ({detail})" if detail else ""))
    if not ok and hint:
        print("      → " + hint)


def warn(name, detail=""):
    print("참고  " + name + (f"  ({detail})" if detail else ""))


print(f"점검 위치: {ROOT}")
# 1) 파이썬, 인코딩, NumPy
v = sys.version_info
line(v >= (3, 8), "Python 3.8 이상", f"{v.major}.{v.minor}.{v.micro}", "python3 를 3.8 이상으로 설치하라")
enc = sys.getfilesystemencoding().lower().replace("-", "")
line(enc == "utf8", "파일 시스템 인코딩 UTF-8 (한글 파일 이름을 위해 필요)", sys.getfilesystemencoding(), "export LANG=C.UTF-8 LC_ALL=C.UTF-8 를 설정하고 다시 실행하라 (systemd 서비스는 설치 스크립트가 설정한다)")
try:
    import numpy as np
    line(True, "NumPy", np.__version__)
except Exception as e:
    np = None
    line(False, "NumPy", str(e), "pip3 install numpy")
# 2) 폴더 구조와 manifest
for d in ("최종ML", "진단에이전트", "통신"):
    line((ROOT / d).is_dir(), f"폴더 {d}/", "", "fabrx 폴더 전체를 그대로 복사하라 (tar 로 풀면 한글 이름이 유지된다)")
mf = ROOT / "manifest.json"
if mf.exists():
    man = json.loads(mf.read_text(encoding="utf-8"))
    missing, bad = [], []
    for e in man["files"]:
        p = ROOT / e["path"]
        if not p.exists():
            missing.append(e["path"])
        elif p.stat().st_size != e["size"] or hashlib.sha256(p.read_bytes()).hexdigest() != e["sha256"]:
            bad.append(e["path"])
    line(not missing, f"파일 {len(man['files'])}개 모두 있다", f"없는 파일 {missing[:5]}" if missing else "", "없는 파일을 다시 복사하라 (같은 번들 tar.gz 를 다시 풀기)")
    model_bad = [f for f in bad if f.startswith("최종ML/모델/")]
    other_bad = [f for f in bad if f not in model_bad]
    line(not model_bad, "모델 파일 내용이 번들과 같다 (SHA-256)", f"다른 파일 {model_bad[:5]}" if model_bad else "", "복사 중 손상되었거나 모델을 바꾼 것이다. 모델을 바꾼 것이 아니면 다시 복사하라")
    if other_bad:
        warn("번들과 내용이 다른 코드·문서 파일 (의도한 수정이면 무시)", str(other_bad[:6]))
else:
    warn("manifest.json 이 없어 파일 목록 점검을 건너뜀")
# 3) 모델 파일
mdl = ROOT / "최종ML" / "모델"
for f in ("gp.npz", "영역.json", "모델정보.json"):
    line((mdl / f).exists(), f"모델 파일 {f}", "", "최종ML/모델/ 를 다시 복사하라")
if np is not None and (mdl / "gp.npz").exists():
    try:
        z = np.load(mdl / "gp.npz")
        line(len(z.files) == 32, "gp.npz 내용 (배열 32개)", f"{len(z.files)}개")
    except Exception as e:
        line(False, "gp.npz 읽기", str(e), "파일이 손상되었다. 다시 복사하라")
# 4) 선택 기능: 고정밀 모드. torch 와 tabpfn 은 하위 프로세스에서 조용히 불러 본다 (torch 가 NumPy 버전과 맞지 않으면 긴 경고가 쏟아지고 멈출 수 있다)
import subprocess


def probe(code):
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=180)
        return r.returncode, r.stdout.strip(), r.stderr
    except Exception as e:
        return 1, "", str(e)


w = mdl / "tabpfn" / "tabpfn-v2-regressor.ckpt"
rc, out, err = probe("import torch, numpy; torch.from_numpy(numpy.zeros(2)); print(torch.__version__, torch.cuda.is_available())")
t, conflict = None, False
if rc == 0 and "Failed to initialize NumPy" not in err and out:
    ver, cuda = out.split()[0], out.split()[-1]
    t = f"torch {ver}, CUDA {'사용 가능' if cuda == 'True' else '없음 (CPU)'}"
elif "numpy" in err.lower() and "torch" not in err.split("No module named")[-1][:20].lower():
    conflict = True
rc2, out2, _ = probe("import tabpfn; print(getattr(tabpfn, '__version__', '?'))")
tp = f"tabpfn {out2}" if rc2 == 0 else None
if t and tp and w.exists():
    warn("고정밀 모드 사용 가능", f"{t}, {tp}, 가중치 {w.stat().st_size // 1_000_000} MB")
else:
    warn("고정밀 모드는 쓸 수 없음 (기본 모드 2단 GP 만으로 정상 동작)", f"torch {'정상' if t else ('설치되어 있으나 NumPy 와 맞지 않음' if conflict else '없음')}, tabpfn {'있음' if tp else '없음'}, 가중치 {'있음' if w.exists() else '없음'}")
    if conflict:
        warn("torch 가 NumPy 1.x 용으로 만들어져 NumPy 2.x 와 맞지 않는다", "고정밀 모드가 필요하면 pip3 install 'numpy<2' (다른 프로그램에 영향이 있을 수 있으니 확인 후). 기본 모드는 영향 없음")
# 5) 포트
port = 8300
s = socket.socket()
try:
    s.bind(("127.0.0.1", port))
    line(True, f"포트 {port} 사용 가능")
except OSError:
    line(False, f"포트 {port} 사용 가능", "이미 사용 중", f"이미 서비스가 켜져 있거나 다른 프로그램이 쓰는 중이다 (ss -ltnp | grep {port}). 다른 포트는 --port 로 지정")
finally:
    s.close()
# 6) 실제 불러오기 시험
if "--smoke" in sys.argv and ok_all:
    sys.path.insert(0, str(ROOT / "통신"))
    try:
        import time
        t0 = time.time()
        import 모델서비스 as ms
        svc = ms.Service()
        line(True, "서비스 불러오기", f"{time.time() - t0:.1f}초, 작업 {svc.tasks()}")
        base = {"body_dose": 7.7e12, "epi_doping": 1.7e16, "oxide_thickness": 0.06}
        code, r = svc.predict({"schema_version": 1, "task_type": "surrogate", "request_id": "chk-1", "input_payload": {"process_parameters": base}})
        p = r["result_payload"]
        line(code == 200 and abs(p["vth"] - 2.26) < 0.05 and abs(p["bv"] - 41.1) < 1.0, "기준값 예측 (Vth 약 2.26 V, BV 약 41 V)", f"vth {p['vth']:.3f}, bv {p['bv']:.1f}")
        if svc.agent is not None:
            m = {"vth": p["vth"], "gm": p["gm"], "id_on": p["id_on"], "bv": p["bv"]}
            code, r = svc.predict({"schema_version": 1, "task_type": "diagnose", "request_id": "chk-2", "input_payload": {"measurements": m, "n_wafers": 25}})
            line(code == 200 and r["status"] == "succeeded", "진단 시험", f"{r['metadata']['processing_ms']:.0f} ms, 판정 {r['result_payload']['decision']['top_category']}")
        else:
            line(False, "진단 기능", str(svc.agent_error), "진단에이전트/ 폴더를 확인하라")
    except Exception as e:
        line(False, "서비스 불러오기", f"{type(e).__name__}: {e}", "위의 실패 항목을 먼저 고치고 다시 실행하라")
print("== 전체 판정:", "서비스를 켤 수 있다" if ok_all else "실패 항목을 먼저 고쳐라")
sys.exit(0 if ok_all else 1)
