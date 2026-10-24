#!/usr/bin/env bash
set -eo pipefail
cd "$(dirname "$0")/.."
set -a
source config/aoi-unity-test.env
set +a
set -u
python_bin="${GATEWAY_PYTHON:-$HOME/posco-gateway-venv/bin/python}"
export PYTHONPATH="$PWD/jetson_ws/src/fab_virtual_lot${PYTHONPATH:+:$PYTHONPATH}"
server_pid=""
cleanup() {
  if [[ -n "$server_pid" ]]; then kill "$server_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM
"$python_bin" -m fab_virtual_lot.aoi_unity &
server_pid=$!
"$python_bin" tools/mock_unity/aoi_client.py \
  --url "ws://127.0.0.1:${AOI_UNITY_WS_PORT}/aoi" \
  --token "$AOI_UNITY_TOKEN" \
  --fixture "$AOI_UNITY_TEST_FIXTURE" \
  --output-dir "$AOI_UNITY_TEST_OUTPUT" \
  --max-image-bytes "$AOI_UNITY_MAX_IMAGE_BYTES" \
  --timeout 180
