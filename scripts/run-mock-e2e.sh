#!/usr/bin/env bash
set -eo pipefail
cd "$(dirname "$0")/.."
source /opt/ros/humble/setup.bash
set -u
ros_python_paths="/opt/ros/humble/lib/python3.10/site-packages:/opt/ros/humble/local/lib/python3.10/dist-packages"
export PYTHONPATH="$PWD/services/event_gateway/src:$PWD/jetson_ws/src/fab_virtual_lot:$ros_python_paths${PYTHONPATH:+:$PYTHONPATH}"
python_bin="${GATEWAY_PYTHON:-$HOME/posco-gateway-venv/bin/python}"
exec "$python_bin" scripts/mock_process_test.py "$@"
