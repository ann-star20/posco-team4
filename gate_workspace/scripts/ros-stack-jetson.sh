#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/scripts/lib/ros-stack-common.sh"
runtime="${FAB_RUNTIME_DIR:-$root/data/ros-stack/jetson}"
action="${1:-}"
shift || true
peer_ip="${WSL_HOST:-}"
dry_run=false

while (($#)); do
  case "$1" in
    --wsl-ip) peer_ip="${2:-}"; shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    *) echo "알 수 없는 인자: $1" >&2; exit 2 ;;
  esac
done

usage() {
  echo "사용법: $0 {start|status|check|logs|stop} [--wsl-ip IPv4] [--dry-run]"
}

[[ -n "$action" ]] || { usage; exit 2; }
mkdir -p "$runtime"

case "$action" in
  start)
    valid_ipv4 "$peer_ip" || { echo "WSL 주소가 올바른 IPv4가 아닙니다: $peer_ip" >&2; exit 2; }
    local_ip="$(detect_lan_ip "$peer_ip")" || { echo "Jetson LAN IPv4를 찾지 못했습니다." >&2; exit 1; }
    profile="$runtime/jetson-fastdds.generated.xml"
    write_fastdds_profile "$profile" jetson_wsl_runtime "$local_ip" "$peer_ip"
    echo "Jetson=$local_ip, WSL=$peer_ip, DDS=$profile"
    if $dry_run; then
      echo "DRY-RUN: fab_virtual_lot.surrogate_worker"
      echo "DRY-RUN: fab_virtual_lot.diagnosis_worker"
      exit 0
    fi
    [[ -f "$root/.env" ]] || { echo "$root/.env 파일이 없습니다." >&2; exit 1; }
    [[ -f "$root/.env.ml-prod" ]] || { echo "$root/.env.ml-prod 파일이 없습니다." >&2; exit 1; }
    [[ -f /home/jetson/vision_env/bin/activate ]] && source_setup_safely /home/jetson/vision_env/bin/activate
    source_setup_safely /opt/ros/humble/setup.bash
    [[ -f "$root/jetson_ws/install_vision/setup.bash" ]] || { echo "install_vision 빌드가 없습니다." >&2; exit 1; }
    source_setup_safely "$root/jetson_ws/install_vision/setup.bash"
    set -a; source_setup_safely "$root/.env"; source_setup_safely "$root/.env.ml-prod"; set +a
    export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
    export ROS_LOCALHOST_ONLY=0
    export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
    export FASTRTPS_DEFAULT_PROFILES_FILE="$profile"
    unset FASTDDS_DEFAULT_PROFILES_FILE || true
    export PYTHONPATH="/home/jetson/vision_env/lib/python3.10/site-packages:$root/jetson_ws/src/fab_virtual_lot${PYTHONPATH:+:$PYTHONPATH}"
    python_bin=/home/jetson/vision_env/bin/python3
    [[ -x "$python_bin" ]] || python_bin=python3
    if ! curl -fsS --max-time 3 "${SURROGATE_PROD_URL:-http://127.0.0.1:8300}/health/ready" >/dev/null; then
      echo "경고: ML HTTP 서비스 readiness 확인 실패. 워커 로그를 확인하세요." >&2
    fi
    check_python_imports "$python_bin" rclpy std_msgs httpx \
      || { echo "Jetson ROS Worker Python 의존성 누락: vision_env를 확인하세요." >&2; exit 1; }
    start_managed_process surrogate-worker "$runtime" "$python_bin" -u -m fab_virtual_lot.surrogate_worker
    start_managed_process diagnosis-worker "$runtime" "$python_bin" -u -m fab_virtual_lot.diagnosis_worker
    ;;
  status)
    show_managed_status surrogate-worker "$runtime"
    show_managed_status diagnosis-worker "$runtime"
    ;;
  check)
    source_setup_safely /opt/ros/humble/setup.bash
    profile="$runtime/jetson-fastdds.generated.xml"
    [[ -f "$profile" ]] || { echo "먼저 start를 실행하세요." >&2; exit 1; }
    export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}" ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
    export FASTRTPS_DEFAULT_PROFILES_FILE="$profile"
    unset FASTDDS_DEFAULT_PROFILES_FILE || true
    show_ros_graph
    echo '=== ML HTTP readiness ==='
    curl -sS --max-time 5 "${SURROGATE_PROD_URL:-http://127.0.0.1:8300}/health/ready" || true
    echo
    ;;
  logs)
    exec tail -n 80 -F "$runtime"/*.log
    ;;
  stop)
    stop_managed_process diagnosis-worker "$runtime"
    stop_managed_process surrogate-worker "$runtime"
    ;;
  *) usage; exit 2 ;;
esac
