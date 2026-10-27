# Surrogate and Diagnosis Service Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jetson의 fab-ml-v1 v1.1.0 서로게이트·진단 서비스를 ROS 2, Gateway, Aiven DB, Unity 및 TCAD 검증 흐름에 안전하게 통합한다.

**Architecture:** Gateway는 서로게이트와 진단 작업을 별도 ROS 토픽으로 dispatch하고, Jetson의 독립 Worker가 같은 모델 서비스의 `/predict`와 `/diagnose`를 호출한다. 원형 응답과 실행 메타데이터를 원자적으로 저장하며 `tcad_verify`인 유효한 3변수 후보만 TCAD 어댑터로 전달한다.

**Tech Stack:** Python 3.10, FastAPI, Pydantic v2, ROS 2 Humble/rclpy, httpx, PostgreSQL/Aiven, SQLite outbox, pytest

**Spec:** `docs/superpowers/specs/2026-10-21-surrogate-diagnosis-service-integration-design.md`

## Global Constraints

- 계약 버전은 `fab-ml-v1`, 모델 서비스 버전은 `1.1.0`이다.
- 모델 서비스는 Jetson에서 실행하며 Gateway는 모델 전처리나 GP 단계를 구현하지 않는다.
- 공정 입력은 `body_dose`, `epi_doping`, `oxide_thickness` 세 개이며 `diffusion_time`을 합성하지 않는다.
- 진단 route는 `tcad_verify`, `no_action`, `manual`만 허용한다.
- `high_confidence`는 TCAD 생략에 사용하지 않는다.
- TCAD 검증과 관리자 승인 전에는 보정 명령을 생성하지 않는다.
- mock과 prod는 동일 계약을 사용하고 환경변수만 다르게 한다.
- 기존 AOI·카메라 변경 및 사용자의 미커밋 파일을 수정하거나 정리하지 않는다.

## Review Focus

- HTTP 200인 `OUT_OF_DOMAIN/status=failed`가 성공으로 오인되지 않고 실패 결과로 저장되는지 Task 2·5에서 시험한다.
- `route=tcad_verify`인데 proposal이 null 또는 무효인 경우 TCAD가 호출되지 않는지 Task 5에서 시험한다.
- 중복 ROS 결과와 Worker 재시작이 결과·실행 행을 중복 생성하지 않는지 Task 3·5에서 시험한다.
- 서로게이트와 진단이 동시에 막혀도 서로의 실행기를 차단하지 않는지 Task 3에서 시험한다.
- `git_commit=null`, 세부 단계 시간 누락, `temperature_c=26.85`가 유효하게 보존되는지 Task 1·4에서 시험한다.

---

### Task 1: fab-ml-v1 응답 계약

**Files:**
- Create: `services/event_gateway/src/event_gateway/ml_contracts.py`
- Create: `services/event_gateway/tests/unit/test_ml_contracts.py`
- Modify: `services/event_gateway/src/mock_surrogate/app.py`

**Interfaces:**
- Consumes: 모델 서비스 v1.1.0 JSON 응답
- Produces: `validate_model_response(task_type: str, response: dict) -> ValidatedModelResponse`, `DiagnosisRoute`, `DiagnosisCategory`

- [ ] **Step 1: 실패하는 계약 테스트 작성**

`test_ml_contracts.py`에 health fixture, 성공 predict, 세 diagnosis route, nullable proposal, 새 오류 코드, `OUT_OF_DOMAIN`, `temperature_c=26.85`, `git_commit=None`, inference_total-only timing을 검증하는 테스트를 작성한다.

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest services/event_gateway/tests/unit/test_ml_contracts.py -v`

Expected: `event_gateway.ml_contracts` 모듈 부재로 FAIL.

- [ ] **Step 3: 최소 계약 모델 구현**

Pydantic 모델로 공통 identity/status/metadata를 검증하고 진단 category 8종, route 3종, route/proposal 조합을 검증한다. 원형 payload의 확장 필드는 보존하되 계약에 명시된 enum과 필수 필드는 강제한다.

- [ ] **Step 4: mock 응답을 새 계약에 맞춤**

mock의 `id`를 `id_on`으로 변경하고 `metadata.model`, `timing_ms`, `stages`, 최상위 오류 필드와 항상 존재하는 `tcad_proposal`을 추가한다.

- [ ] **Step 5: 단위 테스트 통과 확인**

Run: `python -m pytest services/event_gateway/tests/unit/test_ml_contracts.py services/event_gateway/tests/unit/test_contracts.py -v`

Expected: PASS.

- [ ] **Step 6: 커밋**

```bash
git add services/event_gateway/src/event_gateway/ml_contracts.py services/event_gateway/src/mock_surrogate/app.py services/event_gateway/tests/unit/test_ml_contracts.py
git commit -m "feat: validate fab ml service responses"
```

### Task 2: Jetson HTTP 클라이언트와 진단 Worker

**Files:**
- Create: `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/ml_client.py`
- Create: `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/diagnosis_worker.py`
- Create: `jetson_ws/src/fab_virtual_lot/test/test_diagnosis_worker.py`
- Modify: `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/surrogate_worker.py`
- Modify: `jetson_ws/src/fab_virtual_lot/test/test_surrogate_client.py`
- Modify: `jetson_ws/src/fab_virtual_lot/setup.py`

**Interfaces:**
- Consumes: ROS 작업 envelope, `POST /api/v1/predict`, `POST /api/v1/diagnose`
- Produces: `ModelHttpClient(mode, url, endpoint, http)`, `fab_diagnosis_worker`, `diagnosis.completed`

- [ ] **Step 1: 실패하는 HTTP/Worker 테스트 작성**

정확한 endpoint, identity/origin/contract/status 검증, HTTP 200 failed 응답 보존, prod의 mock 결과 거절, diagnosis SQLite 재시도와 outbox event 생성을 시험한다.

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_surrogate_client.py jetson_ws/src/fab_virtual_lot/test/test_diagnosis_worker.py -v`

Expected: 공통 client와 diagnosis worker 부재로 FAIL.

- [ ] **Step 3: 공통 HTTP client 추출**

`ModelHttpClient.__call__(request: dict) -> dict`를 구현하고 기존 `SurrogateClient` 호환 이름을 유지한다.

- [ ] **Step 4: 진단 Worker 구현**

`/fab/diagnosis_requests`를 구독하고 `/api/v1/diagnose`를 호출하며 `diagnosis.completed`를 `/fab/events`에 발행한다. `DIAGNOSIS_MODE`, `DIAGNOSIS_MOCK_URL`, `DIAGNOSIS_PROD_URL`, `DIAGNOSIS_TIMEOUT_SECONDS`, `DIAGNOSIS_RUNTIME_DB`를 사용한다.

- [ ] **Step 5: ROS 실행 진입점 추가**

`fab_diagnosis_worker = fab_virtual_lot.diagnosis_worker:main`을 `setup.py`에 등록한다.

- [ ] **Step 6: 테스트 통과 확인**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_surrogate_client.py jetson_ws/src/fab_virtual_lot/test/test_diagnosis_worker.py jetson_ws/src/fab_virtual_lot/test/test_surrogate_runtime.py -v`

Expected: PASS.

- [ ] **Step 7: 커밋**

```bash
git add jetson_ws/src/fab_virtual_lot
git commit -m "feat: add durable diagnosis worker"
```

### Task 3: Gateway 진단 접수와 ROS dispatch

**Files:**
- Modify: `services/event_gateway/src/event_gateway/app.py`
- Modify: `services/event_gateway/src/event_gateway/config.py`
- Modify: `services/event_gateway/src/event_gateway/inference_jobs.py`
- Modify: `services/event_gateway/src/event_gateway/ros_adapter.py`
- Create: `services/event_gateway/tests/unit/test_diagnosis_routes.py`
- Modify: `services/event_gateway/tests/integration/test_surrogate_flow.py`
- Modify: `.env.example`

**Interfaces:**
- Consumes: `POST /api/v1/diagnosis-jobs`, WebSocket `diagnosis.requested`
- Produces: task type `diagnosis`, ROS `/fab/diagnosis_requests`, Settings `ros_diagnosis_request_topic`, `diagnosis_mode`

- [ ] **Step 1: 실패하는 API·dispatch 테스트 작성**

HTTP와 WebSocket 진단 접수, idempotency, active-job 충돌, dispatch payload, 서로게이트/진단 별도 publisher를 시험한다.

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest services/event_gateway/tests/unit/test_diagnosis_routes.py services/event_gateway/tests/integration/test_surrogate_flow.py -v`

Expected: diagnosis task type과 route 부재로 FAIL.

- [ ] **Step 3: 진단 접수 구현**

`DiagnosisRequest`와 `/api/v1/diagnosis-jobs`, WebSocket `diagnosis.requested`를 추가하고 `submit_inference_job`이 diagnosis를 허용하게 한다.

- [ ] **Step 4: 별도 ROS dispatch 구현**

Settings와 adapter에 `/fab/diagnosis_requests` publisher를 추가하고 task type에 따라 정확한 publisher를 선택한다.

- [ ] **Step 5: 환경변수 예제 추가**

`.env.example`에 `ROS_DIAGNOSIS_REQUEST_TOPIC`, `DIAGNOSIS_MODE`를 비밀값 없이 추가한다.

- [ ] **Step 6: 테스트 통과 확인**

Run: `python -m pytest services/event_gateway/tests/unit/test_diagnosis_routes.py services/event_gateway/tests/integration/test_surrogate_flow.py -v`

Expected: PASS.

- [ ] **Step 7: 커밋**

```bash
git add .env.example services/event_gateway/src/event_gateway services/event_gateway/tests
git commit -m "feat: dispatch diagnosis jobs over ros2"
```

### Task 4: 실행 메타데이터와 진단 결과 DDL

**Files:**
- Create: `database/migrations/008_diagnosis_and_ml_executions.sql`
- Modify: `docs/database/integration-schema.md`
- Create: `services/event_gateway/tests/integration/test_diagnosis_migration.py`

**Interfaces:**
- Consumes: inference job과 fab-ml-v1 response metadata
- Produces: `diagnosis_results`, `ml_inference_executions`, 관련 제약·인덱스

- [ ] **Step 1: 실패하는 migration 테스트 작성**

테이블·FK·unique·route check를 검증하고 `git_commit=null`, inference_total-only timing, 재시도별 execution 행을 저장하는 테스트를 작성한다.

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest services/event_gateway/tests/integration/test_diagnosis_migration.py -v`

Expected: migration 008과 테이블 부재로 FAIL.

- [ ] **Step 3: migration 구현**

명세의 컬럼과 JSONB type check, task/route/status 제약, job·model·created_at 조회 인덱스를 추가한다. 기존 migration은 수정하지 않는다.

- [ ] **Step 4: 스키마 문서 갱신**

각 테이블의 책임, 원형 JSON과 추출 컬럼, 시도별 적재 정책을 기록한다.

- [ ] **Step 5: migration 테스트 통과 확인**

Run: `python -m pytest services/event_gateway/tests/integration/test_diagnosis_migration.py services/event_gateway/tests/integration/test_events_migration.py -v`

Expected: PASS.

- [ ] **Step 6: 커밋**

```bash
git add database/migrations/008_diagnosis_and_ml_executions.sql docs/database/integration-schema.md services/event_gateway/tests/integration/test_diagnosis_migration.py
git commit -m "feat: store diagnosis and ml execution metrics"
```

### Task 5: 결과 저장과 보정 route 라우팅

**Files:**
- Create: `services/event_gateway/src/event_gateway/diagnosis.py`
- Create: `services/event_gateway/src/event_gateway/ml_execution.py`
- Modify: `services/event_gateway/src/event_gateway/surrogate.py`
- Modify: `services/event_gateway/src/event_gateway/ros_adapter.py`
- Create: `services/event_gateway/tests/integration/test_diagnosis_flow.py`
- Modify: `services/event_gateway/tests/integration/test_surrogate_flow.py`

**Interfaces:**
- Consumes: `surrogate.completed`, `diagnosis.completed`, validated fab-ml-v1 response
- Produces: 원형 결과, 실행 메타데이터, routing status, committed ACK 결과

- [ ] **Step 1: 실패하는 저장·라우팅 테스트 작성**

no_action/manual/tcad_verify, null·무효 proposal, failed OUT_OF_DOMAIN, duplicate event, model/timing/stages 추출을 각각 시험한다.

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest services/event_gateway/tests/integration/test_diagnosis_flow.py services/event_gateway/tests/integration/test_surrogate_flow.py -v`

Expected: diagnosis ingestion과 실행 메타데이터 저장 부재로 FAIL.

- [ ] **Step 3: 공통 실행 메타데이터 추출 구현**

`store_ml_execution(connection, job, response, received_at) -> UUID`를 구현한다. 누락 가능한 값을 null로 저장하고 원형 metadata를 함께 보존한다.

- [ ] **Step 4: 진단 결과 ingest 구현**

응답 계약과 요청 identity를 검증하고 결과·execution·job 상태·dispatch 상태를 같은 트랜잭션으로 커밋한다.

- [ ] **Step 5: route 분기 구현**

`no_action`, `manual`, `tcad_verify` 규칙을 구현한다. 무효 후보는 `review_required`이고 네트워크 TCAD 작업을 생성하지 않는다.

- [ ] **Step 6: 서로게이트 실행 메타데이터 저장 추가**

기존 응답 원형 보존과 idempotency를 유지하면서 `ml_inference_executions`도 기록한다.

- [ ] **Step 7: 테스트 통과 확인**

Run: `python -m pytest services/event_gateway/tests/integration/test_diagnosis_flow.py services/event_gateway/tests/integration/test_surrogate_flow.py -v`

Expected: PASS.

- [ ] **Step 8: 커밋**

```bash
git add services/event_gateway/src/event_gateway services/event_gateway/tests/integration
git commit -m "feat: persist and route diagnosis results"
```

### Task 6: 3변수 TCAD 요청 mapper

**Files:**
- Create: `services/event_gateway/src/event_gateway/tcad_mapping.py`
- Create: `services/event_gateway/tests/unit/test_tcad_mapping.py`
- Modify: `services/event_gateway/src/event_gateway/contracts.py`
- Modify: `services/event_gateway/src/event_gateway/repository.py`
- Modify: `services/event_gateway/src/event_gateway/verification_worker.py`
- Modify: `services/event_gateway/src/event_gateway/diagnosis.py`
- Modify: `services/event_gateway/tests/integration/test_diagnosis_flow.py`

**Interfaces:**
- Consumes: 모델 서비스의 3변수 `tcad_proposal`
- Produces: `map_diagnosis_proposal(response: DiagnosisModelResponse, run_context) -> TcadVerificationRequest`

- [ ] **Step 1: 실패하는 mapper 테스트 작성**

세 공정 변수, 후보별 predicted outputs, human approval, high confidence 보존과 diffusion_time 부재를 검증한다. 후보 없음·비정상 숫자·run 불일치도 거절한다.

- [ ] **Step 2: 실패 확인**

Run: `python -m pytest services/event_gateway/tests/unit/test_tcad_mapping.py -v`

Expected: mapper 부재로 FAIL.

- [ ] **Step 3: versioned mapper 구현**

모델 후보를 별도 `TcadVerificationRequest` DTO로 변환한다. `CorrectionProposal`의 공정 벡터 검증도 3변수 계약으로 버전 분리하고 기존 demo fixture를 위한 legacy 4변수 파서는 명시적으로 격리한다. repository와 verification worker가 새 DTO의 3변수 원형을 저장·전달하게 하며 가짜 값을 채우지 않는다.

- [ ] **Step 4: diagnosis 라우팅에 mapper 연결**

mapper 성공 시에만 verification job을 만들고 동일 이벤트 재수신 시 1건을 유지한다.

- [ ] **Step 5: 테스트 통과 확인**

Run: `python -m pytest services/event_gateway/tests/unit/test_tcad_mapping.py services/event_gateway/tests/integration/test_diagnosis_flow.py services/event_gateway/tests/integration/test_verification_worker.py services/event_gateway/tests/integration/test_command_delivery.py -v`

Expected: PASS.

- [ ] **Step 6: 커밋**

```bash
git add services/event_gateway/src/event_gateway/tcad_mapping.py services/event_gateway/src/event_gateway/contracts.py services/event_gateway/src/event_gateway/repository.py services/event_gateway/src/event_gateway/verification_worker.py services/event_gateway/src/event_gateway/diagnosis.py services/event_gateway/tests
git commit -m "feat: map diagnosis candidates to tcad requests"
```

### Task 7: mock·실제 서비스 시험 절차와 전체 회귀

**Files:**
- Modify: `docs/runbooks/surrogate-ml-websocket-e2e.md`
- Create: `docs/runbooks/diagnosis-ml-e2e.md`
- Modify: `docs/architecture/current-system-architecture.md`
- Modify: `docs/runbooks/integration-status-and-latency.md`
- Create: `services/event_gateway/tests/integration/test_ml_v11_e2e.py`

**Interfaces:**
- Consumes: Tasks 1-6의 API, 토픽, DDL, Worker
- Produces: mock/prod 실행 명령, ROS 확인 명령, Aiven 확인 SQL, 회귀 증거

- [ ] **Step 1: mock E2E 테스트 작성**

서로게이트 정상, 진단 no_action/manual/tcad_verify, OUT_OF_DOMAIN을 제출해 DB 결과와 TCAD 작업 수를 검증한다.

- [ ] **Step 2: E2E 실패 확인**

Run: `python -m pytest services/event_gateway/tests/integration/test_ml_v11_e2e.py -v`

Expected: 아직 연결되지 않은 경계가 있으면 FAIL.

- [ ] **Step 3: runbook과 아키텍처 갱신**

모델 서비스 → Gateway → 두 ROS Worker → DB → TCAD → Unity 순서, 실제 학습 영역 입력, health 응답, node/topic 확인, Aiven SQL을 기록한다. 비밀값은 문서에 넣지 않는다.

- [ ] **Step 4: 전체 관련 테스트 실행**

Run: `python -m pytest services/event_gateway/tests/unit services/event_gateway/tests/integration jetson_ws/src/fab_virtual_lot/test -v`

Expected: PASS. 환경 의존 DB 테스트는 구성된 `TEST_DATABASE_URL`을 사용하고 실행하지 못한 경우 원인을 결과에 명시한다.

- [ ] **Step 5: 정적 검증**

Run: `git diff --check`

Expected: 출력 없음.

- [ ] **Step 6: 커밋**

```bash
git add docs services/event_gateway/tests/integration/test_ml_v11_e2e.py
git commit -m "docs: add surrogate diagnosis e2e verification"
```

