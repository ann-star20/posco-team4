#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
source "$root/scripts/lib/ros-stack-common.sh"
runtime="${FAB_RUNTIME_DIR:-$root/data/ros-stack/wsl}"
action="${1:-}"
shift || true
peer_ip="${JETSON_HOST:-}"
dry_run=false

while (($#)); do
  case "$1" in
    --jetson-ip) peer_ip="${2:-}"; shift 2 ;;
    --dry-run) dry_run=true; shift ;;
    *) echo "알 수 없는 인자: $1" >&2; exit 2 ;;
  esac
done

usage() {
  echo "사용법: $0 {start|status|check|logs|stop} [--jetson-ip IPv4] [--dry-run]"
}

[[ -n "$action" ]] || { usage; exit 2; }
mkdir -p "$runtime"

case "$action" in
  start)
    valid_ipv4 "$peer_ip" || { echo "Jetson 주소가 올바른 IPv4가 아닙니다: $peer_ip" >&2; exit 2; }
    local_ip="$(detect_lan_ip "$peer_ip")" || { echo "WSL LAN IPv4를 찾지 못했습니다." >&2; exit 1; }
    profile="$runtime/wsl-fastdds.generated.xml"
    write_fastdds_profile "$profile" wsl_jetson_runtime "$local_ip" "$peer_ip"
    echo "WSL=$local_ip, Jetson=$peer_ip, DDS=$profile"
    if $dry_run; then
      echo "DRY-RUN: event_gateway.app"
      echo "DRY-RUN: event_gateway.ros_adapter"
      echo "DRY-RUN: event_gateway.verification_worker"
      exit 0
    fi
    [[ -f "$root/.env" ]] || { echo "$root/.env 파일이 없습니다." >&2; exit 1; }
    source_setup_safely /opt/ros/humble/setup.bash
    [[ -f "$HOME/posco-gateway-venv/bin/activate" ]] && source_setup_safely "$HOME/posco-gateway-venv/bin/activate"
    set -a; source_setup_safely "$root/.env"; set +a
    export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}"
    export ROS_LOCALHOST_ONLY=0
    export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
    export FASTRTPS_DEFAULT_PROFILES_FILE="$profile"
    unset FASTDDS_DEFAULT_PROFILES_FILE || true
    export PYTHONPATH="$root/services/event_gateway/src${PYTHONPATH:+:$PYTHONPATH}"
    python_bin="${GATEWAY_PYTHON:-$HOME/posco-gateway-venv/bin/python}"
    [[ -x "$python_bin" ]] || python_bin=python3
    check_python_imports "$python_bin" fastapi psycopg websockets httpx uvicorn pydantic \
      || { echo "Gateway Python 의존성 누락: posco-gateway-venv를 확인하세요." >&2; exit 1; }
    ensure_windows_firewall_rule "ROS2 FastDDS inbound from Jetson" "$peer_ip" "7400-7470"
    start_managed_process gateway-api "$runtime" "$python_bin" -u -m event_gateway.app
    start_managed_process gateway-ros "$runtime" "$python_bin" -u -m event_gateway.ros_adapter
    start_managed_process verification-worker "$runtime" "$python_bin" -u -m event_gateway.verification_worker
    ;;
  status)
    show_managed_status gateway-api "$runtime"
    show_managed_status gateway-ros "$runtime"
    show_managed_status verification-worker "$runtime"
    ;;
  check)
    source_setup_safely /opt/ros/humble/setup.bash
    profile="$runtime/wsl-fastdds.generated.xml"
    [[ -f "$profile" ]] || { echo "먼저 start를 실행하세요." >&2; exit 1; }
    export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-0}" ROS_LOCALHOST_ONLY=0 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
    export FASTRTPS_DEFAULT_PROFILES_FILE="$profile"
    unset FASTDDS_DEFAULT_PROFILES_FILE || true
    show_ros_graph
    ;;
  logs)
    exec tail -n 80 -F "$runtime"/*.log
    ;;
  stop)
    stop_managed_process verification-worker "$runtime"
    stop_managed_process gateway-ros "$runtime"
    stop_managed_process gateway-api "$runtime"
    ;;
  *) usage; exit 2 ;;
esac
