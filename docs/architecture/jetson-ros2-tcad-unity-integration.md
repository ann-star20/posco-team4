# Jetson ROS 2 · TCAD · PostgreSQL · Unity 통합 설계

작성일: 2026-10-14  
상태: 검토 요청

## 1. 목적

가상 팹에서 Jetson Orin Nano가 생성한 이상 감지·진단·보정 후보를 Windows WSL Gateway가 수신하고, PostgreSQL에 영구 저장한 뒤 별도 워크스테이션의 TCAD로 검증 요청한다. TCAD 검증 결과와 보정 데이터는 다시 PostgreSQL에 저장한 후 Unity에 실시간 전달한다.

## 2. 확정된 환경

- Jetson: Ubuntu 22.04, JetPack 6.2.1, ARM64
- ROS 2: Jetson과 Windows WSL 사이 DDS 토픽 송수신 확인 완료
- 확인 토픽: `/fab/events`, `std_msgs/msg/String`
- Gateway: Windows WSL에서 ROS 2 토픽 구독, HTTP API 및 WebSocket 제공
- PostgreSQL: Windows 측 로컬 컨테이너, 실제 접속 정보는 `.env`에서 관리
- TCAD: 별도 워크스테이션에서 HTTP 서비스로 제공
- Unity: Gateway의 HTTP API와 WebSocket만 사용

## 3. 설계 원칙

1. Jetson의 OS, JetPack, CUDA, ROS 2, DDS, 방화벽, 시스템 Python 설정을 변경하지 않는다.
2. Jetson에서는 `/home/jetson/project/smart_factory` 아래의 프로젝트 파일만 생성·수정한다.
3. 시스템 패키지 설치, `/opt/ros` 수정, systemd 등록은 별도 승인 없이는 수행하지 않는다.
4. PostgreSQL이 영구 상태와 감사 기록의 단일 진실 원천이다.
5. DB 커밋이 완료된 뒤에만 TCAD 요청 또는 Unity 알림을 진행한다.
6. Unity와 Jetson은 PostgreSQL에 직접 접속하지 않는다.
7. 비밀번호·IP·DB URL은 Git에 커밋하지 않고 `.env`로만 관리한다.
8. 이벤트와 명령은 UUID로 멱등 처리한다.

## 4. 전체 구조

```mermaid
flowchart LR
  subgraph JT["Jetson Orin Nano"]
    SIM["가상 로트/ML"] --> PUB["ROS 2 Publisher"]
    CMD["ROS 2 Command Subscriber"] --> SIM
  end

  subgraph GW["Windows WSL"]
    SUB["ROS 2 Gateway Node"] --> API["Event Gateway"]
    API <--> PG[("PostgreSQL")]
    API --> OUT["TCAD HTTP Client"]
    API --> WS["Unity WebSocket"]
  end

  subgraph TW["TCAD 워크스테이션"]
    TA["TCAD HTTP Service"] --> SIL["Silvaco TCAD"]
  end

  subgraph UP["Unity PC"]
    UN["Unity 가상 팹"]
  end

  PUB -- "/fab/events" --> SUB
  API -- "/fab/commands" --> CMD
  OUT -- "HTTP 검증 요청/조회" --> TA
  TA -- "HTTP 결과" --> API
  WS -- "저장 완료 이벤트" --> UN
  UN -- "HTTP 이상 주입/승인" --> API
```

## 5. 프로토콜 선택

### ROS 2

Jetson과 WSL Gateway 사이의 실시간 이벤트 및 명령에 사용한다. DDS 연결이 이미 검증됐으므로 추가 네트워크 설정을 하지 않는다.

- Jetson → Gateway: `/fab/events`
- Gateway → Jetson: `/fab/commands`
- 초기 메시지 타입: `std_msgs/msg/String` JSON
- 스키마 안정화 후 전용 메시지 타입 전환 검토

ROS 2 수신 자체는 영구 보존이 아니므로 Gateway는 이벤트를 수신하는 즉시 PostgreSQL에 저장한다.

### HTTP

Gateway와 별도 TCAD 워크스테이션 사이에 사용한다. TCAD 실행은 오래 걸릴 수 있으므로 동기 응답을 기다리지 않는 비동기 작업 API로 설계한다.

### WebSocket

Gateway가 PostgreSQL에 커밋된 상태 변경을 Unity에 실시간 전달할 때 사용한다. Unity 연결이 끊기면 마지막 `sequence` 이후 이벤트를 HTTP로 재조회한다.

## 6. 처리 상태와 이벤트

| 순서 | 이벤트 | 의미 |
|---:|---|---|
| 1 | `anomaly.detected` | 측정 출력이 정상 범위를 벗어남 |
| 2 | `diagnosis.completed` | 예상 원인과 확률 계산 완료 |
| 3 | `correction.proposed` | 제어 가능한 노브의 보정 후보 생성 |
| 4 | `verification.requested` | TCAD 작업 생성 및 요청 준비 |
| 5 | `verification.accepted` | TCAD가 작업을 접수하고 `job_id` 반환 |
| 6 | `verification.completed` | TCAD 계산 결과 수신 |
| 7 | `correction.verified` | 출력 스펙을 모두 만족한 후보 |
| 8 | `correction.rejected` | TCAD 검증에 실패한 후보 |
| 9 | `correction.approved` | 사람이 검증된 보정안을 승인 |
| 10 | `correction.applied` | 다음 가상 로트 설정에 반영 완료 |

각 이벤트는 `event_id`, `correlation_id`, `causation_id`, `occurred_at`, `source`, `payload`를 가진다. `correlation_id`는 하나의 로트 진단·보정·검증 흐름 전체에서 유지한다.

## 7. 공정 변수 계약

혼동을 피하기 위해 입력과 출력을 분리한다.

- `x_current`: 현재 공정 노브
- `delta_x`: 보정 변화량
- `x_candidate`: TCAD에 적용할 후보값 (`x_current + delta_x`)
- `y_observed`: 이상 로트에서 관측한 출력
- `y_predicted`: 서로게이트가 후보에 대해 예측한 출력
- `y_verified`: TCAD가 계산한 출력
- `targets`: 합격 범위

공정 노브의 API 키는 다음으로 고정한다.

- `oxide_thickness`
- `body_dose`
- `diffusion_time`
- `epi_doping`

출력 키는 `vth`, `gm`, `id_on`, `bv`로 고정한다. 값은 물리 단위와 기준값 대비 비율을 혼용하지 않는다. 초기 데모가 비율을 사용하면 모든 값에 `representation: "normalized_ratio"`를 명시한다.

## 8. ROS 2 이벤트 예시

```json
{
  "schema_version": 1,
  "event_id": "0199f0a4-5a8c-7b8e-9c10-0123456789ab",
  "event_type": "correction.proposed",
  "source": "jetson.correction_agent",
  "occurred_at": "2026-10-14T06:30:00.123Z",
  "correlation_id": "LOT-2026-0012",
  "causation_id": "0199f09f-1111-7222-8333-444444444444",
  "payload": {
    "representation": "normalized_ratio",
    "expected_causes": [
      {"name": "body_dose_shift", "probability": 0.82}
    ],
    "x_current": {
      "oxide_thickness": 1.0,
      "body_dose": 1.0,
      "diffusion_time": 1.0,
      "epi_doping": 1.0
    },
    "delta_x": {
      "oxide_thickness": -0.03,
      "body_dose": 0.05,
      "diffusion_time": 0.0,
      "epi_doping": 0.0
    },
    "x_candidate": {
      "oxide_thickness": 0.97,
      "body_dose": 1.05,
      "diffusion_time": 1.0,
      "epi_doping": 1.0
    },
    "y_observed": {
      "vth": 1.08,
      "gm": 0.94,
      "id_on": 0.91,
      "bv": 0.99
    }
  }
}
```

## 9. TCAD 비동기 HTTP 계약

### 작업 요청

`POST ${TCAD_API_URL}/api/v1/verifications`

Gateway는 `correction.proposed`와 `verification.requested`를 하나의 DB 트랜잭션으로 저장한 뒤 TCAD를 호출한다.

```json
{
  "request_id": "0199f0b0-1111-7222-8333-555555555555",
  "correlation_id": "LOT-2026-0012",
  "device": "AOD4184A",
  "representation": "normalized_ratio",
  "x_current": {},
  "delta_x": {},
  "x_candidate": {},
  "y_observed": {},
  "targets": {},
  "model_version": "surrogate-2026-10-14",
  "deck_template_version": "aod4184a-v1"
}
```

TCAD 서비스는 계산을 기다리지 않고 `202 Accepted`와 `job_id`를 반환한다. 동일 `request_id` 재요청은 같은 작업을 반환한다.

### 결과 조회

`GET ${TCAD_API_URL}/api/v1/verifications/{job_id}`

상태는 `queued`, `running`, `succeeded`, `failed` 중 하나다. `succeeded`이면 `y_verified`, 실행 시간, deck 버전, 로그 참조를 반환한다. Gateway는 백오프 폴링으로 결과를 조회한다. 콜백은 인증 설계가 확정될 때까지 사용하지 않는다.

## 10. Unity 전달 계약

Unity에는 TCAD 요청 전의 잠정 후보와 검증 완료 결과를 구분해 보낸다.

- `correction.proposed`: UI에 “검증 중”으로 표시하며 승인 불가
- `correction.verified`: 현재값, 변화량, 권장값, TCAD 출력 표시 및 승인 가능
- `correction.rejected`: 실패 원인과 TCAD 출력 표시, 승인 불가

Unity는 ROS 2에 참여하지 않는다. Gateway WebSocket의 커밋 완료 이벤트만 받고, 명령은 Gateway HTTP API로 보낸다.

## 11. 승인과 Jetson 명령

Unity가 `verified` 보정안을 승인하면 Gateway가 승인 내역을 DB에 먼저 저장한 뒤 `/fab/commands`에 다음 명령을 발행한다.

```json
{
  "schema_version": 1,
  "command_id": "0199f0c0-1111-7222-8333-666666666666",
  "command_type": "correction.apply",
  "correlation_id": "LOT-2026-0012",
  "proposal_id": "0199f0b0-aaaa-bbbb-cccc-777777777777",
  "x_candidate": {},
  "effective_from_lot": "LOT-2026-0013"
}
```

Jetson은 적용 후 같은 `command_id`를 포함한 `correction.applied` 이벤트를 `/fab/events`로 회신한다. Gateway는 회신 전까지 명령을 완료로 처리하지 않는다.

## 12. 환경변수와 비밀 관리

실제 값은 저장소 루트의 `.env`에만 두고 `.gitignore`로 제외한다. Git에는 `.env.example`만 포함한다.

```dotenv
# Windows/WSL Gateway
DATABASE_URL=postgresql://USER:PASSWORD@HOST:PORT/DATABASE
GATEWAY_HTTP_HOST=0.0.0.0
GATEWAY_HTTP_PORT=8000
UNITY_WS_PATH=/api/v1/stream

# TCAD workstation
TCAD_API_URL=http://TCAD_HOST:PORT
TCAD_REQUEST_TIMEOUT_SECONDS=10
TCAD_POLL_INTERVAL_SECONDS=5

# ROS 2
ROS_DOMAIN_ID=0
ROS_EVENT_TOPIC=/fab/events
ROS_COMMAND_TOPIC=/fab/commands

# SSH deployment; local operator use only
JETSON_HOST=JETSON_CURRENT_IP
JETSON_USER=JETSON_USER
JETSON_PASSWORD=LOCAL_SECRET_ONLY
JETSON_PROJECT_PATH=/home/jetson/project/smart_factory
```

문서와 로그에는 `DATABASE_URL`, `JETSON_PASSWORD`의 실제 값을 출력하지 않는다. Jetson IP가 바뀌면 `.env`의 `JETSON_HOST`만 변경한다. 장기적으로 SSH 키 인증으로 전환하되 이번 범위에서 Jetson SSH 설정은 변경하지 않는다.

## 13. DB 추가 모델

기존 `events`에 더해 다음 테이블을 둔다.

- `correction_proposals`: `x_current`, `delta_x`, `x_candidate`, 예측 출력과 상태
- `verification_jobs`: TCAD `request_id`, `job_id`, 요청·결과 JSON, 상태, 재시도 시각
- `commands`: Unity 승인으로 생성된 Jetson 명령, 발행·확인 상태

도메인 행 변경과 감사 이벤트 삽입은 같은 PostgreSQL 트랜잭션으로 처리한다.

## 14. 장애 처리

- 잘못된 ROS JSON: DB에 저장하지 않고 구조화 로그 기록, 다음 메시지 계속 처리
- 동일 `event_id`: 내용이 같으면 기존 `sequence` 반환, 다르면 충돌 기록
- TCAD 연결 실패: DB 작업을 `queued`로 유지하고 백오프 재시도
- TCAD 응답 유실: 동일 `request_id`로 재요청 또는 `job_id` 조회
- Gateway 재시작: DB의 `queued`·`running` 검증 작업을 재개
- Unity 단절: DB에는 영향 없음, 재연결 후 `sequence` 기반 누락 복구
- ROS 명령 유실: `commands`의 미확인 항목을 재발행하고 `command_id`로 중복 적용 방지

## 15. Jetson 안전 배포 절차

1. 읽기 전용으로 OS, ROS 2, 토픽, 디스크 공간, 프로젝트 경로 확인
2. 기존 프로젝트 파일 목록과 Git 상태 확인
3. `/home/jetson/project/smart_factory` 밖에는 쓰지 않음
4. 기존 파일을 덮어써야 하면 diff를 제시하고 승인 후 변경
5. `colcon build --packages-select <package>`로 대상 패키지만 빌드
6. 임시 셸에서만 `source install/setup.bash`
7. 테스트 publisher/subscriber로 통신 검증
8. 재부팅·서비스 등록·시스템 설정 변경은 수행하지 않음

## 16. TDD 완료 기준

1. Jetson publisher의 정상 JSON이 WSL Gateway를 거쳐 PostgreSQL에 한 번 저장된다.
2. 잘못된 메시지 뒤에도 다음 정상 메시지를 처리한다.
3. 동일 이벤트 재수신 시 중복 행이 생기지 않는다.
4. 보정 후보 저장 후 TCAD 작업이 `202`로 접수된다.
5. TCAD가 중단됐다가 복구돼도 작업이 재개된다.
6. 검증 결과가 DB에 저장된 뒤 Unity에 전달된다.
7. Unity는 `verified`가 아닌 보정안을 승인할 수 없다.
8. 승인 명령이 Jetson에 전달되고 동일 `command_id`는 한 번만 적용된다.
9. Jetson 시스템 설정 변경 없이 프로젝트 경로의 코드만으로 전체 데모가 동작한다.

## 17. 구현 순서

1. `.env.example`과 설정 로더
2. ROS 2 이벤트·명령 계약
3. WSL ROS 2 subscriber와 PostgreSQL 저장
4. TCAD 작업 테이블과 비동기 HTTP 클라이언트
5. TCAD 결과 처리와 보정 상태 전이
6. Gateway WebSocket과 Unity 보정 데이터 계약
7. Unity 승인 API와 ROS 2 command publisher
8. Jetson command subscriber와 적용 ACK
9. 실제 Jetson·TCAD mock·Unity mock 통합 시험
