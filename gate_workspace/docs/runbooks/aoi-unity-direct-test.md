# AOI 테스트 JPG → Unity 직접 WebSocket 시험

기준: 2026-10-19. 이 시험은 기존 ROS/Gateway/Aiven 전체 E2E를 대체하지 않는다. Jetson 역할 프로세스가 AOI 결과를 Unity 화면에 빠르게 전달하는 추가 경로만 검증한다.

## 1. 한 번에 실행

WSL Ubuntu-22.04에서:

```bash
cd /mnt/c/posco_project
bash scripts/run-aoi-unity-test.sh
```

전용 설정은 `config/aoi-unity-test.env`다. 기존 `.env`를 읽거나 수정하지 않는다. 기본 시험은 다음 자원을 사용한다.

- 입력: `jetson_ws/images/test_aoi_mosfet1.jpg`
- 부품 모델: `jetson_ws/models/mosfet_part_v5-26/weights/best.pt`
- 결함 모델: `jetson_ws/models/mosfet_defect_v5-26/weights/best.pt`
- Jetson 역할 WS: `ws://127.0.0.1:8400/aoi`
- mock Unity 수신 결과: `data/aoi-unity-test/unity_<job_id>.jpg/.json`

성공 출력 예:

```text
{"status":"passed","verdict":"fail","parts":4,"defects":1,"annotated_image":"...jpg"}
```

`result_origin`을 반드시 확인한다. `prod`는 실제 두 모델의 추론 결과이고,
`mock`은 통신 검사용 합성 탐지다. Mock 박스는 입력 해상도에 비례해 중앙 시험
영역에 표시되지만 실제 부품이나 결함을 탐지한 결과가 아니다. 모델 정확도나 좌표를
확인하는 시험에서는 반드시 `AOI_MODE=prod`를 사용한다.

받은 JPG에는 부품 탐지 영역을 파란 계열 사각형, 결함 탐지 영역을 빨간 사각형으로 표시한다. 각 사각형 상단에는 `body 0.98`, `lead 0.94`, `crash 0.87`처럼 클래스와 confidence를 표시한다. 원본 해상도에 비례해 글꼴과 선 두께를 조절한다.

## 2. Unity가 보내는 요청

Unity는 연결 후 JSON text frame 하나를 보낸다.

```json
{
  "type": "aoi.inspection.requested",
  "schema_version": 1,
  "request_id": "UUID",
  "job_id": "UUID",
  "run_id": "UUID",
  "lot_id": "LOT-001",
  "unit_id": "MOSFET-001",
  "attempt": 1,
  "fixture_name": "test_aoi_mosfet1.jpg",
  "api_token": "환경변수 AOI_UNITY_TOKEN 값"
}
```

실카메라 연동 전이므로 `fixture_name`은 `AOI_IMAGE_DIR` 바로 아래의 파일명만 허용한다. 경로 문자열은 허용하지 않는다.

## 3. Jetson이 Unity에 보내는 데이터

첫 번째 frame은 JSON text다.

```json
{
  "type": "aoi.inspection.completed",
  "schema_version": 1,
  "message_id": "UUID",
  "request_id": "UUID",
  "job_id": "UUID",
  "run_id": "UUID",
  "lot_id": "LOT-001",
  "unit_id": "MOSFET-001",
  "attempt": 1,
  "device_id": "jetson-1",
  "result_origin": "prod",
  "verdict": "fail",
  "defect_detected": true,
  "processing_ms": 123.456,
  "thresholds": {},
  "parts": [
    {"class_id": 0, "class_name": "body", "confidence": 0.98,
     "bbox_xyxy": [542.0, 814.0, 851.0, 1134.0]}
  ],
  "defects": [
    {"class_id": 0, "class_name": "crash", "confidence": 0.87,
     "bbox_xyxy": [555.0, 874.0, 844.0, 1028.0]}
  ],
  "image": {
    "image_id": "UUID",
    "frame_role": "annotated",
    "mime_type": "image/jpeg",
    "file_name": "annotated.jpg",
    "byte_length": 1300115,
    "sha256": "...",
    "width": 3024,
    "height": 4032,
    "jetson_path": ".../result/.../annotated.jpg",
    "binary_frame_follows": true
  }
}
```

두 번째 frame은 위 `sha256`과 `byte_length`가 일치하는 annotated JPEG binary다. Unity에서는 JSON을 받은 뒤 바로 다음 binary frame을 `Texture2D.LoadImage` 등에 전달한다. 좌표는 원본 이미지 픽셀 기준 `x1,y1,x2,y2`다. Unity 화면에서 이미지를 리사이즈한다면 같은 비율로 좌표를 변환한다.

기본 최대 frame 크기는 8 MiB이며 `AOI_UNITY_MAX_IMAGE_BYTES`로 1~64 MiB 범위에서 변경한다. 무제한 수신은 허용하지 않는다.

## 4. 실제 Jetson/Unity 전환

Jetson에서는 프로젝트 경로에 맞춘 별도 운영 env를 준비하고 서버를 실행한다.
`aoi_unity.py`만 복사하면 안 된다. 이 서버는 `aoi_worker.py`,
`aoi_pipeline.py`, `aoi_runtime.py`에 의존하므로 WSL 저장소의
`fab_virtual_lot/*.py` 전체와 패키지 메타데이터를 함께 배치한다.

WSL에서 다음을 실행한다. 이 명령은 대상 디렉터리의 기존 파일을 삭제하지 않고
동일한 이름의 패키지 파일만 갱신한다.

```bash
cd /mnt/c/posco_project
scp jetson_ws/src/fab_virtual_lot/fab_virtual_lot/*.py \
  jetson@192.168.10.184:/home/jetson/project/smart_factory/jetson_ws/src/fab_virtual_lot/fab_virtual_lot/
scp jetson_ws/src/fab_virtual_lot/setup.py \
    jetson_ws/src/fab_virtual_lot/setup.cfg \
    jetson_ws/src/fab_virtual_lot/package.xml \
  jetson@192.168.10.184:/home/jetson/project/smart_factory/jetson_ws/src/fab_virtual_lot/
```

Jetson에서 소스 의존 파일을 먼저 검사하고 다시 빌드한다.

```bash
cd /home/jetson/project/smart_factory/jetson_ws
test -f src/fab_virtual_lot/fab_virtual_lot/aoi_unity.py
test -f src/fab_virtual_lot/fab_virtual_lot/aoi_worker.py
test -f src/fab_virtual_lot/fab_virtual_lot/aoi_pipeline.py
test -f src/fab_virtual_lot/fab_virtual_lot/aoi_runtime.py

source /opt/ros/humble/setup.bash
colcon build --packages-select fab_virtual_lot --symlink-install --event-handlers console_direct+
source install/setup.bash
python3 -c 'import fab_virtual_lot.aoi_unity, fab_virtual_lot.aoi_worker; print("AOI 모듈 확인 완료")'
ros2 pkg executables fab_virtual_lot
```

`ros2 pkg executables`는 `setup.py`의 실행 항목만 확인하므로 그것만으로 Python
모듈이 모두 배치되었다고 판단하지 않는다. 위 `python3 -c` import 검사가 통과해야
서버를 실행한다.

```bash
cd /home/jetson/project/smart_factory
source /opt/ros/humble/setup.bash
source jetson_ws/install/setup.bash
set -a
source .env.aoi-unity
set +a
ros2 run fab_virtual_lot fab_aoi_unity_server
```

운영 서버는 `AOI_UNITY_WS_HOST=0.0.0.0`으로 바인드하고 Unity는 `ws://<JETSON_IP>:8400/aoi`에 접속한다. 토큰은 test 값을 재사용하지 말고 운영용 비밀값으로 교체한다.

Jetson 팀 연동에서는 AOI 결과를 Gateway/Aiven에도 보존하도록 다음 값을 사용한다.

```dotenv
AOI_ROS_PERSISTENCE_ENABLED=true
AOI_RUNTIME_DB=/home/jetson/project/smart_factory/data/aoi-unity.sqlite
ROS_EVENT_TOPIC=/fab/events
ROS_EVENT_ACK_TOPIC=/fab/event_acks
```

서버 시작 로그의 `ROS persistence=enabled`를 확인한다. 이 모드에서는 Unity에
completed 응답을 보내기 전에 동일 event를 SQLite outbox에 기록하고,
`/fab/events`로 재발행한다. Gateway의 `/fab/event_acks`가 `committed`를 반환할
때까지 pending 상태를 유지한다. Unity 응답의 `persistence_status=queued`는
Jetson outbox 저장 완료를 뜻하며 Aiven commit 완료를 뜻하지 않는다. Aiven commit은
Gateway stream의 같은 `message_id/event_id` 또는 DB 조회로 확인한다.

다른 Jetson 터미널에서 실제 리슨 주소를 확인한다.

```bash
ss -ltnp | grep ':8400'
```

정상 출력에는 `0.0.0.0:8400`이 포함된다. `127.0.0.1:8400`이면 외부 WSL이나
Unity가 접속할 수 없으므로 `.env.aoi-unity`의 `AOI_UNITY_WS_HOST`를
`0.0.0.0`으로 고친 뒤 서버를 재시작한다.

## 5. Jetson 실제 모델 모드와 NumPy 호환성

다음 결과는 좌표 오류가 아니라 Mock 모델 실행이다.

```json
{
  "result_origin": "mock",
  "parts": [{"bbox_xyxy": [5, 5, 120, 120]}],
  "defects": [{"bbox_xyxy": [10, 10, 80, 80]}]
}
```

Jetson에서 `NumPy 2.x`와 NumPy 1.x 기준으로 빌드된 PyTorch·matplotlib가 충돌하면
운영 Python이나 JetPack 패키지를 제거하지 않는다. 프로젝트 전용 디렉터리에 호환
NumPy만 설치하고 해당 서버 프로세스의 import 경로 앞에 둔다.

```bash
cd /home/jetson/project/smart_factory
mkdir -p .python-aoi
python3 -m pip install --no-deps --target .python-aoi 'numpy==1.26.4'

export PYTHONPATH="$PWD/.python-aoi${PYTHONPATH:+:$PYTHONPATH}"
python3 - <<'PY'
import numpy, cv2, torch, matplotlib
from ultralytics import YOLO
print("numpy", numpy.__version__, numpy.__file__)
print("cv2", cv2.__version__)
print("torch", torch.__version__)
print("matplotlib", matplotlib.__version__)
print("ultralytics import 완료")
PY
```

위 import가 모두 성공한 뒤 `.env.aoi-unity`를 다음처럼 설정한다.

```dotenv
AOI_MODE=prod
AOI_INFER_DEVICE=0
```

같은 터미널에서 ROS overlay와 env를 다시 읽고 실행한다.

```bash
cd /home/jetson/project/smart_factory
source /opt/ros/humble/setup.bash
source jetson_ws/install/setup.bash
set -a
source .env.aoi-unity
set +a
export PYTHONPATH="$PWD/.python-aoi${PYTHONPATH:+:$PYTHONPATH}"
ros2 run fab_virtual_lot fab_aoi_unity_server
```

Unity 시험 결과 JSON이 `result_origin=prod`이고 실제 이미지 크기 범위 안의
`bbox_xyxy`를 포함해야 실제 모델 좌표 시험으로 인정한다. prod 시작 실패를 mock
성공으로 대체하지 않는다.

이 직접 경로의 전송 성공은 Aiven DB 커밋을 의미하지 않는다. 동일 AOI 결과의 영구 보존과 재시도는 기존 ROS → Gateway → Aiven E2E가 계속 담당한다.
