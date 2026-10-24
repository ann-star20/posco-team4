# WSL 한 PC AOI·ROS·Aiven·Unity 스트림 직접 시험

2026-10-17 주의: 이 환경에서 ROS 요청 발견 지연이 관측됐다. 작업이 queued로 오래 남을 때 신규 요청을 반복 생성하지 말고 [지연 점검 및 전체 구현 상태](integration-status-and-latency.md)를 확인한다. 이 가이드는 AOI 경로이며 전기적 ML→TCAD→Unity 적용 전체 시험을 뜻하지 않는다.

현재 실행 가능 범위: `CAMERA_MODE=mock`은 저장된 원본 사진을 카메라 프레임 대신 사용한다. `AOI_MODE=prod`는 WSL CPU에서 실제 부품·결함 `best.pt`를 실행한다. Jetson 접속은 필요 없다. Unity 앱 대신 Gateway HTTP/WebSocket 시험 클라이언트를 사용한다. 실제 IP 카메라는 아직 연결하지 않는다.

실제 경로: **시험 클라이언트 → Gateway HTTP `/api/v1/inspection-jobs` → Aiven 작업/발행 대기 → Gateway ROS `/fab/inference_requests` 발행 → WSL AOI Worker 구독 → 이미지 2단계 추론 및 `result` JPG 저장 → Worker ROS `/fab/events` 발행 → Gateway 구독/Aiven 이벤트·이미지 메타데이터 저장 → Gateway `/fab/event_acks` 발행 → Worker가 SQLite outbox 완료 표시 → Gateway WebSocket `/api/v1/stream`으로 결과 표시**. Gateway는 `/fab/events`의 구독자이고, AOI Worker는 `/fab/inference_requests`의 구독자다. ROS DDS 발견에는 수 초가 걸릴 수 있다.

## 준비

- WSL Ubuntu 22.04, ROS 2 Humble, `/home/user/posco-gateway-venv`.
- 이 PC의 `.env`에는 Aiven 연결과 `AOI_*`, `CAMERA_FIXTURE_PATH`가 있다. 비밀번호·URL을 출력하지 않는다.
- 모델: `jetson_ws/models/mosfet_part_v5-26/weights/best.pt` 및 결함 모델의 같은 위치.
- 원본 시험 이미지: `jetson_ws/images/`. 기본 `.env`는 `mosfet_fail_scratch_bend (9).png`.
- `.env`의 `AOI_IMAGE_DIR`은 WSL에서 `/mnt/c/posco_project/jetson_ws/images`이며, HTTP 요청의 `fixture_name`으로 이 폴더의 한 파일을 선택할 수 있다. 생략 시 `CAMERA_FIXTURE_PATH`를 읽는다. 경로가 아닌 파일명만 허용한다.
- WSL venv에 OpenCV, torch CPU, torchvision CPU, ultralytics가 설치되어 있어야 한다. 실모델을 실행할 수 없다면 `AOI_MODE=mock`만 선택한다. prod 오류를 mock 성공으로 대체하지 않는다.
- 동일 역할의 Gateway 브리지·AOI Worker·Gateway API가 이미 실행 중이면 중복 실행하지 않는다.

아래 모든 명령은 **서로 다른 WSL 터미널**에서 실행한다. 세 터미널 모두 시작 위치는 동일하다. `${PYTHONPATH}`를 PowerShell이 해석하는 문제가 있으므로 명령은 WSL Bash 안에 직접 입력한다.

## A — Gateway ROS 브리지

```bash
cd /mnt/c/posco_project
export PYTHONPATH="$PWD/services/event_gateway/src"
source /opt/ros/humble/setup.bash
source "$HOME/posco-gateway-venv/bin/activate"
python -c 'import rclpy, psycopg; print("ROS/DB import OK")'
python -m event_gateway.ros_adapter
```

## B — WSL을 Jetson으로 실행

```bash
cd /mnt/c/posco_project
export PYTHONPATH="$PWD/jetson_ws/src/fab_virtual_lot"
source /opt/ros/humble/setup.bash
source "$HOME/posco-gateway-venv/bin/activate"
set -a
source .env
set +a
python -c 'from fab_virtual_lot.aoi_worker import main; print("AOI Worker import OK")'
python -m fab_virtual_lot.aoi_worker
```

`.env`의 `AOI_PART_MODEL_FILE`, `AOI_DEFECT_MODEL_FILE`, `CAMERA_FIXTURE_PATH`, `AOI_RESULT_DIR`는 WSL에서 읽히는 경로다. 실제 Jetson에 배포할 때는 Jetson 측 `.env`에 `/home/jetson/project/smart_factory/...` 경로를 설정한다. 운영 카메라를 연결하기 전에는 `CAMERA_MODE=mock`을 유지한다. 임계값은 `AOI_PART_CONF_THRESHOLD`, `AOI_DEFECT_CONF_THRESHOLD`, `AOI_PART_IOU_THRESHOLD`, `AOI_DEFECT_IOU_THRESHOLD`로 지정한다. Worker 재시작 후 새 요청에 반영된다.

## C — Gateway HTTP/Unity WebSocket

```bash
cd /mnt/c/posco_project
export PYTHONPATH="$PWD/services/event_gateway/src"
source "$HOME/posco-gateway-venv/bin/activate"
python -m event_gateway.app
```

## D — Gateway를 통해 AOI 작업 한 건 접수 (권장)

새 WSL 터미널에서 아래를 실행한다. 토큰 자체를 출력하지 않고 `.env`에서 읽는다. `fixture_name`은 실제 `jetson_ws/images`에 있는 원본 파일명으로 바꿀 수 있다. `run_id`, `request_id`는 요청당 새 UUID다.

```bash
cd /mnt/c/posco_project
export PYTHONPATH="$PWD/services/event_gateway/src"
source "$HOME/posco-gateway-venv/bin/activate"
python - <<'PY'
from pathlib import Path
from uuid import uuid4
import os, time, httpx
from event_gateway.config import Settings

settings = Settings.load(Path('.env'))
request = {'request_id': str(uuid4()), 'run_id': str(uuid4()),
           'lot_id': 'WSL-AOI-TEST', 'unit_id': 'MOSFET-1',
           'stage_id': 'final_aoi', 'stage_attempt': 1,
           'fixture_name': 'mosfet_fail_scratch_bend (9).png'}
headers = {'x-unity-token': settings.unity_api_token}
base = f'http://127.0.0.1:{settings.gateway_port}'
with httpx.Client(timeout=10) as client:
    response = client.post(base + '/api/v1/inspection-jobs', json=request, headers=headers)
    response.raise_for_status()
    job_id = response.json()['job_id']
    print('run_id:', request['run_id'], 'job_id:', job_id)
    for _ in range(90):
        state = client.get(base + '/api/v1/inspection-jobs/' + job_id, headers=headers)
        state.raise_for_status()
        if state.json()['status'] in ('completed', 'failed'):
            print(state.json()['status'] + ':', state.json()['result_event_id'])
            break
        time.sleep(2)
    else:
        print('timeout:', state.json())
PY
```

`completed`가 뜬 경우에만 아래 JPG/DB/ACK 검증으로 간다. 여러 공정 요청은 각기 다른 `unit_id`로 병행할 수 있다. 동일 `run_id`·`unit_id`·`stage_id`에서 미완료 작업이 있으면 HTTP 409가 정상이며, 동일 `request_id`·동일 본문 재전송은 기존 작업 ID를 돌려준다.

존재하지 않는 `fixture_name`이면 Worker가 `aoi.inspection.failed` 이벤트(`error_code=image_unreadable`)를 보내고 작업은 `failed`로 끝난다. 이 경우 JPG가 없는 것이 정상이다. `fixture_name`에 디렉터리 이동(`../`)을 넣으면 Gateway가 HTTP 422로 거부한다.

## D-2 — Gateway 입구를 건너뛰는 ROS 진단 요청 (선택)

```bash
cd /mnt/c/posco_project
export PYTHONPATH="$PWD/jetson_ws/src/fab_virtual_lot"
source /opt/ros/humble/setup.bash
source "$HOME/posco-gateway-venv/bin/activate"
python -m fab_virtual_lot.aoi_request --lot-id WSL-AOI-TEST
```

CLI는 Gateway의 작업 접수·발행 대기를 우회한다. 따라서 `/fab/inference_requests` → Worker → `/fab/events` → Gateway 저장/ACK를 분리 진단할 때만 사용한다. CLI가 출력한 `run_id`와 `job_id`를 기록한다. 같은 요청을 시험하려면 CLI를 다시 실행하지 않는다(새 ID가 생성됨). 중복·ACK 검증은 Worker의 SQLite와 Aiven 이벤트를 대조한다.

```bash
cd /mnt/c/posco_project
export PYTHONPATH="$PWD/services/event_gateway/src"
source "$HOME/posco-gateway-venv/bin/activate"
python -m event_gateway.communication_check gateway --run-id '<출력된 run_id>'
```

`status=matched`면 Aiven 이벤트 HTTP 조회와 실제 Unity WebSocket 재생이 일치한다. 사진 바이너리를 WebSocket에 넣은 것이 아니라 이미지 메타데이터를 결과 이벤트에 담는다.

JPG/JSON 확인:

```bash
ls -lh "jetson_ws/result/aoi/<출력된 job_id>/1/"
```

`original.jpg`, `annotated.jpg`, `result.json`이 있어야 한다. DB에 기록된 `local_directory`와 `file_name`은 WSL 시험 경로다. 이 경로는 Unity에서 직접 열 수 있는 URL이 아니다. 원격 Jetson 이미지 조회 API는 아직 구현 대상이다.

DB와 ACK는 비밀 URL을 출력하지 않는 Python으로 조회한다.

```bash
cd /mnt/c/posco_project
export PYTHONPATH="$PWD/services/event_gateway/src"
source "$HOME/posco-gateway-venv/bin/activate"
python - <<'PY'
from pathlib import Path
from uuid import UUID
import psycopg
from event_gateway.config import Settings
run_id = UUID(input('run_id: ').strip())
with psycopg.connect(Settings.load(Path('.env')).database_url) as db:
    for row in db.execute("SELECT event_id, sequence, payload->>'verdict', jsonb_array_length(payload->'detections') FROM events WHERE run_id=%s AND event_type='aoi.inspection.completed' ORDER BY sequence", (run_id,)):
        print('event:', row)
    for row in db.execute("SELECT image_role, local_directory, file_name, sha256, cloud_status FROM aoi_image_artifacts WHERE job_id IN (SELECT (payload->>'job_id')::uuid FROM events WHERE run_id=%s AND event_type='aoi.inspection.completed') ORDER BY image_role", (run_id,)):
        print('image:', row)
PY
```

```bash
python - <<'PY'
import sqlite3
with sqlite3.connect('jetson_ws/result/aoi.sqlite') as db:
    print(db.execute('SELECT event_id, delivered_sequence FROM pending ORDER BY rowid DESC LIMIT 5').fetchall())
PY
```

`delivered_sequence`가 양수면 해당 event의 Aiven 커밋 ACK를 Worker가 처리했다는 뜻이다. 0/NULL이면 아직 미확인, -1은 영속 격리다.

## 2026-10-16 실측 결과

WSL 원본 `mosfet_fail_scratch_bend (9).png`, 두 실제 best.pt, CPU 실행에서 `body/lead/tab` 5개와 `bend/crash` 2개를 탐지했다. 시험 `run_id=7d675e52-5473-49bd-bac4-3279690177b5`, `job_id=c4d8f9d1-90e9-4993-b34a-68e9266d45de`에 대해 Aiven `events.sequence=11`, 이미지 메타데이터 2건, SQLite ACK sequence=11, WebSocket `status=matched`를 확인했다. 정확도·실카메라 안정성 검증 결과는 아니다.

Gateway HTTP 접수와 ROS 디스패치를 거쳐 `fixture_name=test_aoi_mosfet1.jpg`를 선택한 시험도 완료했다. `run_id=a5426c5a-0dd1-431f-b1bc-d61348009ea6`, `job_id=4e8efa21-5743-4349-bf71-a49bee37b2d8`, `events.sequence=13`, 결함 판정 `fail`, 탐지 5개, Aiven 이미지 메타데이터 2건, 실제 JPG 2개, Worker ACK sequence=13, HTTP/WebSocket `status=matched`를 확인했다. 결과 이미지는 `jetson_ws/result/aoi/4e8efa21-5743-4349-bf71-a49bee37b2d8/1/annotated.jpg`에 있다.
