# WSL·Jetson 전체 스택 최종 실행 가이드

## 1. 목적과 실행 범위

이 문서는 Jetson이 재부팅되어 IP가 새로 할당된 상황에서 전체 스택을 기동하고
검증하는 절차다.

```text
IP 카메라 → Jetson Preview(:8500)·AOI(:8400)
          → Jetson AOI/서로게이트/진단 ROS Worker
          → ROS 2 DDS → WSL Gateway(:8000) → Aiven → Unity
          → 필요 시 TCAD HTTP 검증 → 관리자 승인 → Unity 보정 명령
```

자동 스크립트는 OS·네트워크 설정을 바꾸지 않는다. 현재 IP로 Fast DDS XML을
생성하고 자신이 시작한 프로세스만 PID 파일로 관리한다.

| 위치 | 구성요소 | 실행 방법 |
|---|---|---|
| Jetson | 실제 ML HTTP 서비스 `:8300` | 모델 팀 명령으로 별도 실행 |
| Jetson | 카메라 Preview `:8500` + AOI `:8400` | 별도 foreground 터미널 |
| Jetson | 서로게이트·진단 ROS Worker | `ros-stack-jetson.sh` |
| WSL | Gateway API/WebSocket + ROS Adapter + TCAD 검증 Worker | `ros-stack-wsl.sh` |

AOI와 ML HTTP 서비스는 모델·GPU 로그를 실시간 확인할 수 있도록 자동 스크립트의
백그라운드 프로세스와 분리한다.

## 2. 재부팅 후 IP 확인

WSL과 Jetson에서 각각 실행한다.

```bash
hostname -I
```

두 장비가 공유하는 LAN 대역 주소를 사용한다. `127.*`, `169.254.*`, Jetson USB
주소 `192.168.55.1`, Docker 주소 `172.17.*`는 사용하지 않는다.

예를 들어 WSL이 `192.168.10.182`, Jetson이 `192.168.10.224 192.168.55.1
172.17.0.1`이면 다음 주소만 사용한다.

```text
WSL_IP=192.168.10.182
JETSON_IP=192.168.10.224
```

이하 `<WSL_IP>`, `<JETSON_IP>`는 실제 숫자로 바꾼다. 꺾쇠를 그대로 입력하지 않는다.

## 3. 최초 1회 준비

### 3.1 WSL

```bash
cd /mnt/c/posco_project
chmod +x scripts/ros-stack-wsl.sh
```

`/mnt/c/posco_project/.env`에 다음 항목이 있어야 한다. 비밀값은 출력하거나 Git에
넣지 않는다.

```dotenv
DATABASE_URL=postgresql://...
UNITY_API_TOKEN=...
ROS_COMMAND_KEY=...
SURROGATE_MODE=prod
DIAGNOSIS_MODE=prod
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8000
```

### 3.2 Jetson에 자동화 파일 배치

WSL에서 현재 Jetson 주소로 복사한다.

```bash
cd /mnt/c/posco_project

scp scripts/ros-stack-jetson.sh \
  jetson@<JETSON_IP>:/home/jetson/project/smart_factory/scripts/

scp scripts/lib/ros-stack-common.sh \
  jetson@<JETSON_IP>:/home/jetson/project/smart_factory/scripts/lib/
```

Jetson에서:

```bash
cd /home/jetson/project/smart_factory
chmod +x scripts/ros-stack-jetson.sh
```

필수 파일:

```text
.env
.env.ml-prod
.env.camera-prod                 # 실제 카메라
.env.camera-mock                 # 저장 이미지 시험용
jetson_ws/install_vision/setup.bash
```

`.env.ml-prod` 핵심값:

```dotenv
SURROGATE_MODE=prod
SURROGATE_PROD_URL=http://127.0.0.1:8300
DIAGNOSIS_MODE=prod
DIAGNOSIS_PROD_URL=http://127.0.0.1:8300
ROS_SURROGATE_REQUEST_TOPIC=/fab/surrogate_requests
ROS_DIAGNOSIS_REQUEST_TOPIC=/fab/diagnosis_requests
ROS_EVENT_TOPIC=/fab/events
ROS_EVENT_ACK_TOPIC=/fab/event_acks
```

## 4. 전체 기동 순서

```text
① 실제 ML HTTP → ② AOI·카메라 → ③ Jetson ROS Worker
→ ④ WSL Gateway → ⑤ DDS·DB·Unity 검증
```

### 4.1 Jetson 터미널 A — 실제 ML HTTP 서비스

모델 팀이 제공한 실행 명령을 사용한다. 이미 떠 있다면 중복 실행하지 않는다.

```bash
curl -sS http://127.0.0.1:8300/health/ready | python3 -m json.tool
```

필수 판정:

```text
status = ready
result_origin = prod
service_version = 1.1.0 이상
surrogate_ready = true
diagnosis_ready = true
```

실제 추론 주소는 `POST /api/v1/predict`, `POST /api/v1/diagnose`다.

### 4.2 Jetson 터미널 B — AOI·카메라 서버

AOI는 `/home/jetson/vision_env/bin/python3`로 실행한다. 현재 Jetson 배포에서는
NumPy 1.26.4는 `.python-aoi`, Torch와 Ultralytics는 `~/.local`에 있으므로
`PYTHONNOUSERSITE=1`을 사용하지 않는다. 대신 `.python-aoi`를 `PYTHONPATH` 맨
앞에 두어 사용자 영역의 NumPy 2.x보다 우선한다.

```bash
/home/jetson/vision_env/bin/python3 -m pip install \
  'numpy==1.26.4' 'websockets>=13,<16'

unset PYTHONNOUSERSITE
export PYTHONPATH="$PWD/.python-aoi:$PWD/jetson_ws/src/fab_virtual_lot${PYTHONPATH:+:$PYTHONPATH}"
/home/jetson/vision_env/bin/python3 -c '
import cv2, numpy, torch, ultralytics, websockets
from websockets.sync.server import serve
print("AOI 의존성 정상", websockets.__version__)
'
```

위 설치는 최초 1회만 필요하다. 확인 명령이 모두 성공한 뒤 서버를 시작한다.
Jetson의 OpenCV가 NumPy 1.x ABI로 빌드되어 있으므로 이 가상환경에서는 NumPy
2.x로 올리지 않는다.

실제 카메라:

```bash
cd /home/jetson/project/smart_factory
source /home/jetson/vision_env/bin/activate
source /opt/ros/humble/setup.bash
source jetson_ws/install_vision/setup.bash

set -a
source .env
source .env.camera-prod
set +a

unset PYTHONNOUSERSITE
export PYTHONPATH="$PWD/.python-aoi:$PWD/jetson_ws/src/fab_virtual_lot${PYTHONPATH:+:$PYTHONPATH}"

/home/jetson/vision_env/bin/python3 -u -m fab_virtual_lot.aoi_unity
```

카메라 없이 저장 이미지로 시험할 때는 `.env.camera-prod` 대신
`.env.camera-mock`을 source한다.

정상 로그:

```text
AOI Unity WebSocket ready: ws://0.0.0.0:8400/aoi
Camera Preview WebSocket ready: ws://0.0.0.0:8500/camera/preview
```

포트 확인:

```bash
ss -ltnp | grep -E ':8300|:8400|:8500'
```

### 4.3 Jetson 터미널 C — 서로게이트·진단 ROS Worker

```bash
cd /home/jetson/project/smart_factory
./scripts/ros-stack-jetson.sh start --wsl-ip <WSL_IP>
```

이 명령은 Jetson LAN IP 선택, DDS XML 생성, 환경 로드, ML readiness 확인 후
`/fab_surrogate_worker`, `/fab_diagnosis_worker`를 병렬 실행한다.

```bash
./scripts/ros-stack-jetson.sh status
./scripts/ros-stack-jetson.sh check
./scripts/ros-stack-jetson.sh logs
```

`logs`에서 `Ctrl+C`를 눌러도 Worker는 종료되지 않는다.

### 4.4 WSL 터미널 A — Gateway 전체 실행

```bash
cd /mnt/c/posco_project
./scripts/ros-stack-wsl.sh start --jetson-ip <JETSON_IP>
```

다음 프로세스가 시작된다.

```text
gateway-api            HTTP/WebSocket :8000
gateway-ros            /fab_gateway_bridge
verification-worker    TCAD HTTP 검증 작업 처리
```

```bash
./scripts/ros-stack-wsl.sh status
./scripts/ros-stack-wsl.sh check
./scripts/ros-stack-wsl.sh logs
```

## 5. ROS·DDS 정상 판정

노드 목록:

```text
/fab_gateway_bridge
/fab_surrogate_worker
/fab_diagnosis_worker
/fab_aoi_unity_bridge           # AOI ROS 영속화 활성화 시
```

| 토픽 | Publisher | Subscription | 의미 |
|---|---:|---:|---|
| `/fab/surrogate_requests` | 1 이상 | 1 이상 | Gateway → 서로게이트 |
| `/fab/diagnosis_requests` | 1 이상 | 1 이상 | Gateway → 진단 |
| `/fab/events` | 1 이상 | 1 이상 | Jetson → Gateway/Aiven |
| `/fab/event_acks` | 1 이상 | 2 이상 | Gateway → Jetson ACK |

WSL 수동 확인:

```bash
cd /mnt/c/posco_project
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE="$PWD/data/ros-stack/wsl/wsl-fastdds.generated.xml"
unset FASTDDS_DEFAULT_PROFILES_FILE

ros2 node list --no-daemon
ros2 topic info /fab/events --verbose --no-daemon
ros2 topic info /fab/surrogate_requests --verbose --no-daemon
ros2 topic info /fab/diagnosis_requests --verbose --no-daemon
ros2 topic echo /fab/event_acks --no-daemon
```

IP 변경 뒤에는 기존 프로세스를 모두 재시작해야 새 DDS XML이 반영된다.

## 6. 기능별 E2E 시험

### 6.1 AOI Preview·검사

```bash
cd /mnt/c/posco_project
source "$HOME/posco-gateway-venv/bin/activate"

python tools/mock_unity/camera_aoi_flow_client.py \
  --preview-url ws://<JETSON_IP>:8500/camera/preview \
  --preview-token '<CAMERA_PREVIEW_TOKEN>' \
  --aoi-url ws://<JETSON_IP>:8400/aoi \
  --aoi-token '<AOI_UNITY_TOKEN>' \
  --camera-id aoi-camera-1 \
  --output-dir /mnt/c/posco_project/data/camera-aoi-flow-test \
  --timeout 180
```

정상 흐름은 Preview/JPEG → `frame_id` → AOI accepted/completed → annotated
JPEG → `/fab/events` → Aiven commit → `status=committed` ACK다.

### 6.2 실제 서로게이트 모델

WSL과 Jetson 모두 `SURROGATE_MODE=prod`여야 한다.

```bash
cd /mnt/c/posco_project
set -a; source .env; set +a

REQUEST_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
RUN_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')

curl -sS -X POST http://127.0.0.1:8000/api/v1/surrogate-jobs \
  -H 'Content-Type: application/json' \
  -H "X-Unity-Token: $UNITY_API_TOKEN" \
  -d "{\"schema_version\":1,\"request_id\":\"$REQUEST_ID\",\"run_id\":\"$RUN_ID\",\"lot_id\":\"LOT-SURROGATE-001\",\"unit_id\":\"MOSFET-001\",\"stage_id\":\"electrical\",\"stage_attempt\":1,\"model_contract_version\":\"fab-ml-v1\",\"input_payload\":{\"process_parameters\":{\"body_dose\":7.7e12,\"epi_doping\":1.7e16,\"oxide_thickness\":0.06},\"requested_outputs\":[\"vth\",\"gm\",\"id_on\",\"bv\"]}}"

echo "RUN_ID=$RUN_ID"
```

흐름: Gateway queued → ROS surrogate request → Jetson `POST :8300/api/v1/predict`
→ `surrogate.completed` → Aiven → committed ACK → Unity stream.

### 6.3 실제 진단 모델

```bash
REQUEST_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
RUN_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')

curl -sS -X POST http://127.0.0.1:8000/api/v1/diagnosis-jobs \
  -H 'Content-Type: application/json' \
  -H "X-Unity-Token: $UNITY_API_TOKEN" \
  -d "{\"schema_version\":1,\"request_id\":\"$REQUEST_ID\",\"run_id\":\"$RUN_ID\",\"lot_id\":\"LOT-DIAGNOSIS-001\",\"unit_id\":\"MOSFET-001\",\"stage_id\":\"diagnosis\",\"stage_attempt\":1,\"model_contract_version\":\"fab-ml-v1\",\"input_payload\":{\"measurements\":{\"vth\":2.1,\"gm\":10.0,\"id_on\":20.0,\"bv\":null},\"n_wafers\":1,\"refine\":false}}"

echo "RUN_ID=$RUN_ID"
```

흐름: Gateway queued → ROS diagnosis request → Jetson `POST :8300/api/v1/diagnose`
→ `diagnosis.completed` → Aiven → committed ACK → Unity stream.

`route=tcad_verify`는 자동 보정이 아니다. TCAD 검증 결과 저장과 관리자 승인 이후에만
Unity 보정 명령으로 진행한다.

## 7. Unity 연결

```text
중앙 요청: ws://<WSL_IP>:8000/api/v1/control
중앙 결과: ws://<WSL_IP>:8000/api/v1/stream?run_id=<RUN_ID>&after_sequence=0
보정 명령: ws://<WSL_IP>:8000/api/v1/commands?run_id=<RUN_ID>
Preview:   ws://<JETSON_IP>:8500/camera/preview
AOI:       ws://<JETSON_IP>:8400/aoi
```

`/control`, `/commands`는 `X-Unity-Token` 헤더가 필요하다. 결과 stream의 마지막
`sequence`를 저장하고 재접속 시 `after_sequence`로 사용한다.

Unity PC PowerShell:

```powershell
Test-NetConnection <WSL_IP> -Port 8000
Test-NetConnection <JETSON_IP> -Port 8400
Test-NetConnection <JETSON_IP> -Port 8500
```

## 8. DB 검증

```sql
SELECT job_id, task_type, status, result_event_id, updated_at
FROM public.inference_jobs ORDER BY updated_at DESC LIMIT 20;

SELECT sequence, event_type, source, payload, received_at
FROM public.events
WHERE event_type IN ('aoi.inspection.completed','surrogate.completed','diagnosis.completed')
ORDER BY received_at DESC LIMIT 20;

SELECT job_id, response_body->>'result_origin' AS result_origin,
       response_body->>'model_version' AS model_version,
       response_body->>'status' AS status, created_at
FROM public.surrogate_results ORDER BY created_at DESC LIMIT 10;

SELECT job_id, response_body, compensation_route, routing_status, created_at
FROM public.diagnosis_results ORDER BY created_at DESC LIMIT 10;

SELECT job_id, task_type, model_name, model_version,
       inference_duration_ms, service_duration_ms, status, completed_at
FROM public.ml_inference_executions ORDER BY completed_at DESC LIMIT 20;
```

실제 모델 성공 판정은 `result_origin=prod`, `status=succeeded`다.

## 9. 로그·종료

```bash
# Jetson Worker
./scripts/ros-stack-jetson.sh status
./scripts/ros-stack-jetson.sh logs

# WSL Gateway
./scripts/ros-stack-wsl.sh status
./scripts/ros-stack-wsl.sh logs
```

AOI는 Jetson 터미널 B, ML HTTP는 터미널 A에서 로그를 본다. 연속 영상은 디스크에
저장하지 않고 RAM Ring Buffer를 사용하며 요청 원본과 annotated 결과만 저장한다.

종료:

```bash
# WSL
./scripts/ros-stack-wsl.sh stop

# Jetson
./scripts/ros-stack-jetson.sh stop
```

AOI와 ML HTTP는 해당 foreground 터미널에서 `Ctrl+C`로 종료한다.

## 10. IP가 다시 바뀌었을 때

1. WSL·Jetson 자동 스택 `stop`
2. AOI 종료
3. 양쪽 `hostname -I`
4. Jetson Worker를 새 `<WSL_IP>`로 `start`
5. WSL Gateway를 새 `<JETSON_IP>`로 `start`
6. AOI 재시작
7. 양쪽 `check`

자동 실행에서는 `config/dds/*.xml`을 사용하지 않고 다음 파일을 매번 생성한다.

```text
Jetson: data/ros-stack/jetson/jetson-fastdds.generated.xml
WSL:    data/ros-stack/wsl/wsl-fastdds.generated.xml
```

## 11. 배포 전 검증

### 실제 Ubuntu WSL dry-run

```bash
FAB_RUNTIME_DIR=/tmp/fab-wsl-dry FAB_HOST_IPS='<WSL_IP>' \
  bash scripts/ros-stack-wsl.sh start --jetson-ip <JETSON_IP> --dry-run

FAB_RUNTIME_DIR=/tmp/fab-jetson-dry \
FAB_HOST_IPS='<JETSON_IP> 192.168.55.1 172.17.0.1' \
  bash scripts/ros-stack-jetson.sh start --wsl-ip <WSL_IP> --dry-run
```

### Gateway 전체 단위 테스트

```bash
source "$HOME/posco-gateway-venv/bin/activate"
python -m pytest services/event_gateway/tests/unit -q \
  --basetemp=/tmp/pytest-ros-stack-suite
```

### Bash 구문 검사

```bash
bash -n scripts/lib/ros-stack-common.sh \
  scripts/ros-stack-wsl.sh scripts/ros-stack-jetson.sh
```

### DDS XML 검사

```bash
python3 - <<'PY'
import xml.etree.ElementTree as ET
ET.parse('/tmp/fab-wsl-dry/wsl-fastdds.generated.xml')
ET.parse('/tmp/fab-jetson-dry/jetson-fastdds.generated.xml')
print('DDS XML 검사 통과')
PY
```

최종 판정은 위 네 검증이 exit code `0`이고, 실제 E2E에서 Aiven 결과가
`result_origin=prod`, `status=succeeded`, ROS ACK가 `committed`일 때다.

### 2026-10-21 검증 기록

- 실제 Ubuntu WSL 양쪽 dry-run: 통과
- Gateway 전체 단위 테스트: `57 passed`
- Bash 구문 검사: 통과
- 생성된 WSL·Jetson DDS XML 파싱: `DDS_XML_VALID`
- 참고: 단위 테스트에는 `httpx`/Starlette deprecation warning 1건이 있으나 실패는
  없었다.
