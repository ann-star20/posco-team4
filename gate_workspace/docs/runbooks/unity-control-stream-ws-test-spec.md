# Unity ↔ Gateway ML/TCAD WebSocket 테스트 명세

작성일: 2026-10-22
대상: WSL Gateway(`services/event_gateway`)를 띄우고 Unity가 전기적 ML(및 그 결과로
촉발되는 TCAD 검증)에 요청을 보내 결과를 받는 테스트.
소스 기준: `services/event_gateway/src/event_gateway/app.py`,
`inference_jobs.py`, `stream.py` (2026-10-22 기준 코드 분석).

## 1. 핵심 원칙 — 두 WebSocket의 역할은 분리된다

Gateway는 Unity에 **두 개의 서로 다른 WebSocket**을 제공하며, 절대 하나로 합치지
않는다.

| 채널 | 경로 | 방향/역할 | 응답 시점 |
|---|---|---|---|
| 제어 WS | `ws://<GATEWAY_IP>:8000/api/v1/control` | Unity → Gateway 요청 접수 전용 | **즉시 동기 응답** (`request.accepted` / `request.rejected`) |
| 스트림 WS | `ws://<GATEWAY_IP>:8000/api/v1/stream?run_id=...&after_sequence=...` | Gateway → Unity 커밋 이벤트 재생 전용 | **비동기** — ML/TCAD 처리가 끝나 DB에 커밋된 뒤에만 도착 |

- 제어 WS가 주는 `request.accepted`는 "작업이 DB에 접수되어 큐에 들어갔다"는
  뜻일 뿐, ML 추론이나 TCAD 검증이 끝났다는 뜻이 아니다. (`app.py:171` 참고)
- 실제 추론/검증 결과는 같은 커넥션으로 돌아오지 않는다. 반드시 스트림 WS를
  별도로 열어 `run_id`로 구독해야 한다.
- 스트림 WS는 DB의 커밋 이벤트를 `sequence` 커서로 반복 조회(polling)하는
  재생기다. 연결이 끊겨도 이벤트는 Aiven PostgreSQL에 보존되므로
  `after_sequence`에 마지막으로 받은 sequence를 넣어 재접속하면 유실 없이
  이어받는다. (`app.py:212-233`)
- sequence는 연속 번호가 아니다. 빈 번호를 누락으로 간주하지 않는다.

## 2. 전체 데이터 경로

```text
Unity
  -> Gateway WS /api/v1/control   (요청, 즉시 accepted/rejected)
  -> PostgreSQL inference_jobs/inference_dispatches 커밋
  -> ROS 2 /fab/surrogate_requests 또는 /fab/diagnosis_requests
  -> Jetson Worker (fab_surrogate_worker / fab_diagnosis_worker)
  -> HTTP POST <ML_URL>/api/v1/predict 또는 /api/v1/diagnose
  -> ROS 2 /fab/events (surrogate.completed / diagnosis.completed)
  -> Gateway/Aiven 커밋
  -> (diagnosis에서 anomaly_detected=true + 유효한 tcad_proposal이 있을 때만)
     TCAD 검증 outbox 생성 -> TCAD mock/실서버 HTTP POST/GET
     -> tcad.verification.* 이벤트 커밋
  -> Gateway WS /api/v1/stream (run_id 구독)
  -> Unity
```

**Unity는 TCAD에 직접 연결하지 않는다.** TCAD 호출은 Gateway/Worker가
전적으로 수행하며, Unity는 Gateway 스트림 WS에서 `tcad.verification.*`
이벤트로만 진행 상황과 결과를 본다. ("TCAD ML"이라는 표현을 쓰더라도
실제로는 Unity → 전기적 ML(diagnosis/surrogate) 요청 → 이상 탐지 시에만
내부적으로 TCAD HTTP 검증이 추가로 붙는 구조다.)

## 3. 제어 WS 요청 계약

연결 시 헤더 `X-Unity-Token`에 Gateway `.env`의 `UNITY_API_TOKEN` 값을 보낸다.
토큰이 없거나 틀리면 Gateway가 코드 1008로 연결을 닫는다. (`app.py:143-150`)

지원하는 `type` 세 가지 (그 외 값은 즉시 `request.rejected`/`unsupported_type`):

- `inspection.requested` (AOI)
- `surrogate.requested` (전기적 특성 ML)
- `diagnosis.requested` (이상 진단 ML, 결과에 따라 TCAD 자동 연계)

### surrogate.requested / diagnosis.requested 메시지 형식

```json
{
  "type": "diagnosis.requested",
  "schema_version": 1,
  "request_id": "<NEW_UUID>",
  "run_id": "<NEW_UUID>",
  "lot_id": "LOT-001",
  "unit_id": "MOSFET-001",
  "stage_id": "diagnosis",
  "stage_attempt": 1,
  "model_contract_version": "fab-ml-v1",
  "input_payload": { "scenario": "anomaly" }
}
```

- `surrogate.requested`는 `stage_id` 기본값이 `electrical`, `diagnosis.requested`는
  `diagnosis`다. 둘 다 `model_contract_version`은 현재 `fab-ml-v1`만 허용한다.
  (`app.py:44-58`)
- `extra="forbid"`라서 정의되지 않은 필드가 섞이면 바로 검증 오류로 거절된다.
- 매 시험마다 `request_id`, `run_id`는 새 UUID를 쓴다. 같은 `request_id`에
  다른 내용이 오면 `409`(JobConflict)로 거절된다. (`inference_jobs.py:47-50`)
- 동일 `run_id` + `unit_id` + `stage_id`에 이미 진행 중(`queued/dispatching/accepted/running`)인
  작업이 있으면 역시 `409`로 거절된다. (`inference_jobs.py:51-57`)

### 즉시 응답 (제어 WS, 동기)

정상 접수:

```json
{
  "type": "request.accepted",
  "request_id": "<REQUEST_UUID>",
  "job_id": "<JOB_UUID>",
  "status": "queued"
}
```

거절 (예시):

```json
{ "type": "request.rejected", "code": "unsupported_type" }
{ "type": "request.rejected", "code": "invalid_request" }
{ "type": "request.rejected", "code": 409, "detail": "request_id has different content" }
```

이 응답들은 모두 **같은 TCP 연결에서 밀리초 단위로 즉시 온다.** ML 추론이나
TCAD 왕복을 기다리지 않는다.

## 4. 스트림 WS 결과 계약 (비동기)

```text
ws://<GATEWAY_IP>:8000/api/v1/stream?run_id=<control에 보낸 run_id와 동일>&after_sequence=0
```

- 인증 헤더 불필요(현재 코드 기준, `app.py:212`). `run_id`가 다르면 해당 run의
  이벤트만 보이므로 반드시 제어 WS에서 쓴 `run_id`와 동일하게 맞춘다.
- 받을 이벤트 타입(관련 사례):
  - `surrogate.completed` / `diagnosis.completed` — ML 응답 원형(JSONB) 도착
  - `tcad.verification.queued` / `running` / `succeeded` / `failed` / `cancelled` —
    후보별 TCAD 진행 상태
  - `tcad.verification.batch_completed` — 해당 proposal의 모든 후보 종료
  - `tcad.verification.review_required` — 성공 후보가 있어 관리자 확인 대기
  - `correction.*` — 검증 결과를 사람이 승인하는 단계 (이번 테스트 범위 밖이면 무시)
- `tcad.verification.*` payload에는 `api_token`, `tcad_api_token`,
  `x_fab_token`, `endpoint_url`, `tcad_prod_url` 같은 전송 비밀 필드가 Gateway에서
  자동 제거된 뒤 내려온다. (`stream.py:4-26`) Unity/로그에 토큰이 노출될 걱정은
  없지만, 반대로 이 필드들이 안 보이는 것은 버그가 아니라 의도된 마스킹이다.
- `correction.*` 이벤트에는 `current/delta/recommended` 비교값이 추가 가공되어
  실린다 (`stream.py:27-35`).

### 결과가 안 올 때 확인 순서

1. 스트림 WS를 연 `run_id`가 제어 WS 요청의 `run_id`와 정확히 같은가.
2. `inference_jobs.status`가 `queued`에 멈춰 있지 않은가 (Jetson Worker 미기동/ROS
   연결 끊김 의심).
3. ML 응답이 `anomaly_detected=false`이거나 `tcad_proposal`이 없으면 TCAD 이벤트는
   정상적으로 발생하지 않는다 (의도된 동작, 오류 아님).

## 5. 환경변수 (WSL Gateway `.env`)

```dotenv
DATABASE_URL=<Aiven PostgreSQL>
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8000
UNITY_API_TOKEN=<제어 WS 인증 토큰, 로컬 .env에만>
UNITY_MODE=mock          # 테스트용 Unity Python peer 사용 시
TCAD_MODE=mock           # 테스트는 mock, 실제 검증 서버 준비 후 prod
TCAD_MOCK_URL=http://127.0.0.1:8100
SURROGATE_MODE=mock      # 또는 prod (Jetson 모델 서비스 준비 시)
SURROGATE_MOCK_URL=http://<WSL_IP>:8300
DIAGNOSIS_MODE=mock
DIAGNOSIS_MOCK_URL=http://<WSL_IP>:8300
ROS_SURROGATE_REQUEST_TOPIC=/fab/surrogate_requests
ROS_DIAGNOSIS_REQUEST_TOPIC=/fab/diagnosis_requests
ROS_EVENT_TOPIC=/fab/events
ROS_EVENT_ACK_TOPIC=/fab/event_acks
```

`TCAD_MODE=prod`로 바꾸려면 `TCAD_PROD_URL`과 `TCAD_API_TOKEN`이 반드시 있어야
하며, 없으면 Gateway가 기동을 거부한다. (`config.py:89-91`)

## 6. 이번 테스트 환경 (팀 공유용)

- WSL (Gateway 실행 호스트) IP: `192.168.10.234`
- Jetson (Worker/모델 호스트) IP: `192.168.10.253`, 계정 `jetson` / `jetson1234`
- Gateway 소스: `services/event_gateway` (WSL 경로 `/mnt/c/posco_project/services/event_gateway`)
- Jetson과 WSL IP는 재부팅/네트워크 변경 시 바뀔 수 있으므로 매 세션 시작 전
  양쪽에서 `hostname -I`로 재확인한다. 주소가 바뀌면 `.env`와
  `config/dds/wsl-fastdds.xml` / `config/dds/jetson-fastdds.xml`도 맞춰 수정한다.

> 비밀번호/토큰 등은 이 문서가 아니라 각 호스트의 로컬 `.env`에만 보관한다.
> 팀 공유 문서·로그·테스트 실패 출력에 그대로 붙여넣지 않는다.

## 7. 실행 절차 요약 (WSL)

1. **터미널 A — ROS bridge**
   `event_gateway.ros_adapter` 실행 (ROS_DOMAIN_ID/RMW_IMPLEMENTATION은 현재
   셸 값을 상속, 0으로 덮어쓰지 않음).
2. **터미널 B — HTTP/WS 서버**
   `python -u -m event_gateway.app` → `curl http://127.0.0.1:8000/health/live`로
   `{"status":"ok"}` 확인.
3. **터미널 C — mock ML 서비스** (실제 모델 서비스 없을 때만)
   `python -u -m mock_surrogate.app` (`SURROGATE_BIND_PORT=8300`), WSL/Jetson
   양쪽에서 `curl http://<WSL_IP>:8300/health/ready`로 접근 확인.
   (Jetson에서 실패하면 Windows/Hyper-V 방화벽에서 8300 인바운드 허용 필요.)
4. **Jetson — Worker 실행**
   SSH로 Jetson(`192.168.10.253`, `jetson`/`jetson1234`) 접속 후
   `fab_surrogate_worker` / `fab_diagnosis_worker` 실행. `SURROGATE_MOCK_URL`에
   WSL IP(`192.168.10.234`)를 명시한다.
5. **(TCAD까지 시험할 경우) 터미널 D/E — mock TCAD + 검증 Worker**
   `fab-mock-tcad`, `fab-verification-worker` 실행.
6. **Unity(또는 테스트 클라이언트)**
   제어 WS `ws://192.168.10.234:8000/api/v1/control`에 연결해
   `diagnosis.requested`(또는 `surrogate.requested`) 전송 → `request.accepted` 확인.
   동시에 스트림 WS `ws://192.168.10.234:8000/api/v1/stream?run_id=<동일>&after_sequence=0`을
   열어 `*.completed` 및 (해당 시) `tcad.verification.*` 이벤트를 수신.

## 8. 테스트 시나리오 매트릭스

| input_payload.scenario | 기대 결과 |
|---|---|
| `normal` | `*.completed` 이벤트만, TCAD 호출 없음 |
| `anomaly` | `*.completed` + TCAD 검증 outbox 생성 + `tcad.verification.*` 연쇄 + `review_required` |
| `missing_candidate` | `*.completed`, `routing_status=review_required`, TCAD 호출 없음 |
| `failed`류(모델 실패) | `inference_jobs.status=failed`, TCAD 호출 없음 |

## 9. DB 확인 쿼리 (Aiven)

```sql
SELECT job_id, request_id, task_type, status, result_event_id, updated_at
FROM public.inference_jobs
WHERE task_type IN ('surrogate','diagnosis')
ORDER BY created_at DESC LIMIT 10;

SELECT sequence, event_id, event_type, source, payload, received_at
FROM public.events
WHERE event_type IN ('surrogate.completed','diagnosis.completed')
ORDER BY sequence DESC LIMIT 10;

SELECT g.proposal_id, g.status, g.candidate_count, g.terminal_count,
       c.candidate_index, c.tcad_request_id, c.status, c.last_error_code
FROM tcad_proposal_groups g
JOIN tcad_verification_candidates c USING (proposal_id)
ORDER BY g.created_at DESC, c.candidate_index;
```

## 10. 실패 판별 기준

- 제어 WS에서 `request.rejected`/`unsupported_type`, `invalid_request`: 메시지
  스키마 오류(필수 필드 누락, 허용되지 않는 필드, 타입 불일치).
- 제어 WS에서 `request.rejected`/409: 같은 `request_id`가 다른 내용으로 재전송됨,
  또는 같은 `run_id+unit_id+stage_id`에 이미 진행 중인 작업이 있음.
- 제어 WS는 정상(`accepted`)인데 스트림 WS에 결과가 안 옴: Jetson Worker 미기동,
  ROS 토픽 미연결, 또는 ML 서비스(`/health/ready`) 다운 — Worker/서비스 로그부터
  확인.
- TCAD 401/403: 토큰 불일치, 해당 후보는 즉시 terminal failed.
- TCAD 400/422: 요청 계약 오류, 자동 재시도 없음.
- TCAD 5xx/네트워크 오류: 동일 `tcad_request_id`로 재시도.

## 11. Unity 없이 직접 시험하는 스크립트

Unity 클라이언트를 아직 붙이지 않고도 큐 적재·비동기 결과 수신을 그대로 확인할 수
있다. `tools/mock_unity/ml_queue_probe.py`는 다음을 한 번에 수행한다.

1. 제어 WS에 여러 건을 연속으로 보내고, 각 건의 **즉시** `request.accepted`만
   기록한다 (ML 처리를 기다리지 않음을 직접 확인).
2. 전송이 끝난 뒤 별도로 스트림 WS를 열어 `run_id`로 구독하고, 결과 이벤트가
   도착할 때마다 "접수 시각 대비 몇 초 뒤에 왔는지"를 출력한다.
3. 모든 요청의 결과를 받으면 요약(`status: passed`, 각 건의 경과 시간)을 출력한다.

```bash
cd /mnt/c/posco_project
source "$HOME/posco-gateway-venv/bin/activate"
export PYTHONPATH="$PWD/services/event_gateway/src"

python tools/mock_unity/ml_queue_probe.py \
  --gateway ws://192.168.10.234:8000 \
  --token "$UNITY_API_TOKEN" \
  --request-type diagnosis.requested \
  --scenarios anomaly anomaly anomaly normal \
  --timeout 180
```

- `--scenarios`에 값을 여러 개 주면 그 개수만큼 요청을 만든다(`unit_id`는
  `UNIT-1`, `UNIT-2`...로 자동 부여). 동시에 여러 건을 던져 큐에 쌓이는지,
  그리고 각 건이 제출 순서와 무관하게 끝나는 순서로 도착하는지 확인하는 용도다.
- 출력의 `sent_unit_id`/`response` 줄은 제어 WS 즉시 응답, 그 다음
  `event_type`/`elapsed_since_accept_s` 줄들은 스트림 WS에서 받은 비동기 결과다.
  `elapsed_since_accept_s`가 0에 가깝지 않고 Jetson Worker 처리 시간만큼 걸리는
  것이 정상이며, 이게 바로 "접수는 즉시, 결과는 나중에"를 숫자로 보여주는
  부분이다.
- `anomaly` 시나리오를 섞으면 TCAD 검증까지 이어지는지도 같은 스트림 WS 로그에서
  `tcad.verification.*` 이벤트로 확인할 수 있다(스크립트는 `*.completed`까지만
  기다리고 종료하므로, TCAD 단계까지 보려면 터미널 출력을 계속 지켜보거나
  `--timeout`을 늘린다).
- 필요하면 `--run-id`를 고정값으로 줘서 같은 run에 반복 테스트를 누적시킬 수도
  있다. 단, 같은 `run_id`+`unit_id`+`stage_id`로 진행 중인 작업이 있으면 409로
  거절되므로 재시험 시 `unit_id`가 겹치지 않게 한다.

## 12. 2026-10-22 발견된 이슈와 조치 (Unity 연동 전 필독)

실제 WSL↔Jetson 연동 시험 중 아래 두 가지가 막혀 있었고, 지금 모두 조치했다.
Unity 담당자가 테스트할 때 같은 증상을 보면 아래 순서로 재현/확인한다.

### 12.1 Windows 방화벽 — ROS 2 DDS 디스커버리 차단 (조치 완료)

증상: `request.accepted`는 오지만 스트림 WS에 결과가 영원히 안 옴.
`ros2 topic info /fab/diagnosis_requests --verbose --no-daemon`을 WSL에서 돌리면
`Subscription count: 0`인데 Jetson 쪽에서 똑같이 돌리면 `Subscription count: 1`
(비대칭 디스커버리 — Jetson→WSL UDP가 Windows 방화벽에 막혀 있었음).

조치: 관리자 PowerShell에서 아래 규칙 추가 완료.
```powershell
New-NetFirewallRule -DisplayName "ROS2 FastDDS inbound from Jetson" `
  -Direction Inbound -Protocol UDP -LocalPort 7400-7470 `
  -RemoteAddress 192.168.10.253 -Action Allow
```
`scripts/ros-stack-wsl.sh start`를 실행하면 이제 이 규칙이 없을 때 자동으로
생성을 시도한다(UAC 승인 필요). Jetson IP가 바뀌면 `-RemoteAddress`를 바꿔
규칙을 다시 만들어야 한다.

### 12.2 워커 예외가 로그에서 뭉개짐 (코드 수정 완료, 재배포 필요)

증상: 방화벽을 고친 뒤에도 요청이 `queued`에서 멈추고
`diagnosis unavailable or invalid response; durable request retained` 경고만
반복됨. 막혀있던 요청의 저장된 바디를 그대로 ML 서비스에 재전송하면 HTTP 200
success가 나오는데도 워커 자신은 계속 실패 — 실제 예외가
`background_error` 콜백에서 버려지고 있어서 원인을 알 수 없었다.

조치: `diagnosis_worker.py`, `surrogate_worker.py`의 `background_error`가 이제
예외 내용(`repr`)을 경고 로그에 포함한다 (로그 문자열만 바뀜, 동작/시그니처는
동일).

```python
def background_error(self, _exc):
    self.get_logger().warning(
        f"diagnosis unavailable or invalid response; durable request retained: {_exc!r}")
```

**이 수정은 아직 Jetson에 배포되지 않았다.** Jetson의 실행 경로
(`/home/jetson/project/smart_factory/jetson_ws/src/fab_virtual_lot`)는 WSL의
`/mnt/c/posco_project`와 별도 디렉터리이므로 파일을 직접 복사해야 한다. 이
워커는 `colcon build` 없이 `PYTHONPATH`로 소스를 바로 읽으므로 **빌드는 필요
없다.**

## 13. 수정 배포 → 재구동 순서

WSL 터미널에서:

```bash
cd /mnt/c/posco_project

# 1) 수정된 두 파일을 Jetson에 복사
scp jetson_ws/src/fab_virtual_lot/fab_virtual_lot/diagnosis_worker.py \
  jetson_ws/src/fab_virtual_lot/fab_virtual_lot/surrogate_worker.py \
  jetson@192.168.10.253:/home/jetson/project/smart_factory/jetson_ws/src/fab_virtual_lot/fab_virtual_lot/
```

Jetson에서 (SSH 접속 후):

```bash
cd /home/jetson/project/smart_factory

# 2) 기존 워커 정지 (sqlite 큐에 남은 미완료 요청은 보존됨 — 재시작 후 자동 재처리)
./scripts/ros-stack-jetson.sh stop

# 3) 재기동 (DDS 프로파일 재생성 + ML readiness 확인 + python 패키지 확인 포함)
./scripts/ros-stack-jetson.sh start --wsl-ip 192.168.10.234

# 4) 상태/로그 확인 — 이제 실패 시 진짜 예외가 보여야 한다
./scripts/ros-stack-jetson.sh status
tail -f data/ros-stack/jetson/diagnosis-worker.log
```

WSL 쪽은 이미 떠 있으면 재기동 불필요. 처음부터 다시 띄워야 하면:

```bash
cd /mnt/c/posco_project
./scripts/ros-stack-wsl.sh stop
./scripts/ros-stack-wsl.sh start --jetson-ip 192.168.10.253
./scripts/ros-stack-wsl.sh check   # 모든 토픽 Publisher/Subscription 양쪽 1 이상 확인
```

재기동 순서가 중요한 이유: Jetson 워커가 먼저 토픽을 구독해야 Gateway가 보내는
요청을 받을 수 있다. 순서를 바꿔도 디스커버리가 늦게라도 맞춰지긴 하지만,
문제 재현/디버깅 시에는 **Jetson 먼저 → WSL 다음 → `check`로 양방향 확인** 순서를
지키는 게 원인 추적에 유리하다.

## 14. 테스트 실행과 기대되는 DB 결과 (Unity 담당자 검증용)

### 14.1 정상 플로우 요청 (diagnosis, 실제 모델 계약)

```bash
cd /mnt/c/posco_project
set -a; source .env; set +a

REQUEST_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')
RUN_ID=$(python3 -c 'import uuid; print(uuid.uuid4())')

curl -sS -X POST http://127.0.0.1:8000/api/v1/diagnosis-jobs \
  -H 'Content-Type: application/json' \
  -H "X-Unity-Token: $UNITY_API_TOKEN" \
  -d "{\"schema_version\":1,\"request_id\":\"$REQUEST_ID\",\"run_id\":\"$RUN_ID\",\"lot_id\":\"LOT-DIAGNOSIS-001\",\"unit_id\":\"MOSFET-001\",\"stage_id\":\"diagnosis\",\"stage_attempt\":1,\"model_contract_version\":\"fab-ml-v1\",\"input_payload\":{\"measurements\":{\"vth\":2.1,\"gm\":10.0,\"id_on\":20.0,\"bv\":null},\"n_wafers\":1,\"refine\":false}}"

echo "RUN_ID=$RUN_ID"
```

**즉시(동기) 응답**: `{"job_id":"...","status":"queued"}` — 이건 접수 확인일
뿐, 아래 DB 결과가 나와야 "끝까지 흘렀다"고 판단한다.

Unity 쪽에서는 동시에 같은 `RUN_ID`로 스트림 WS를 열어 `diagnosis.completed`
이벤트가 오는지 눈으로도 확인한다:
```text
ws://192.168.10.234:8000/api/v1/stream?run_id=<RUN_ID>&after_sequence=0
```

### 14.2 수십 초 뒤 DB로 최종 확인 (성공 기준)

```sql
-- 1) job 자체가 completed로 끝났는지
SELECT job_id, task_type, status, result_event_id, updated_at
FROM public.inference_jobs
WHERE request_id = '<REQUEST_ID>';
-- 기대: status = 'completed' (failed면 모델 쪽 응답이 status=failed였다는 뜻)

-- 2) 커밋된 이벤트가 실제로 생겼는지
SELECT sequence, event_type, source, received_at
FROM public.events
WHERE event_type = 'diagnosis.completed'
ORDER BY received_at DESC LIMIT 5;
-- 기대: source = 'jetson.diagnosis', sequence가 새로 하나 더 생김

-- 3) 진단 결과 상세
SELECT job_id, top_category, compensation_route, high_confidence, routing_status, created_at
FROM public.diagnosis_results
ORDER BY created_at DESC LIMIT 5;
-- 기대: routing_status가 normal / review_required / verification_queued / failed 중 하나
--       (anomaly_detected=false면 normal, true + 유효 후보면 verification_queued)

-- 4) (routing_status=verification_queued였던 경우만) TCAD 검증까지 이어졌는지
SELECT g.proposal_id, g.status, c.candidate_index, c.status, c.last_error_code
FROM tcad_proposal_groups g JOIN tcad_verification_candidates c USING (proposal_id)
ORDER BY g.created_at DESC;
```

`inference_jobs.status`가 계속 `queued`에 머물러 있고 `attempt_count`
(`inference_dispatches`)만 계속 늘어나면 아직 워커 쪽에서 막혀 있다는 뜻이다 —
이번에는 `diagnosis-worker.log`에 진짜 예외 메시지가 찍히므로 그걸 보고 원인을
좁힌다.

### 14.3 Unity 담당자에게 전달할 최종 체크리스트

1. 제어 WS(`/api/v1/control`)로 요청 보내면 **밀리초 내** `request.accepted` 옴 — 이건 "접수"일 뿐, 결과 아님.
2. 결과는 반드시 **별도의** 스트림 WS(`/api/v1/stream?run_id=...`)에서 비동기로 옴. 같은 커넥션에서 기다리면 안 됨.
3. `anomaly_detected=true` + 유효 후보가 있을 때만 `tcad.verification.*` 이벤트가 추가로 옴 — 안 오는 게 정상인 경우도 있음(§4 참고).
4. 결과가 안 오면 Unity 쪽 문제가 아닐 수 있다 — 위 14.2 SQL로 Gateway/워커 쪽 상태부터 확인 요청.
5. 운영 Unity(`UNITY_MODE=prod`)에서는 mock TCAD 검증 결과 승인이 차단된다 — 테스트 중 승인 버튼이 안 눌리면 이것부터 확인.

## 15. 참고 문서

- `docs/runbooks/surrogate-ml-websocket-e2e.md` — 전기적 ML WS E2E 상세 절차
- `docs/runbooks/diagnosis-ml-e2e.md` — 진단 모델 실제 전환 절차
- `docs/runbooks/tcad-verification-service-e2e.md` — TCAD 검증 큐 상세 절차
- `docs/runbooks/full-mock-process.md` — 전체 mock 공정 통합 실행
- `docs/architecture/ml-integration-contract.md` — ML 계약과 책임 경계
- `docs/architecture/jetson-ros2-tcad-unity-integration.md` — 모드 플래그와 전체 아키텍처
