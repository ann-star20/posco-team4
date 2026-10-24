"""Jetson 배포 번들 만들기 (개발 PC 에서만 쓴다, 번들에는 들어가지 않는다).
  python 번들만들기.py
결과: ../Jetson배포/fabrx/ (폴더 그대로 복사해도 되고), ../Jetson배포/fabrx_jetson.tar.gz (한글 파일 이름이 유지되는 tar, 권장)
  - 서비스에 필요한 파일만 복사 (재학습·평가·보고서·학습 데이터·결과 폴더는 제외)
  - manifest.json (크기와 SHA-256), 파이썬 3.8 문법 호환 검사, 절대 경로 검사
모델이나 코드를 고친 뒤에는 이 스크립트를 다시 실행해 번들을 새로 만든다.
"""
import ast
import hashlib
import json
import shutil
import sys
import tarfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "Jetson배포"
B = OUT / "fabrx"
DEV_ONLY_ML = {"최종ML만들기.py", "고정밀_점검.py"}                 # 재학습·점검용 (PC 에서만 필요, sklearn 사용)


def copy(src, dst, lf=False):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if lf:                                                         # 셸 스크립트와 서비스 템플릿은 줄바꿈을 LF 로
        dst.write_bytes(src.read_bytes().replace(b"\r\n", b"\n"))
    else:
        shutil.copy2(src, dst)


def main():
    if B.exists():
        shutil.rmtree(B)
    # 최종ML: 실행 코드와 모델
    for f in (ROOT / "최종ML").glob("*.py"):
        if f.name not in DEV_ONLY_ML:
            copy(f, B / "최종ML" / f.name)
    for sub in ("모델", "테스트"):
        for f in (ROOT / "최종ML" / sub).rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                copy(f, B / "최종ML" / f.relative_to(ROOT / "최종ML"))
    # 진단 에이전트
    copy(ROOT / "진단에이전트" / "진단에이전트.py", B / "진단에이전트" / "진단에이전트.py")
    copy(ROOT / "진단에이전트" / "README.md", B / "docs" / "진단에이전트_README.md")
    # 통신
    for n in ("모델서비스.py", "변환기.py", "시험.py", "README.md", "계약_보완.md"):
        copy(HERE / n, B / "통신" / n)
    for f in (HERE / "예시").glob("*.json"):
        copy(f, B / "통신" / "예시" / f.name)
    # 도구 (루트로 펼친다)
    for f in (HERE / "도구").iterdir():
        if f.is_file():
            copy(f, B / f.name, lf=f.suffix in (".sh", ".template"))
    # 문서
    for n in ("README.md", "Jetson_흐름.md", "Jetson_테스트_체크리스트.md"):
        copy(ROOT / "최종ML" / n, B / "docs" / (("최종ML_" + n) if n == "README.md" else n))
    # 점검: 파이썬 3.8 문법, 절대 경로
    problems = []
    for f in B.rglob("*.py"):
        src = f.read_text(encoding="utf-8")
        try:
            ast.parse(src, feature_version=(3, 8))
        except SyntaxError as e:
            problems.append(f"{f.relative_to(B)}: 파이썬 3.8 문법 오류 {e}")
        for bad in ("C:\\", "C:/", "Downloads", "Desktop"):
            if bad in src:
                problems.append(f"{f.relative_to(B)}: 절대 경로 의심 '{bad}'")
    # manifest
    files = []
    for f in sorted(B.rglob("*")):
        if f.is_file() and f.name != "manifest.json":
            files.append({"path": f.relative_to(B).as_posix(), "size": f.stat().st_size, "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
    info = json.loads((B / "최종ML" / "모델" / "모델정보.json").read_text(encoding="utf-8"))
    (B / "manifest.json").write_text(json.dumps({"만든 시각": time.strftime("%Y-%m-%d %H:%M:%S"), "모델 만든 날": info.get("만든날"), "files": files}, ensure_ascii=False, indent=1), encoding="utf-8")
    # tar.gz (한글 이름 유지: PAX 형식, 권한 정리)
    tgz = OUT / "fabrx_jetson.tar.gz"

    def flt(ti):
        ti.uid = ti.gid = 0
        ti.uname = ti.gname = ""
        ti.mode = 0o755 if (ti.isdir() or ti.name.endswith(".sh")) else 0o644
        return ti
    with tarfile.open(tgz, "w:gz", format=tarfile.PAX_FORMAT) as t:
        t.add(B, arcname="fabrx", filter=flt)
    total = sum(e["size"] for e in files)
    print(f"번들: {B}  (파일 {len(files)}개, {total / 1e6:.1f} MB)")
    print(f"tar.gz: {tgz}  ({tgz.stat().st_size / 1e6:.1f} MB)")
    for p in problems:
        print("문제:", p)
    if problems:
        sys.exit(1)
    print("점검 통과: 파이썬 3.8 문법 호환, 절대 경로 없음")


if __name__ == "__main__":
    main()
