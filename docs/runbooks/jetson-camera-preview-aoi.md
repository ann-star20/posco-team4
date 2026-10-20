# Jetson 카메라 Preview와 AOI 적용·시험 절차

이 문서는 Jetson이 IP 카메라를 한 번 연결해 RAM Ring Buffer를 유지하고, Unity가 Preview의 `frame_id`를 골라 AOI를 요청하는 현재 구현 기준이다. Jetson 시스템 설정은 바꾸지 않으며 프로젝트 코드, 프로젝트 전용 `.env`, ROS 2 package만 갱신한다.

## 1. 보안과 적용 전 확인

- 채팅에 노출된 카메라 비밀번호는 실제 연동 전에 반드시 변경한다.
- 계정과 비밀번호를 URL, Git, 화면 캡처, 로그에 넣지 않는다.
- 실제 값은 Jetson의 `/home/jetson/project/smart_factory/.env.camera-prod`에만 저장하고 `chmod 600`을 적용한다.
- 백업은 필수가 아니다. Jetson에 직접 수정한 미커밋 코드가 있을 때만 해당 프로젝트를 별도 보관한다. OS, JetPack, ROS 설정은 수정하지 않는다.

Jetson에서 기존 변경을 먼저 확인한다.

```bash
cd /home/jetson/project/smart_factory
git status --short
```

직접 수정한 파일이 없다면 WSL에서 먼저 dry-run하고 코드만 복사한다.

```bash
rsync -avn --exclude build --exclude install --exclude log \
  /mnt/c/posco_project/jetson_ws/src/ \
  jetson@<JETSON_IP>:/home/jetson/project/smart_factory/jetson_ws/src/
```

목록이 맞으면 `-n`만 제거해 실행한다. Jetson에 직접 수정한 파일이 있으면 덮어쓰기 전에 커밋하거나 그 파일만 복사해 보관한다.

## 2. 환경변수 작성

### Mock 카메라

카메라 없이 저장된 이미지로 Preview·AOI·ROS 영속화를 함께 시험한다.

```bash
cd /home/jetson/project/smart_factory
nano .env.camera-mock
chmod 600 .env.camera-mock
```

```dotenv
CAMERA_MODE=mock
CAMERA_ID=aoi-camera-1
CAMERA_FIXTURE_PATH=/home/jetson/project/smart_factory/jetson_ws/images/test_aoi_mosfet1.jpg
CAMERA_CAPTURE_FPS=10
CAMERA_RING_BUFFER_SECONDS=2
CAMERA_RING_BUFFER_MAX_MB=128
CAMERA_PREVIEW_HOST=0.0.0.0
CAMERA_PREVIEW_PORT=8500
CAMERA_PREVIEW_WIDTH=1280
CAMERA_PREVIEW_HEIGHT=720
CAMERA_PREVIEW_FPS=5
CAMERA_PREVIEW_JPEG_QUALITY=75
CAMERA_PREVIEW_MAX_CLIENTS=2
CAMERA_PREVIEW_TOKEN=<별도-시험-토큰>
AOI_UNITY_WS_HOST=0.0.0.0
AOI_UNITY_WS_PORT=8400
AOI_UNITY_TOKEN=<별도-AOI-토큰>
AOI_QUEUE_SIZE=10
AOI_EXECUTOR_WORKERS=1
AOI_COMPLETION_WAIT_SECONDS=30
AOI_FRAME_SPOOL_DIR=/home/jetson/project/smart_factory/result/aoi-frame-spool
AOI_RESULT_DIR=/home/jetson/project/smart_factory/result/aoi
AOI_RUNTIME_DB=/home/jetson/project/smart_factory/result/aoi.sqlite
AOI_ROS_PERSISTENCE_ENABLED=true
```

기존 AOI 모델 경로, 임계값, ROS topic, `DATABASE_URL`은 현재 프로젝트 `.env` 값을 유지한다.

### 실제 IP 카메라

Mock 파일을 복사하고 아래 항목만 바꾼다. HTTPS가 정상 인증서를 제공하면 HTTPS를 우선 사용한다. 사설 인증서라면 `CAMERA_TLS_CA_FILE`에 CA 파일을 지정한다. HTTP는 명시적으로 허용해야만 열린다.

```dotenv
CAMERA_MODE=prod
CAMERA_SOURCE_URL=https://192.168.10.111:8080
CAMERA_AUTH_MODE=basic
CAMERA_USERNAME=<카메라-계정>
CAMERA_PASSWORD=<변경한-카메라-비밀번호>
CAMERA_TLS_VERIFY=true
CAMERA_TLS_CA_FILE=
CAMERA_ALLOW_HTTP=false
CAMERA_CONNECT_TIMEOUT_SECONDS=5
CAMERA_READ_TIMEOUT_SECONDS=5
CAMERA_RECONNECT_INTERVAL_SECONDS=3
```

HTTPS를 사용할 수 없어 내부망 HTTP를 시험할 때만 다음 두 값을 사용한다.

```dotenv
CAMERA_SOURCE_URL=http://192.168.10.111:8080
CAMERA_ALLOW_HTTP=true
```

## 3. Jetson 빌드와 서버 실행

의존성을 확인하고 ROS package를 증분 빌드한다.

```bash
cd /home/jetson/project/smart_factory/jetson_ws
source /opt/ros/humble/setup.bash
python3 -c 'import cv2, numpy, ultralytics; from websockets.sync.server import serve; print("카메라 의존성 확인")'
colcon build --packages-select fab_virtual_lot --symlink-install
source install/setup.bash
ros2 pkg executables fab_virtual_lot
```

`websockets.sync`를 찾지 못하면 Ubuntu 기본 패키지가 너무 오래된 것이다. 시스템 Python을 교체하지 말고 Jetson 사용자 영역에 프로젝트 요구 버전만 설치한 뒤 위 확인 명령을 다시 실행한다.

```bash
python3 -m pip install --user 'websockets>=13,<16'
```

서버는 Jetson에서 실행한다. 하나의 명령이 카메라 capture, Preview `8500`, AOI `8400`, AOI outbox를 함께 시작한다.

```bash
cd /home/jetson/project/smart_factory
source /opt/ros/humble/setup.bash
source jetson_ws/install/setup.bash
set -a
source .env
source .env.camera-mock  # 실제 카메라는 .env.camera-prod
set +a
ros2 run fab_virtual_lot fab_aoi_unity_server
```

다른 Jetson 터미널에서 listen 상태를 확인한다.

```bash
ss -ltnp | grep -E ':8400|:8500'
```

## 4. Unity 없이 WSL에서 사전 시험

WSL의 `<JETSON_IP>`와 토큰을 실제 값으로 바꾼다. Preview 한 장을 받고 출력 JSON의 `frame_id`를 기록한다.

Ring Buffer의 기본 보존 시간은 2초이므로 권장 방법은 아래 통합 클라이언트다. Preview에서 받은 `frame_id`를 복사하지 않고 즉시 AOI 요청에 사용한다.

```bash
python tools/mock_unity/camera_aoi_flow_client.py \
  --preview-url ws://<JETSON_IP>:8500/camera/preview \
  --preview-token '<CAMERA_PREVIEW_TOKEN>' \
  --aoi-url ws://<JETSON_IP>:8400/aoi \
  --aoi-token '<AOI_UNITY_TOKEN>' \
  --camera-id aoi-camera-1 \
  --output-dir /mnt/c/posco_project/data/camera-aoi-flow-test \
  --timeout 180
```

Preview와 AOI를 각각 확인해야 할 때만 다음 두 단계 명령을 사용한다. 이 경우 Preview 출력 후 2초 안에 AOI 요청을 보내야 하며 `frame_id`를 그대로 입력해야 한다.

```bash
cd /mnt/c/posco_project
source "$HOME/posco-gateway-venv/bin/activate"
python tools/mock_unity/camera_preview_client.py \
  --url ws://<JETSON_IP>:8500/camera/preview \
  --token '<CAMERA_PREVIEW_TOKEN>' \
  --camera-id aoi-camera-1 \
  --output /mnt/c/posco_project/data/camera-preview/latest.jpg
```

그 `frame_id`로 AOI를 요청한다.

```bash
python tools/mock_unity/aoi_frame_client.py \
  --url ws://<JETSON_IP>:8400/aoi \
  --token '<AOI_UNITY_TOKEN>' \
  --camera-id aoi-camera-1 \
  --frame-id <PREVIEW_FRAME_ID> \
  --output-dir /mnt/c/posco_project/data/aoi-frame-test
```

정상 결과는 `accepted` 후 `completed`, annotated JPG 저장이다. 너무 오래된 frame은 `stale_frame`, 큐가 가득 차면 `queue_full`로 거부된다.

## 5. Gateway·Aiven 영속화 확인

WSL Gateway를 먼저 실행한다.

```bash
cd /mnt/c/posco_project
source /opt/ros/humble/setup.bash
source "$HOME/posco-gateway-venv/bin/activate"
set -a
source .env
set +a
export PYTHONPATH="$PWD/services/event_gateway/src${PYTHONPATH:+:$PYTHONPATH}"
python -m event_gateway.ros_adapter
```

별도 WSL 터미널에서 ACK를 확인한다.

```bash
source /opt/ros/humble/setup.bash
ros2 topic echo /fab/event_acks
```

AOI 완료 뒤 `status: committed`가 보이면 Gateway가 Aiven transaction을 commit한 것이다. Unity WebSocket 완료는 화면 전달 성공일 뿐 DB commit을 뜻하지 않는다. 자세한 DB 조회는 [`manual-ros2-aiven-check.md`](manual-ros2-aiven-check.md)를 따른다.

## 6. Unity 담당자에게 전달할 계약

- Preview URL: `ws://<JETSON_IP>:8500/camera/preview`
- AOI URL: `ws://<JETSON_IP>:8400/aoi`
- 중앙 이벤트·승인·보정 URL: `ws://<GATEWAY_IP>:8000/api/v1/...`
- Preview 구독 후 JSON metadata와 JPEG binary가 한 쌍으로 반복된다.
- AOI 요청에는 사용자가 화면에서 고른 `camera_id`, `frame_id`를 넣는다.
- AOI 응답 순서는 `aoi.inspection.accepted` → `aoi.inspection.completed` → annotated JPEG binary다.
- 정확한 JSON 필드는 [`../api/asyncapi.yaml`](../api/asyncapi.yaml)을 사용한다.

## 7. 운영 관찰과 중지

RAM과 발열은 저장 없이 관찰한다.

```bash
free -h
tegrastats
```

Preview는 최신 frame만 유지하고 디스크에 저장하지 않는다. AOI가 접수된 frame과 결과만 `AOI_FRAME_SPOOL_DIR`, `AOI_RESULT_DIR`, SQLite outbox에 남는다. 중지는 실행 터미널에서 `Ctrl+C`로 한다. 문제가 있으면 이전 코드와 `.env`로 되돌려 다시 빌드하면 되며 Jetson OS 설정을 복원할 작업은 없다.
