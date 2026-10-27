# 서로게이트 ML WebSocket E2E 실행 가이드

## 1. 실제 통신 경로

```text
Unity
  -> Gateway WebSocket /api/v1/control
  -> PostgreSQL inference_jobs/inference_dispatches
  -> ROS 2 /fab/surrogate_requests
  -> Jetson fab_surrogate_worker
  -> HTTP POST <SURROGATE_URL>/api/v1/predict
  -> ROS 2 /fab/events (surrogate.completed)
  -> Gateway/Aiven events + surrogate_results
  -> Gateway WebSocket /api/v1/stream
  -> Unity
```

WebSocket은 Unity와 Gateway 사이에 사용한다. Jetson Worker와 ML 모델 사이에는
요청-응답형 HTTP를 사용한다. 실제 모델 서비스는 모델을 메모리에 상주 로드하고
`POST /api/v1/predict` 계약을 제공해야 한다.

## 2. IP 확인

Jetson과 WSL 주소는 재부팅이나 네트워크 변경 후 달라질 수 있다.

Jetson:

```bash
hostname -I
```

WSL:

```bash
hostname -I
```

주소가 바뀌면 `.env`, `config/dds/wsl-fastdds.xml`, Jetson의
`config/dds/jetson-fastdds.xml`을 먼저 맞춘다.

## 3. WSL 터미널 A: Gateway ROS bridge

```bash
cd /mnt/c/posco_project
source /opt/ros/humble/setup.bash
source "$HOME/posco-gateway-venv/bin/activate"

export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE=/mnt/c/posco_project/config/dds/wsl-fastdds.xml
unset FASTDDS_DEFAULT_PROFILES_FILE
export PYTHONPATH="$PWD/services/event_gateway/src:/opt/ros/humble/local/lib/python3.10/dist-packages:/opt/ros/humble/lib/python3.10/site-packages${PYTHONPATH:+:$PYTHONPATH}"

python -c 'import rclpy, std_msgs, psycopg; print("Gateway bridge dependencies OK")'
python -u -m event_gateway.ros_adapter
```

이 터미널은 계속 실행한다.

## 4. WSL 터미널 B: Gateway HTTP/WebSocket

```bash
cd /mnt/c/posco_project
source "$HOME/posco-gateway-venv/bin/activate"
export PYTHONPATH="$PWD/services/event_gateway/src${PYTHONPATH:+:$PYTHONPATH}"
python -u -m event_gateway.app
```

확인:

```bash
curl http://127.0.0.1:8000/health/live
```

정상 응답:

```json
{"status":"ok"}
```

Unity 접속 주소:

```text
ws://<GATEWAY_IP>:8000/api/v1/control
ws://<GATEWAY_IP>:8000/api/v1/stream?run_id=<RUN_ID>&after_sequence=0
```

## 5. Mock 시험일 때 WSL 터미널 C: Mock ML 서비스

실제 ML 서비스가 아직 없을 때만 실행한다.

```bash
cd /mnt/c/posco_project
source "$HOME/posco-gateway-venv/bin/activate"
export PYTHONPATH="$PWD/services/event_gateway/src${PYTHONPATH:+:$PYTHONPATH}"
export SURROGATE_BIND_HOST=0.0.0.0
export SURROGATE_BIND_PORT=8300
python -u -m mock_surrogate.app
```

WSL에서 확인:

```bash
curl http://127.0.0.1:8300/health/ready
```

Jetson에서도 반드시 확인한다.

```bash
curl http://<WSL_IP>:8300/health/ready
```

Jetson에서 연결되지 않으면 Windows/Hyper-V 방화벽에서 Jetson 주소에 대해 WSL TCP
8300 인바운드를 허용해야 한다. 실제 모델을 Jetson 로컬에서 실행할 때는 이 단계
대신 `SURROGATE_PROD_URL=http://127.0.0.1:<MODEL_PORT>`를 사용한다.

## 6. Jetson: 패키지 빌드와 executable 확인

Jetson 설정 전체를 변경하지 않고 해당 ROS 패키지만 빌드한다.

```bash
cd /home/jetson/project/smart_factory/jetson_ws
source /home/jetson/vision_env/bin/activate
source /opt/ros/humble/setup.bash

python3 -c 'import rclpy, std_msgs, httpx; print("Surrogate worker dependencies OK")'

colcon build \
  --symlink-install \
  --packages-select fab_virtual_lot \
  --build-base build_vision \
  --install-base install_vision

source install_vision/setup.bash
ros2 pkg executables fab_virtual_lot | grep fab_surrogate_worker
```

정상 결과:

```text
fab_virtual_lot fab_surrogate_worker
```

`httpx` import만 실패한 경우 `vision_env`에만 설치한다. 시스템 Python과 JetPack은
변경하지 않는다.

```bash
python3 -m pip install 'httpx>=0.27,<1'
```

## 7. Jetson: Mock Worker 실행

`<WSL_IP>`는 설명용 자리표시자이며 그대로 붙여넣으면 안 된다. 꺾쇠까지 입력하면
Bash가 `<WSL_IP>`를 입력 파일 리다이렉션으로 해석해 `No such file or directory`가
발생한다. 예를 들어 현재 WSL 주소가 `192.168.10.182`라면 아래처럼 실제 숫자만 쓴다.

```bash
cd /home/jetson/project/smart_factory
source /home/jetson/vision_env/bin/activate
source /opt/ros/humble/setup.bash
source jetson_ws/install_vision/setup.bash

export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE=/home/jetson/project/smart_factory/config/dds/jetson-fastdds.xml
unset FASTDDS_DEFAULT_PROFILES_FILE

export SURROGATE_MODE=mock
export SURROGATE_MOCK_URL=http://192.168.10.182:8300
export SURROGATE_TIMEOUT_SECONDS=15
export SURROGATE_RUNTIME_DB=/home/jetson/project/smart_factory/data/surrogate.sqlite
export ROS_SURROGATE_REQUEST_TOPIC=/fab/surrogate_requests
export ROS_EVENT_TOPIC=/fab/events
export ROS_EVENT_ACK_TOPIC=/fab/event_acks

export PYTHONPATH="/home/jetson/vision_env/lib/python3.10/site-packages:$PWD/jetson_ws/src/fab_virtual_lot${PYTHONPATH:+:$PYTHONPATH}"

/usr/bin/python3 -c 'import httpx; print("ros2 run interpreter can import httpx")'

ros2 run fab_virtual_lot fab_surrogate_worker
```

ROS console script는 빌드 당시 Python을 shebang에 고정한다. 기존 `install_vision`이
시스템 Python으로 빌드됐다면 `vision_env`를 활성화해도 `ros2 run`은
`/usr/bin/python3`로 실행될 수 있다. 위 PYTHONPATH는 시스템 Python에서도
`vision_env`의 `httpx`를 찾도록 한 현재 프로젝트용 호환 설정이다. 실제 shebang은
다음 명령으로 확인한다.

```bash
head -n 1 /home/jetson/project/smart_factory/jetson_ws/install_vision/fab_virtual_lot/lib/fab_virtual_lot/fab_surrogate_worker
```

`ros2 run`이 여전히 실패하면 활성화된 `vision_env` Python으로 동일한 ROS 노드를
직접 실행해 interpreter 문제를 우회한다.

```bash
/home/jetson/vision_env/bin/python3 -u -m fab_virtual_lot.surrogate_worker
```

## 8. 실제 ML 서비스 전환

Worker는 `.env` 파일을 자동으로 읽지 않고 시작 시점의 `os.environ`을 읽는다.
Jetson 프로젝트 루트의 `.env.surrogate-prod`에 실제 모델 설정을 보관하고 Worker
실행 직전에 source한다. `.env.*`는 Git에서 제외된다.

```bash
cd /home/jetson/project/smart_factory
nano .env.surrogate-prod
```

모델이 같은 Jetson에서 실행되는 예:

```dotenv
SURROGATE_MODE=prod
SURROGATE_PROD_URL=http://127.0.0.1:8300
SURROGATE_TIMEOUT_SECONDS=15
SURROGATE_RUNTIME_DB=/home/jetson/project/smart_factory/data/surrogate.sqlite
ROS_SURROGATE_REQUEST_TOPIC=/fab/surrogate_requests
ROS_EVENT_TOPIC=/fab/events
ROS_EVENT_ACK_TOPIC=/fab/event_acks
```

별도 모델 서버라면 `127.0.0.1` 대신 실제 모델 서버의 LAN 주소를 쓴다. 문서의
`<MODEL_HOST>`나 `<MODEL_PORT>` 같은 꺾쇠 자리표시자를 파일에 그대로 넣지 않는다.

```bash
chmod 600 .env.surrogate-prod
set -a
source .env
source .env.surrogate-prod
set +a
```

`.env`에도 동일 변수가 있으면 나중에 source한 `.env.surrogate-prod` 값이 우선한다.
값을 바꾼 뒤에는 Worker를 재시작해야 한다.

모델 팀 서비스가 `fab-ml-v1`의 `POST /api/v1/predict`를 구현한 뒤 실제 적용되는
값은 다음과 같다.

```bash
export SURROGATE_MODE=prod
export SURROGATE_PROD_URL=http://<MODEL_HOST>:<MODEL_PORT>
```

Mock URL로 실패를 숨기지 않는다. prod 모델 호출 실패 시 작업은 Jetson SQLite에
남고 재시도한다.

## 9. ROS 연결 확인

WSL 조회 터미널:

```bash
source /opt/ros/humble/setup.bash
export ROS_DOMAIN_ID=0
export ROS_LOCALHOST_ONLY=0
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export FASTRTPS_DEFAULT_PROFILES_FILE=/mnt/c/posco_project/config/dds/wsl-fastdds.xml
unset FASTDDS_DEFAULT_PROFILES_FILE

ros2 node list --no-daemon
ros2 topic info /fab/surrogate_requests --verbose --no-daemon
ros2 topic info /fab/events --verbose --no-daemon
ros2 topic info /fab/event_acks --verbose --no-daemon
```

정상 기준:

```text
/fab/surrogate_requests: Publisher 1, Subscription 1
/fab/events:             Publisher 1 이상, Subscription 1
/fab/event_acks:         Publisher 1, Subscription 1 이상
```

노드 목록에는 다음이 보여야 한다.

```text
/fab_gateway_bridge
/fab_surrogate_worker
```

## 10. Unity WebSocket 요청

연결 시 `X-Unity-Token` 헤더에 Gateway `.env`의 `UNITY_API_TOKEN`을 보낸다.

```text
ws://<GATEWAY_IP>:8000/api/v1/control
```

Mock 정상 시나리오:

```json
{
  "type": "surrogate.requested",
  "schema_version": 1,
  "request_id": "<NEW_UUID>",
  "run_id": "<NEW_UUID>",
  "lot_id": "LOT-001",
  "unit_id": "MOSFET-001",
  "stage_id": "electrical",
  "stage_attempt": 1,
  "model_contract_version": "fab-ml-v1",
  "input_payload": {"scenario": "normal"}
}
```

Mock 이상 시나리오는 `scenario`를 `anomaly`로 바꾼다. 각 시험에서
`request_id`와 `run_id`는 새 UUID를 사용한다.

접수 응답:

```json
{
  "type": "request.accepted",
  "request_id": "<REQUEST_UUID>",
  "job_id": "<JOB_UUID>",
  "status": "queued"
}
```

결과 구독:

```text
ws://<GATEWAY_IP>:8000/api/v1/stream?run_id=<동일_RUN_ID>&after_sequence=0
```

## 11. DB 검증

```sql
SELECT job_id, request_id, task_type, status, result_event_id, updated_at
FROM public.inference_jobs
WHERE task_type = 'surrogate'
ORDER BY created_at DESC
LIMIT 10;

SELECT sequence, event_id, event_type, source, payload, received_at
FROM public.events
WHERE event_type = 'surrogate.completed'
ORDER BY sequence DESC
LIMIT 10;

SELECT job_id, source_event_id, response_body, routing_status, proposal_id, created_at
FROM public.surrogate_results
ORDER BY created_at DESC
LIMIT 10;
```

정상 완료 시 `inference_jobs.status=completed`, `events.event_type=surrogate.completed`,
`surrogate_results` 신규 1건을 모두 확인해야 한다.

## 12. 자주 발생하는 오류

### `No executable found`

`install_vision` 빌드 또는 소싱이 누락됐다. 6단계를 다시 수행한다.

### `ModuleNotFoundError: httpx`

`httpx` 설치 여부가 아니라 `ros2 run` entrypoint와 설치한 Python이 다른 문제일 수
있다. `head -n 1 .../fab_surrogate_worker`로 shebang을 확인한다. `httpx`가
`vision_env`에 이미 있다면 7단계처럼 해당 site-packages를 PYTHONPATH에 포함하거나
`/home/jetson/vision_env/bin/python3 -m fab_virtual_lot.surrogate_worker`로 실행한다.

### `-bash: WSL_IP: No such file or directory`

문서의 `<WSL_IP>`를 그대로 붙여넣은 것이다. WSL의 `hostname -I` 결과 중 실제 LAN
주소로 전체 자리표시자를 교체한다. 예: `http://192.168.10.182:8300`.

### `model unavailable or invalid response`

Worker는 정상이나 `<SURROGATE_URL>/api/v1/predict`가 닿지 않거나 응답 계약이 다르다.
먼저 Jetson에서 `/health/ready`를 호출한다.

### `/fab/surrogate_requests`의 `Subscription count: 0`

Worker가 실행되지 않았거나 DDS 프로파일/도메인이 Gateway와 다르다.

### 요청은 accepted인데 결과가 없음

`inference_jobs`, Jetson `data/surrogate.sqlite`, ML 서비스 로그 순서로 확인한다.
요청은 유실되지 않고 Worker inbox에서 재시도된다.
