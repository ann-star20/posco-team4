#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then echo '.env 파일이 없습니다.' >&2; exit 1; fi
set -a
source .env
set +a
for required in DATABASE_URL APPROVAL_OPERATOR APPROVAL_TOKEN ROS_COMMAND_KEY; do
  if [[ -z "${!required:-}" ]]; then echo "$required 값을 .env에 설정해야 합니다." >&2; exit 1; fi
done
export PYTHONPATH="$PWD/services/event_gateway/src"
pids=()
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM
if [[ "${TCAD_MODE:-mock}" == mock ]]; then
  python3 -m mock_tcad.app & pids+=("$!")
fi
python3 -m event_gateway.verification_worker & pids+=("$!")
python3 -m event_gateway.app & pids+=("$!")
if command -v ros2 >/dev/null 2>&1; then
  python3 -m event_gateway.ros_adapter & pids+=("$!")
else
  echo 'ROS 환경 미소싱: Gateway/TCAD만 시작했습니다. source /opt/ros/humble/setup.bash 후 bridge를 실행하세요.'
fi
wait
