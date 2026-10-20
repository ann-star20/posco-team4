# 공정 검사·추론·ACK 테스트 프로세스

2026-10-18: ML→TCAD→승인→Unity 적용 ACK까지 포함한 [전체 mock 실행](full-mock-process.md)을 추가했다. `bash scripts/run-mock-e2e.sh`로 현재 구현된 전체 mock 공정을 시험한다. 아래 '구현 후' 절은 더 넓은 장애·실장비 인수 요구다.

기준일: 2026-10-17. 1절 ROS ACK와 2절 HTTP/WebSocket 점검은 실행 가능하다. AOI fixture·실모델·HTTP/WS 제어도 부분 구현됐다. 3절 이후는 미구현 요구를 포함하는 목표 시험 절차다. [최신 구현/검증 상태](integration-status-and-latency.md)에서 완료 범위를 확인한다. Unity 앱 개발은 범위에 포함하지 않는다.

추가 구현 상태: [WSL 한 PC AOI 실모델·ROS·Aiven·WebSocket 직접 시험](wsl-aoi-one-pc.md)은 실행 가능하다. AOI 제어 요청은 구현됐지만 원격 이미지 조회 API·ML 요청·Unity 적용 ACK는 구현 대상이다.

## 1. 지금 실행 가능한 ROS 이벤트 → Aiven ACK 확인

전체 절차는 [수동 ROS·Aiven 가이드](manual-ros2-aiven-check.md)를 따른다. 같은 bridge/발행기를 중복 시작하지 않는다. Jetson 발행기를 켜기 전에 ACK 관찰자를 준비한다.

WSL 터미널 A — Gateway:

```bash
cd /mnt/c/posco_project
source /opt/ros/humble/setup.bash
source "$HOME/posco-gateway-venv/bin/activate"
export PYTHONPATH="$PWD/services/event_gateway/src${PYTHONPATH:+:$PYTHONPATH}"
python -m event_gateway.ros_adapter
```

WSL 터미널 B — 저장 확인 ACK:

```bash
source /opt/ros/humble/setup.bash
ros2 topic echo /fab/event_acks std_msgs/msg/String
```

Jetson의 별도 확인 터미널:

```bash
source /opt/ros/humble/setup.bash
ros2 topic info /fab/events --verbose
ros2 topic info /fab/event_acks --verbose
```

`/fab/events`에 Gateway 구독자가 있고, `/fab/event_acks`에 관찰자 구독이 확인된 뒤 기존 가이드의 Jetson 발행기를 실행한다. DB 커밋이 없는데 ACK가 나오는 것은 실패다. ACK의 event_id/run_id/sequence를 Aiven `events`와 대조한다. 기존 데모는 시작할 때 새 이벤트 두 건을 만든다. 재시작하면 새 두 건이 추가되므로 복구 시험과 신규 생성 시험을 구분한다.

ACK를 놓쳤다면 Jetson에서 다음 읽기 전용 조회로 확인한다. completed는 과거 성공 기록이며 현재 통신이 살아 있다는 증거는 아니다.

```bash
python3 - <<'PY'
import sqlite3
path = '/home/jetson/project/smart_factory/data/event-outbox.sqlite'
with sqlite3.connect(f'file:{path}?mode=ro', uri=True) as db:
    for row in db.execute('SELECT event_id,run_id,delivered_sequence FROM pending ORDER BY created_at DESC LIMIT 10'):
        print(row)
PY
```

`delivered_sequence IS NULL`은 미확인, 양수는 Aiven 커밋 ACK 확인, -1은 격리 ACK다. Aiven 조회 명령은 기존 가이드 3절·4절을 사용하며 비밀 URL을 로그에 출력하지 않는다.

## 2. 지금 실행 가능: HTTP·WebSocket 통신 점검

각 WSL 터미널에서 공통 준비:

```bash
cd /mnt/c/posco_project
source "$HOME/posco-gateway-venv/bin/activate"
export PYTHONPATH="$PWD/services/event_gateway/src${PYTHONPATH:+:$PYTHONPATH}"
```

TCAD mock 서버 터미널:

```bash
python -m mock_tcad.app
```

다른 터미널에서 실제 HTTP POST·GET 및 동일 request_id 재전송을 확인:

```bash
python -m event_gateway.communication_check tcad-mock
```

성공하면 `status=succeeded`, `result_origin=mock`, job_id가 나온다. 이 점검은 TCAD mock SQLite에 시험 작업 하나를 만들고 Aiven에 가짜 이벤트를 삽입하지 않는다. 각 단계 Aiven 기록까지 시험하려면 1절의 Jetson 데모와 `python -m event_gateway.verification_worker`를 함께 실행한다. TCAD mock의 pass 시나리오를 기준으로 한다.

원격 워크스테이션에서 mock 서버를 실행할 때 해당 서버의 `.env`에 `TCAD_BIND_HOST=0.0.0.0`, `TCAD_BIND_PORT=8100`을 설정한다. Gateway의 `.env`는 `TCAD_MODE=mock`, `TCAD_MOCK_URL=http://<워크스테이션 IP>:8100`으로 지정한다. WSL 로컬 시험만 한다면 기본 127.0.0.1을 유지한다. 원격 mock을 사용할 때는 통합 시작 스크립트가 아니라 각 프로세스를 개별 실행해 불필요한 로컬 mock 서버를 시작하지 않는다.

Gateway HTTP/WebSocket 서버 터미널:

```bash
python -m event_gateway.app
```

다른 터미널에서 기존 Aiven 이벤트의 run ID로 HTTP 재생과 WebSocket 수신 일치를 검사한다. run ID는 Jetson `data/demo-run-id` 또는 기존 Aiven 조회 결과를 사용한다.

```bash
python -m event_gateway.communication_check gateway --run-id '<실제 RUN_ID>'
```

`status=matched`, event_id, sequence가 나오면 같은 커밋 이벤트를 HTTP와 실제 WebSocket으로 받았다. 이벤트가 없는 run은 실패로 보고한다. 이 도구는 Unity 앱 역할의 통신 시험 클라이언트이며 C# 앱이 필요하지 않다. 지속 관찰은 기존 `tools/mock_unity/client.py`를 사용한다.

다른 PC에서 검사하려면 그 PC에 설치한 프로젝트의 `.env`에서 `UNITY_GATEWAY_HTTP_URL=http://<Gateway 호스트>:8000`, `UNITY_GATEWAY_WS_URL=ws://<Gateway 호스트>:8000/api/v1/stream`을 설정한다. loopback은 다른 컴퓨터를 가리키지 않는다. WSL의 외부 접근 가능 주소·포트는 해당 네트워크에서 확인하며 임의로 방화벽 설정을 바꾸지 않는다.

Silvaco 미연결 서비스 틀은 별도 터미널에서 실행:

```bash
TCAD_BIND_PORT=8200 python -m tcad_service.app
```

다른 터미널에서 준비 여부만 검사:

```bash
TCAD_MODE=prod TCAD_PROD_URL=http://127.0.0.1:8200 \
python -m event_gateway.communication_check tcad-readiness
```

`reachable=true, ready=false`와 종료 코드 2는 HTTP 서버에 도달했지만 Silvaco가 미연결이라는 뜻이다. `tcad-mock` 점검기는 mock 출처를 확인한 서버에만 fixture를 제출한다. prod 서비스는 임의의 가상 성공을 만들지 않는다.

주의: 기존 mock 서버는 요청 본문의 일부만 비교했으나 지금은 전체 본문을 비교한다. 이전 mock DB에 저장된 작업의 재시도는 충돌할 수 있다. 기록을 삭제하지 말고 새 시험 run/request ID로 시험한다. 이전 작업 실패는 별도 확인한다.

## 3. 구현 후: 카메라 mock 전체 흐름

1. 새 run_id와 단일 stage_attempt를 만들고 모든 모델 모드를 mock으로 설정한다.
2. 이미지 저장소, Gateway API/ROS 브리지, Jetson mock inference Worker, TCAD mock/검증 Worker, Python Unity 시험 클라이언트를 실행한다. 이미지 저장소와 모델 readiness를 먼저 확인한다.
3. Jetson의 CAMERA_MODE=mock과 고정 fixture 경로를 설정한다. 실제 카메라는 필요하지 않다.
4. Python 시험 클라이언트가 WS control에 inspection.requested와 camera_id를 보낸다. request.accepted에 job_id가 있고 Aiven에 요청·작업·이벤트가 남아야 한다.
5. /fab/inference_requests를 관찰한다. Jetson inbox 저장 후 inference.accepted가 /fab/events에 나타나고 해당 event의 committed ACK를 받아야 한다. fixture 프레임 캡처·HTTP 업로드 후 artifact_id와 sha256, DB ready를 확인한 뒤 추론한다.
6. AOI 결과에 부품·결함 배열, score, 임계값, 판정, 모델 버전, input_origin/result_origin, 원본·결과 artifact_id가 있어야 한다.
7. Unity mock은 커밋 이벤트를 받아 job/stage를 맞추고 이미지를 조회한다. 동일 sequence의 중복 표시를 막는다.
8. 별도 진단 단계 요청을 시험한다. TCAD 입력이 준비된 사례만 검증 job을 생성하고, 부족한 사례는 review_required가 되어야 한다.

## 4. 구현 후: 실제 카메라·네트워크·prod 모델

- 카메라 prod: 기존 `/home/jetson/project/test/jetson_phone_camera_rec.py`는 OpenCV로 HTTP `/video`를 읽는 방식임을 확인했다. 대화형 스크립트를 그대로 import하지 않는다. headless adapter 구현 후 CAMERA_SOURCE_URL에 현재 카메라 주소를 넣고 CAMERA_MODE=prod로 전환한다. 입력 프레임의 freshness, frame_id/hash, 저장 성공·동일 작업의 원본 고정, 연결 실패·재연결을 확인한다. 카메라는 현재 미연결이며 env 변경만으로 아직 캡처가 실행되지는 않는다. Unity 캡처 코드는 만들지 않는다.

- 원격 mock: TCAD mock은 워크스테이션에서, Unity mock은 다른 PC에서 실행한다. URL만 각 호스트로 바꾸고 mock 모드는 유지한다. 실제 HTTP/WebSocket/ROS를 통과해야 한다.
- AOI prod: 모델 파일·클래스·전처리·기준 이미지 정답을 확인하고 AOI_MODE만 prod로 바꾼 새 run으로 시험한다. 파일명을 보고 모델 로더를 추측하지 않는다. 알려진 정상·불량·부품 없음 사례를 비교한다.
- 진단 prod: 모델 입력 특성 순서·단위·정규화와 평가 세트가 준비된 이후에만 전환한다.
- TCAD prod: 실제 서비스 readiness와 단일 job 조회, X/Y 단위, request_id 멱등성을 확인한 뒤 전환한다. 미연결 틀의 503은 정상적인 미준비 응답이며 계산 성공은 아니다.
- 실제 Unity: 동일 요청/스트림 계약으로 접속한다. mock Unity 성공은 C# 앱 구현 성공을 보증하지 않는다.

## 5. 필수 실패 시험과 합격 기준

| 상황 | 합격 기준 |
|---|---|
| 같은 request_id 재전송 | job 한 개. 같은 ID의 다른 본문은 충돌 오류 |
| Unity 접수 ACK 유실 | 재요청으로 같은 job 확인 |
| ROS 작업 전달 중복 | Jetson inbox job 한 개, 동시 중복 추론 없음 |
| Jetson 수신 직후 재시작 | inbox에서 작업 복구 |
| 추론 결과 생성 후 네트워크 단절 | outbox에 보존, 복구 후 Aiven 커밋과 ACK |
| Aiven 장애 | committed ACK 없음, 재시도 후 결과 행 중복 없음 |
| 이미지 저장 실패·용량 초과 | ready/completed/pass로 넘어가지 않음 |
| 결과 이미지 업로드 후 프로세스 종료 | artifact 재사용 또는 미참조 상태 복구, 원본 보존 |
| WebSocket 재접속 | 마지막 처리 sequence 이후 재생, 화면 중복 방지 |
| 오래된 stage/attempt 결과 | 최신 단계 상태를 덮어쓰지 않음 |
| 부품 미검출·낮은 점수 | pass 처리하지 않고 review/error |
| 모델 파일 누락·버전 불일치 | prod 시작/작업 실패를 명시, mock 자동 대체 없음 |
| AOI 외관 결함만 있음 | 무조건 TCAD 호출하지 않음 |
| TCAD timeout·503 | 재시도/만료 기록, verified로 변경되지 않음 |
| 검증 통과 | 사람 승인 전 recipe 적용 없음 |

시험 기록에는 시간, run_id/job_id/event_id, 모델·모드, 입력 sha256, 예상/실제 상태, Aiven sequence, artifact 조회 결과, 재시도 횟수를 기록한다. 비밀정보와 전체 연결 문자열은 기록하지 않는다. 운영 데이터를 지우며 복구 시험하지 않고 시험 run과 테스트 스키마를 분리한다.
