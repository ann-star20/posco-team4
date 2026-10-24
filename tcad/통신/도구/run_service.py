"""모델 서비스 시작 (영문 이름의 진입점: systemd 와 터미널 어디서든 같은 방식으로 시작한다).
  python3 run_service.py [--port 8300] [--token 영문토큰] [--log-file 경로] [--no-agent]
환경변수: FAB_SERVICE_TOKEN, FAB_SERVICE_LOG
"""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
svc_dir = ROOT / "통신"
if not (svc_dir / "모델서비스.py").exists():
    sys.exit(f"통신/모델서비스.py 를 찾을 수 없다: {svc_dir}  (fabrx 폴더 전체를 그대로 복사했는지 확인하고 `python3 check_env.py` 를 실행하라)")
sys.path.insert(0, str(svc_dir))
runpy.run_path(str(svc_dir / "모델서비스.py"), run_name="__main__")
