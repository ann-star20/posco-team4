# 인터페이스 정의서 (Interface Definition Document)

- 기준일: 2026-10-23
- 대상 시스템: Virtual Fab (Unity ↔ Gateway ↔ Jetson ↔ TCAD 워크스테이션)
- 1차 출처: `docs/api/openapi.yaml`(3.1.0), `docs/api/asyncapi.yaml`(2.6.0) — 두 계약 문서에 선언된 스키마/오류코드/`x-implementation-status`를 그대로 인용한다.
- 2차 검증: 실제 구현 소스(`services/event_gateway/src/event_gateway/app.py`, `tcad_client.py`, `tcad_candidate_worker.py`, `tcad_service/app.py`)를 대조해, 계약 문서와 실제 코드가 불일치하는 지점을 "문서화 격차"로 별도 표기했다.
- 표기: **구현** = 실제 코드 경로 존재·동작 확인 / **모크** = mock 서버만 응답, prod 백엔드는 미연결 / **스캐폴드** = 엔드포인트는 존재하나 항상 503/404만 반환 / **미문서화** = 코드에는 있지만 OpenAPI/AsyncAPI에 없음

---

## 1. 인터페이스 경계 개요

| # | 경계 | 프로토콜 | 호스트:포트(기본값) | 인증 | 상태 |
|---|------|---------|------|------|------|
| 1 | Unity ↔ Jetson Camera Preview | WebSocket | `{JETSON_HOST}:8500` | `api_token`(body) | 구현 |
| 2 | Unity ↔ Jetson AOI 직접검사 | WebSocket | `{JETSON_HOST}:8400` | `api_token`(body) | 구현 |
| 3 | Unity ↔ Gateway 중앙 제어 | WebSocket | `{gatewayHost}:8000` | `X-Unity-Token`(header) | 구현 |
| 4 | Unity ↔ Gateway 이벤트 스트림/리플레이 | WebSocket + REST | `{gatewayHost}:8000` | REST 없음 / WS 없음 | 구현 |
| 5 | Unity ↔ Gateway 작업 생성·조회 | REST | `{gatewayHost}:8000` | `X-Unity-Token`(header) | 구현 |
| 6 | Unity ↔ Gateway 보정 명령 전달 | WebSocket | `{gatewayHost}:8000` | `X-Unity-Token`(header) | 구현 |
| 7 | 운영자 ↔ Gateway 레거시 승인 | REST | `{gatewayHost}:8000` | `X-Approval-Token`(header) + 승인자 식별자 | 구현 (별도 경로, 6과 불연결) |
| 8 | Unity ↔ Gateway TCAD 후보 승인(풀링) | REST | `{gatewayHost}:8000` | `X-Unity-Token`(header) | 구현, **미문서화** |
| 9 | Gateway ↔ TCAD 워크스테이션 (신규, request-id keyed) | REST | `{tcadHost}:8200` | `X-Fab-Token`(header) | 구현 |
| 10 | Gateway ↔ TCAD 워크스테이션 (레거시, job-id keyed) | REST | `{tcadHost}:8200` | 없음 | 스캐폴드 (항상 503/404) |
| 11 | Unity ↔ Jetson Surrogate 모델 | REST | `{surrogateHost}:8300` | 없음(계약상 미정의) | 모크 |
| 12 | Gateway ↔ Jetson ROS 2 토픽 | ROS 2 DDS (domain) | `ROS_DOMAIN_ID` 공유 | HMAC-SHA256(`command_mac`, 명령 토픽만) | 구현 |

---

## 2. REST 인터페이스

### 2.1 Gateway 작업 생성/조회 (Unity → Gateway)

| Method | Path | 설명 | 인증 | 요청 스키마 | 응답(성공) | 오류 | 상태 |
|---|---|---|---|---|---|---|---|
| GET | `/health/live` | 프로세스 생존 확인 | 없음 | - | `{status:"ok"}` | - | 구현 |
| POST | `/api/v1/inspection-jobs` | AOI 접수형 작업 생성 | `X-Unity-Token` | `InspectionRequest` | 202 `JobAccepted{job_id,status:queued}` | 400/401/409/503 | 구현 |
| POST | `/api/v1/surrogate-jobs` | 간이 원인분석 ML 작업 생성 | `X-Unity-Token` | `SurrogateJobRequest` | 202 `JobAccepted` | 401/409/503 | 구현 |
| POST | `/api/v1/diagnosis-jobs` | 진단(diagnosis) ML 작업 생성 — TCAD 보정 후보 산출의 입구 | `X-Unity-Token` | `SurrogateJobRequest`를 상속한 `DiagnosisRequest`(`stage_id` 기본값만 `diagnosis`로 다름) | 202 `JobAccepted` | 401/409/503 | 구현, **미문서화**(OpenAPI에 `/api/v1/diagnose`로도 `/api/v1/diagnosis-jobs`로도 없음 — `app.py:126`) |
| GET | `/api/v1/jobs/{job_id}` | AOI/Surrogate/Diagnosis 작업 상태 조회 | `X-Unity-Token` | - | `JobStatus{job_id,request_id,run_id,status,result_event_id}` | 401/404 | 구현 |
| GET | `/api/v1/inspection-jobs/{job_id}` | `GET /api/v1/jobs/{job_id}`의 구버전 호환 경로(동일 핸들러) | `X-Unity-Token` | - | 동일 | 401/404 | 구현, deprecated |
| GET | `/api/v1/events?run_id&after_sequence&limit` | Aiven 커밋 이벤트 재생 | 없음(쿼리만) | - | `{events:[StoredEvent...]}` | 400 | 구현 |

**JobStatus.status 상태 전이**: `queued → dispatching → accepted → running → {completed\|failed\|cancelled}` (app.py/inference_jobs.py 기준. OpenAPI enum과 일치).

### 2.2 레거시 보정 승인 (운영자 → Gateway, `correction_proposals` 경로)

| Method | Path | 설명 | 인증 | 요청 | 응답 | 오류 |
|---|---|---|---|---|---|---|
| POST | `/api/v1/proposals/{proposal_id}/approval` | `correction_proposals`에 등록된, TCAD로 검증된 보정 후보를 승인 | `X-Approval-Token` + `approved_by`가 `settings.approval_operator`와 일치해야 함(`app.py:252`) | `ApprovalRequest{approved_by, effective_from_lot}` | 200 `{command_id, status:"pending"}` | 400/401/403/409/503 | 구현 |

승인되면 `commands` 테이블에 레코드가 생성되고, `GET /api/v1/commands`(WebSocket, §3.6)를 통해 Unity에 푸시된다. **이 경로는 `tcad_proposal_groups` 기반 신규 경로(§2.3)와 완전히 분리되어 있으며 서로 연결되지 않는다** — 두 보정 승인 메커니즘이 공존하는 것은 설계상 미해결 항목이다(`requirements-definition.md` §8 참조).

### 2.3 TCAD 후보 승인 — Unity 풀링 방식 (신규, `tcad_proposal_groups` 경로)

**OpenAPI에 아직 선언되지 않은 구현된 엔드포인트.** `app.py:267-342` 기준으로 정의한다.

#### `GET /api/v1/tcad/proposals?status=review_required`

- 인증: `X-Unity-Token`
- 쿼리: `status` (기본값 `review_required`; `tcad_proposal_groups.status` CHECK 제약과 동일한 enum: `queued, running, completed, failed, cancelled, review_required`)
- 응답 200:
```json
{
  "proposals": [
    {
      "proposal_id": "uuid",
      "job_id": "uuid",
      "run_id": "uuid",
      "status": "review_required",
      "created_at": "ISO-8601",
      "candidates": [
        {
          "tcad_request_id": "uuid",
          "candidate_index": 0,
          "process_parameters": {"body_dose": 0, "epi_doping": 0, "oxide_thickness": 0},
          "result_payload": {"vth": 0, "gm": 0, "id_on": 0, "bv": 0},
          "spec_verdict": {"vth_pass": true, "bv_pass": true, "overall": "in_spec", "spec_source": "datasheet_AOI4184"}
        }
      ]
    }
  ]
}
```
- `spec_verdict.overall` enum: `in_spec | out_of_spec | bv_unconfirmed | spec_unavailable` (`tcad_candidate_worker.py:17-25`의 `evaluate_spec`).

#### `POST /api/v1/tcad/proposals/{proposal_id}/decision`

- 인증: `X-Unity-Token`
- 요청(`TcadDecisionRequest`):
```json
{"decided_by": "string(min 1)", "decision": "approved|rejected", "selected_tcad_request_id": "uuid|null"}
```
  - `decision=approved`일 때 `selected_tcad_request_id`는 필수이며, 반드시 해당 `proposal_id`에 속한 후보여야 한다. 아니면 400.
  - `proposal_id`가 `tcad_proposal_groups.status='review_required'`가 아니면 404 (이미 결정됐거나 존재하지 않음).
- 응답 200:
  - 승인: `{"proposal_id","status":"approved","process_parameters":{...}}` — 그룹은 `completed`로 전환, `approved_by`/`approved_at`/`selected_tcad_request_id` 기록. **응답 본문의 `process_parameters`가 Unity가 바로 적용할 공정값이며, 별도의 명령 디스패치(§2.2의 `/commands` 경로)를 타지 않는다.**
  - 거부: `{"proposal_id","status":"rejected","process_parameters":null}` — 그룹은 `failed`로 전환.
  - 감사 이벤트 `tcad.verification.decided`가 `run_id` 기준으로 기록됨.
- 오류: 400(선택 후보 없음/후보가 그룹에 속하지 않음), 401, 404.

### 2.4 Gateway ↔ TCAD 워크스테이션 (신규, request-id keyed — 실제 사용 중인 경로)

`services/event_gateway/src/event_gateway/tcad_client.py`의 `TcadCandidateClient`가 사용하는 계약. Gateway의 `verification-worker` 프로세스(`tcad_candidate_worker.py`)가 polling 루프로 호출한다.

| Method | Path | 인증 | 요청 | 응답 | 상태 |
|---|---|---|---|---|---|
| POST | `/api/v1/tcad/verify` | `X-Fab-Token` | `TcadCandidateVerificationRequest{request_id, job_id?, run_id?, lot_id?, process_parameters, requested_outputs:[vth,gm,id_on,bv], predicted_outputs?, options:{timeout_seconds}}` | 202 `TcadCandidateAccepted{request_id, status:"queued", queue_position, estimated_seconds, accepted_at}` | 구현(`x-implementation-status: implemented`, OpenAPI에 등재됨) |
| GET | `/api/v1/tcad/jobs/{request_id}` | `X-Fab-Token` | - | 200 `TcadCandidateJobStatus{request_id,status,queue_position?,progress?,result_payload?,prediction_error?,metadata?,error_code?,error_message?,cancelled_at?}` | 구현 |

`status` enum(OpenAPI): `queued, running, succeeded, failed, cancelled`. 게이트웨이 쪽 DB enum(`tcad_verification_candidates.status`)은 이보다 넓다 — `pending, submitting, queued, running, succeeded, failed, cancelled, expired` (`pending`/`submitting`/`expired`는 게이트웨이 내부 상태이며 TCAD 서버 쪽 enum에는 없다. 폴링 대상이 되기 전 단계이거나 데드라인 초과로 게이트웨이가 자체 판단한 상태다).

### 2.5 Gateway ↔ TCAD 워크스테이션 (레거시, job-id keyed — 스캐폴드)

| Method | Path | 상태 |
|---|---|---|
| GET | `/health/ready` | 스캐폴드, 항상 503 `{code:"backend_not_configured"}` (`tcad_service/app.py:21`) |
| POST | `/api/v1/verifications` | 스캐폴드, 항상 503 |
| GET | `/api/v1/verifications/{job_id}` | 스캐폴드, 항상 404 `{code:"job_not_found"}` |

이 경로는 `verification_jobs`/`correction_proposals` 테이블을 쓰는 레거시 `VerificationWorker._run_legacy_once()`(`verification_worker.py:34`)가 호출하지만, 실제 TCAD 서비스(`tcad_service/app.py`)는 "절대 모의 prod 결과를 생성하지 않는다"는 명시적 설계로 항상 실패를 반환한다. **실사용 경로가 아니다** — §2.4가 실사용 경로다.

### 2.6 Jetson Surrogate 모델 (모크)

| Method | Path | 인증 | 상태 |
|---|---|---|---|
| POST | `/api/v1/predict` | OpenAPI에 보안 스키마 미정의 | 모크만 응답(`http://127.0.0.1:8300`), 실제 Jetson 모델 서비스(`{surrogateHost}:{surrogatePort}`)는 미연결 |

---

## 3. WebSocket 인터페이스

### 3.1 `/camera/preview` (Jetson, 저지연 미리보기)
- 방향: Unity → 구독(`camera.preview.subscribe`, body에 `api_token`) → Jetson이 `camera.preview.subscribed`(JSON 메타) 후 `camera.preview.frame`(JSON) + 바로 뒤따르는 binary JPEG 프레임을 반복 송신.
- 정책: latest-only — 느린 클라이언트의 이전 프레임은 폐기.
- 상태: 구현.

### 3.2 `/aoi` (Jetson, 직접 AOI 검사)
- Unity → `aoi.inspection.requested`(JSON, `api_token` 포함).
- Jetson → `aoi.inspection.accepted` → `aoi.inspection.completed`(JSON 메타) + 바로 뒤 binary `aoi.annotated.jpeg`, 또는 `aoi.inspection.rejected`/`aoi.inspection.failed`.
- 주의: `aoi.inspection.completed.persistence_status: queued`는 Jetson SQLite outbox 저장 완료일 뿐 Aiven DB commit을 의미하지 않는다.
- 상태: 구현.

### 3.3 `/api/v1/control` (Gateway, 중앙 제어)
- 인증: 연결 시 `X-Unity-Token` 헤더 필수.
- Unity → `inspection.requested` | `surrogate.requested` | `diagnosis.requested`(`type` 필드로 분기, `app.py:162-170`).
- Gateway → `request.accepted{request_id,job_id,status}` 또는 `request.rejected{code}` (`code`는 `unsupported_type`/`invalid_request` 문자열 또는 400/409/503 정수).
- **문서화 격차**: AsyncAPI의 `GatewayInspectionRequested`/`GatewaySurrogateRequested`만 선언돼 있고 `diagnosis.requested`(`DiagnosisRequest`) 메시지는 스키마가 없다 — 실제로는 `app.py`에서 세 타입 모두 처리한다.

### 3.4 `/api/v1/stream` (Gateway, 이벤트 재생)
- 쿼리: `run_id`(필수), `after_sequence`(기본 0).
- Gateway → `StoredEvent` 연속 송신(sequence 순서), 신규 이벤트 없으면 폴링 대기.
- 상태: 구현.

### 3.5 `/api/v1/events` — REST (WebSocket 아님, §2.1 참조)

### 3.6 `/api/v1/commands` (Gateway, 보정 명령 전달 — 레거시 경로 전용)
- 인증: 연결 시 `X-Unity-Token` 헤더 + 쿼리 `run_id` 필수.
- Gateway → `correction.command`(§2.2에서 승인된 명령을 `command_dispatcher.claim_due_commands`로 폴링해 푸시).
- Unity → `correction.applied{command_id,proposal_id,run_id,effective_from_lot}` → Gateway가 `application.ack` 또는 형식 오류 시 `application.rejected` 응답.
- **이 채널은 §2.3(TCAD 풀링 승인)에서 승인된 공정값을 전달하지 않는다** — §2.3은 POST 응답 본문으로 직접 반환한다. 두 경로가 불연결이라는 점은 §2.2에서도 언급한 핵심 아키텍처 특징이다.

### 3.7 ROS 2 DDS 토픽 (Gateway ↔ Jetson)

| 토픽 | 방향 | 메시지 | 비고 |
|---|---|---|---|
| `/fab/inference_requests` | Gateway → Jetson | `RosAoiRequestPayload` | AOI 작업 디스패치 |
| `/fab/surrogate_requests` | Gateway → Jetson | `RosSurrogateRequestPayload` | Surrogate/Diagnosis 작업 디스패치(`RosAoiRequestPayload`를 확장, `task_type` 분기) |
| `/fab/events` | Jetson → Gateway | `RosEventEnvelope` | at-least-once, `event_id`로 멱등 처리. DB ACK 전까지 Jetson이 재발행 가능 |
| `/fab/event_acks` | Gateway → Jetson | `RosEventAckPayload{event_id,run_id,sequence?,status:committed\|dead_lettered}` | Jetson outbox 정리 신호 |
| `/fab/commands` | Gateway → Jetson | `CorrectionCommandBody` + `command_mac`(HMAC-SHA256, 64자 hex) | 가상 공정 명령. `command_mac`은 인증/변조 방지용이며 로그에 노출 금지 |

전송: `std_msgs/msg/String`(JSON UTF-8 payload), QoS depth 10, ROS 2 Humble, 양쪽 `ROS_DOMAIN_ID` 일치 필요.

---

## 4. 보안/인증 경계 요약

| 토큰 | 헤더/위치 | 적용 범위 | 비교 방식 |
|---|---|---|---|
| `X-Unity-Token` | HTTP 헤더 / WS 연결 헤더 | `/api/v1/*-jobs`, `/api/v1/jobs/{id}`, `/api/v1/control`, `/api/v1/commands`, `/api/v1/tcad/proposals(/decision)` | `secrets.compare_digest` (`app.py:83`), 토큰 미설정 시 503 |
| `X-Approval-Token` | HTTP 헤더 | `/api/v1/proposals/{id}/approval` | `secrets.compare_digest` + `approved_by == settings.approval_operator` 이중 검증 |
| `X-Fab-Token` | HTTP 헤더 | `/api/v1/tcad/verify`, `/api/v1/tcad/jobs/{id}` (Gateway→TCAD 방향) | TCAD 서버 측 검증(게이트웨이는 발신만) |
| `api_token` (body) | WS 메시지 본문 | `/camera/preview`, `/aoi` (Jetson 엔드포인트) | Jetson 쪽 구현, 로그 노출 금지 명시 |
| `command_mac` | 메시지 필드 | `/fab/commands` ROS 토픽만 | HMAC-SHA256, write-only |

인증이 전혀 없는 경계: `/api/v1/events`(REST, 쿼리 `run_id`만으로 조회 — 토큰 불요), `/api/v1/stream`(WS), `/health/live`, `/api/v1/predict`(모크).

---

## 5. 문서화 격차 (OpenAPI/AsyncAPI ↔ 실제 구현)

| 격차 | 내용 | 영향 |
|---|---|---|
| `/api/v1/diagnosis-jobs` 미등재 | `app.py:126`에 구현돼 있으나 `openapi.yaml`에 path 없음 | 외부 연동자가 계약 문서만 보고는 진단 작업 생성 경로를 알 수 없음 |
| `GET/POST /api/v1/tcad/proposals(/decision)` 미등재 | §2.3 전체가 `openapi.yaml`에 없음 (가장 최근에 구현된 Unity 승인 경로) | 가장 최근 기능이 계약 문서에서 완전히 빠져 있음 — 다음 OpenAPI 갱신 시 최우선 추가 대상 |
| `diagnosis.requested` WS 메시지 스키마 없음 | `asyncapi.yaml`의 `/api/v1/control`에 `inspection.requested`/`surrogate.requested`만 선언 | §3.3 참조 |
| `tcad_verification_candidates.status` enum 불일치 | OpenAPI `TcadCandidateJobStatus.status`는 5개 값, 실제 DB는 8개 값(`pending/submitting/expired` 추가) | §2.4 참조. API 응답과 내부 상태 모델이 다르다는 점을 연동 문서에 명시해야 함 |

---

## 6. 관련 문서

- `docs/architecture/current-system-architecture.md` — 시퀀스 다이어그램 및 전체 데이터 흐름
- `docs/requirements/requirements-definition.md` — FR/NFR 추적성 매트릭스
- `docs/api/openapi.yaml`, `docs/api/asyncapi.yaml` — 원본 계약 (본 문서는 이들의 해설 + 실제 구현 대조본)
