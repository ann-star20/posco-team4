#!/usr/bin/env bash
# 현재 .env 모드로 장기 실행. 관리자 승인을 자동으로 만들지 않는다.
set -eo pipefail
cd "$(dirname "$0")/.."
set -a
source .env
set +a
source /opt/ros/humble/setup.bash
set -u
ros_python_paths="/opt/ros/humble/lib/python3.10/site-packages:/opt/ros/humble/local/lib/python3.10/dist-packages"
export PYTHONPATH="$PWD/services/event_gateway/src:$PWD/jetson_ws/src/fab_virtual_lot:$ros_python_paths${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${GATEWAY_PYTHON:-$HOME/posco-gateway-venv/bin/python}"
pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT
trap 'exit 130' INT TERM
if [[ -n "${ROS_TEST_PROFILE:-}" ]]; then export FASTRTPS_DEFAULT_PROFILES_FILE="$ROS_TEST_PROFILE"; fi
if [[ "${START_LOCAL_MOCK_SERVICES:-true}" == true ]]; then
  if [[ "${TCAD_MODE:-mock}" == mock ]]; then "$python_bin" -m mock_tcad.app & pids+=("$!"); fi
  if [[ "${SURROGATE_MODE:-mock}" == mock ]]; then "$python_bin" -m mock_surrogate.app & pids+=("$!"); fi
fi
"$python_bin" -m event_gateway.app & pids+=("$!")
"$python_bin" -m event_gateway.ros_adapter & pids+=("$!")
"$python_bin" -m event_gateway.verification_worker & pids+=("$!")
if [[ "${RUN_EDGE_WORKERS:-true}" == true ]]; then
  "$python_bin" -m fab_virtual_lot.aoi_worker & pids+=("$!")
  "$python_bin" -m fab_virtual_lot.surrogate_worker & pids+=("$!")
fi
if [[ "${AOI_UNITY_DIRECT_ENABLED:-false}" == true ]]; then
  "$python_bin" -m fab_virtual_lot.aoi_unity & pids+=("$!")
fi
if [[ "${UNITY_MODE:-mock}" == mock && -n "${FAB_RUN_ID:-}" ]]; then
  "$python_bin" tools/mock_unity/peer.py --run-id "$FAB_RUN_ID" & pids+=("$!")
fi
# 어느 한 서비스가 끝나면 실패를 드러내고 이 스크립트가 시작한 프로세스만 종료한다.
wait -n "${pids[@]}"
echo '서비스가 종료됐습니다. 위 로그를 확인하세요.' >&2
exit 1
