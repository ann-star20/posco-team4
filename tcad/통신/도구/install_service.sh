#!/bin/bash
# 모델 서비스를 Jetson 부팅 때 자동으로 켜지게 등록한다 (systemd).
#   sudo ./install_service.sh install     # 등록하고 바로 시작
#   sudo ./install_service.sh status      # 상태와 최근 로그
#   sudo ./install_service.sh uninstall   # 등록 해제
# 이 스크립트는 Windows 에서는 시험하지 못했다 (systemd 가 필요). 처음 쓸 때 결과를 확인할 것.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
ACTION="${1:-install}"
UNIT=/etc/systemd/system/fabrx-model.service

if [ "$(id -u)" -ne 0 ]; then
  echo "root 권한이 필요하다: sudo $0 $ACTION"; exit 1
fi
USER_NAME="${SUDO_USER:-root}"

case "$ACTION" in
  install)
    PYTHON="$(command -v python3)"
    [ -n "$PYTHON" ] || { echo "python3 를 찾을 수 없다"; exit 1; }
    [ -f "$DIR/fabrx-model.service.template" ] || { echo "fabrx-model.service.template 이 없다"; exit 1; }
    systemctl stop fabrx-model.service 2>/dev/null || true          # 다시 설치할 때 이미 켜진 서비스가 포트를 잡고 있으면 점검이 실패하므로 먼저 멈춘다
    if "$PYTHON" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8300/health', timeout=3)" >/dev/null 2>&1; then
      echo "8300 포트에서 이미 서비스가 동작 중이다. 터미널에서 직접 켠 python3 run_service.py 일 가능성이 크다."
      echo "그 터미널에서 Ctrl+C 로 끈 뒤 다시 실행하라 (또는 ss -ltnp | grep 8300 으로 확인)."
      exit 1
    fi
    echo "사전 점검 중 (check_env.py)..."
    sudo -u "$USER_NAME" env LANG=C.UTF-8 LC_ALL=C.UTF-8 "$PYTHON" "$DIR/check_env.py" || { echo "점검에 실패했다. 위 안내대로 고친 뒤 다시 실행하라 (포트 사용 중 때문이면 기존 서비스를 먼저 멈춘다)"; exit 1; }
    mkdir -p /var/log/fabrx /etc/fabrx
    chown "$USER_NAME" /var/log/fabrx
    if [ ! -f /etc/fabrx/service.env ]; then
      printf '# 토큰을 쓰려면 아래 줄의 # 를 지우고 영문 토큰으로 바꾼다. Worker 는 요청 헤더 X-Fab-Token 에 같은 값을 보낸다.\n#FAB_SERVICE_TOKEN=change-me\n' > /etc/fabrx/service.env
      chmod 600 /etc/fabrx/service.env
    fi
    sed -e "s|@USER@|$USER_NAME|g" -e "s|@DIR@|$DIR|g" -e "s|@PYTHON@|$PYTHON|g" "$DIR/fabrx-model.service.template" > "$UNIT"
    systemctl daemon-reload
    systemctl enable --now fabrx-model.service
    sleep 3
    systemctl --no-pager status fabrx-model.service | head -n 12 || true
    echo "확인: curl http://127.0.0.1:8300/health   로그: /var/log/fabrx/model-service.log (또는 journalctl -u fabrx-model)"
    ;;
  status)
    systemctl --no-pager status fabrx-model.service | head -n 15 || true
    tail -n 20 /var/log/fabrx/model-service.log 2>/dev/null || true
    ;;
  uninstall)
    systemctl disable --now fabrx-model.service 2>/dev/null || true
    rm -f "$UNIT"
    systemctl daemon-reload
    echo "등록 해제했다 (/etc/fabrx, /var/log/fabrx 는 남겨 두었다)"
    ;;
  *)
    echo "사용법: sudo $0 [install|status|uninstall]"; exit 1 ;;
esac
