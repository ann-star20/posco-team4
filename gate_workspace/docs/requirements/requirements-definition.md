# Virtual Fab 요구사항 정의서 (Software Requirements Specification)

기준일: 2026-10-23
기준 저장소: `C:\posco_project`
기준 계약 문서: [OpenAPI](../api/openapi.yaml), [AsyncAPI](../api/asyncapi.yaml), [시스템 아키텍처](../architecture/current-system-architecture.md)

이 문서는 목표(to-be) 명세가 아니라 **현재 코드·DB 마이그레이션·계약 문서(OpenAPI/AsyncAPI)에
대조해 검증된 요구사항**이다. 각 기능 요구사항(FR)에 구현 상태를 명시하며, 상태는
계약 문서의 `x-implementation-status`(`implemented`/`mock`/`scaffold`)를 그대로 따른다.

## 1. 목적과 범위

### 1.1 목적

Virtual Fab은 반도체(MOSFET) 가상 공장 파일럿으로, 다음을 목표로 한다.

- Unity 3D 가상 Fab UI에서 Jetson 실물 카메라로 완성품 외관 검사(AOI)를 수행한다.
- 전기적 특성(Surrogate) 추론과 이상 원인 진단(Diagnosis)을 수행한다.
- 진단이 공정 보정을 제안하면 TCAD(Silvaco Atlas) 시뮬레이션으로 검증하고,
  관리자 승인을 받은 뒤에만 가상 공정값에 반영한다.
- 모든 결과는 Aiven PostgreSQL에 멱등하게 영구 저장하고, Unity 연결이 끊겨도
  재접속 시 빠짐없이 재생(replay)한다.

### 1.2 범위

| 포함 | 제외 |
| --- | --- |
| Jetson Camera/AOI, Gateway API/WS/ROS, TCAD 검증·승인, 이벤트 영속화 | 실제 Silvaco Atlas 모델/deck 설계 자체(외부 상용 프로그램 내부) |
| Unity와의 HTTP/WebSocket/ROS 계약 | Unity 클라이언트 UI 구현(외부 팀 책임) |
| TCAD 워크스테이션과의 HTTP 계약 | TCAD 워크스테이션의 `dbascii.exe` 내부 로직 |
| ML(Surrogate/Diagnosis) 모델과의 HTTP 계약 | ML 모델 자체의 학습·아키텍처(외부 팀 제공) |

### 1.3 이해관계자

| 역할 | 책임 |
| --- | --- |
| Unity 팀 | Unity Virtual Fab UI/클라이언트 구현, 관리자 승인 UX |
| Gateway 팀 (본 저장소) | Event Gateway, ROS Bridge, TCAD Verification Worker, DB 스키마 |
| ML 팀 | Jetson `:8300` Surrogate/Diagnosis 모델 서비스 |
| TCAD 운용 담당 | Windows TCAD 워크스테이션, Silvaco Atlas 라이선스·deck |
| 관리자(Approver) | TCAD 후보 검토·승인/반려, 기존 보정 제안 승인 |

## 2. 용어 정의

| 용어 | 정의 |
| --- | --- |
| AOI | Automated Optical Inspection. 완성품 외관 부품/결함 검사 |
| Surrogate | 공정변수(`body_dose`,`epi_doping`,`oxide_thickness`)로 전기적 특성(`vth`,`gm`,`id_on`,`bv`)을 예측하는 GP 모델 |
| Diagnosis | 측정값으로 이상 원인과 보정 후보, TCAD route를 산출하는 에이전트 |
| TCAD 후보(candidate) | Diagnosis가 제안한 보정 공정변수 조합 하나. Silvaco로 검증 대상 |
| proposal group | 한 Diagnosis 응답에서 나온 TCAD 후보들의 묶음(`tcad_proposal_groups`) |
| spec_verdict | TCAD 실측값을 데이터시트 규격과 대조한 판정 결과 |
| run_id / job_id / request_id / event_id | 4절 "식별자" 참고(아키텍처 문서 7절과 동일) |

## 3. 기능 요구사항 (FR)

상태 범례: **구현** = 실제 운영 가능, **모크** = 계약은 구현되었으나 실제 백엔드 대신
mock 서비스로 대체 가능, **미구현** = 계약만 정의되고 코드 없음.

### 3.1 AOI (외관 검사)

| ID | 요구사항 | 근거/구현 | 상태 |
| --- | --- | --- | --- |
| FR-AOI-01 | Unity는 Jetson Preview WebSocket(`:8500/camera/preview`)에 구독해 최신 JPEG만 저지연으로 받는다 (느린 클라이언트의 과거 frame은 폐기) | `jetson_ws/.../camera_preview.py`, AsyncAPI `/camera/preview` | 구현 |
| FR-AOI-02 | Unity는 Jetson AOI WebSocket(`:8400/aoi`)에 `camera_id`+`frame_id`를 보내 지정 frame의 부품(`body`,`lead`,`tab`)·결함(`bend`,`crash`,`scratch`) 검사를 요청한다 | `jetson_ws/.../aoi_unity.py`, `aoi_pipeline.py`, AsyncAPI `/aoi` | 구현 |
| FR-AOI-03 | AOI 결과(JSON + annotated JPEG)는 직접 응답과 별개로 SQLite outbox → `/fab/events` → Gateway → Aiven 경로로 영속화되어야 한다 | `jetson_ws/.../outbox.py`, migration `004_create_aoi_image_artifacts.sql` | 구현 |
| FR-AOI-04 | Gateway 접수형 AOI 작업(`POST /api/v1/inspection-jobs`)도 동일하게 ROS dispatch로 처리되어야 한다 | `app.py`, `inference_jobs.py`, OpenAPI `/api/v1/inspection-jobs` | 구현 |
| FR-AOI-05 | 직접 WS 응답의 `persistence_status=queued`는 Aiven commit 완료를 의미하지 않는다(별도 ACK 필요) | AsyncAPI `AoiDirectResult.persistence_status` 설명 | 구현(계약으로 명시) |

### 3.2 Surrogate 추론

| ID | 요구사항 | 근거/구현 | 상태 |
| --- | --- | --- | --- |
| FR-SUR-01 | Unity는 `POST /api/v1/surrogate-jobs` 또는 `/api/v1/control` WS로 Surrogate 작업을 요청할 수 있다 | `app.py`, OpenAPI `/api/v1/surrogate-jobs`, AsyncAPI `/api/v1/control` | 구현 |
| FR-SUR-02 | Gateway는 ROS `/fab/surrogate_requests`로 Jetson Surrogate Worker에 작업을 배포해야 한다 | `ros_adapter.py`, `surrogate.py`, AsyncAPI `/fab/surrogate_requests` | 구현 |
| FR-SUR-03 | Surrogate Worker는 로컬 ML HTTP `POST 127.0.0.1:8300/api/v1/predict`를 호출해 `vth,gm,id_on,bv`를 받아야 한다 | `jetson_ws/.../surrogate_worker.py` | 모크(실 모델은 ML팀 제공) |
| FR-SUR-04 | Surrogate 완료 결과는 `/fab/events`로 반환되고 Aiven commit 뒤에만 `/fab/event_acks`의 `committed`가 발행되어야 한다 | `ros_adapter.py`, migration `006_surrogate_and_unity_delivery.sql` | 구현 |

### 3.3 Diagnosis 및 TCAD 후보 생성

| ID | 요구사항 | 근거/구현 | 상태 |
| --- | --- | --- | --- |
| FR-DIAG-01 | Diagnosis는 Surrogate와 독립적인 별도 요청이며 Surrogate 성공만으로 자동 트리거되지 않는다 | `diagnosis.py`, 아키텍처 문서 4절 Note | 구현 |
| FR-DIAG-02 | Diagnosis 응답의 `result_payload.compensation.route`가 `tcad_verify`이고 `tcad_proposal.candidates`가 있을 때만 Gateway는 TCAD 큐를 생성해야 한다 | `tcad_queue.py: admit_tcad_candidates` | 구현 |
| FR-DIAG-03 | TCAD 큐 생성 시 Diagnosis 응답에 포함된 규격값(`result_payload.spec`)을 `tcad_proposal_groups.routing_snapshot.spec`에 함께 보존해야 한다 | `tcad_queue.py:24-28` | 구현 |
| FR-DIAG-04 | `route=no_action`/`manual`/실패/후보 없음인 경우 TCAD 큐 없이 진단 결과만 이벤트로 기록되어야 한다 | 아키텍처 문서 4절 `alt` 분기 | 구현 |

### 3.4 TCAD 검증

| ID | 요구사항 | 근거/구현 | 상태 |
| --- | --- | --- | --- |
| FR-TCAD-01 | Verification Worker는 동시 실행 개수를 `TCAD_MAX_CONCURRENT_JOBS`로 제한하며 후보를 DB lease한 뒤 제출해야 한다 | `tcad_candidate_worker.py`, `config.py: tcad_max_concurrent_jobs` | 구현 |
| FR-TCAD-02 | Verification Worker는 `POST /api/v1/tcad/verify`로 후보를 접수시키고, terminal 상태(`succeeded/failed/cancelled`)까지 `GET /api/v1/tcad/jobs/{request_id}`를 polling 해야 한다 | `tcad_client.py`, OpenAPI `/api/v1/tcad/verify`, `/api/v1/tcad/jobs/{request_id}` | 구현 |
| FR-TCAD-03 | 후보가 `succeeded`로 끝나면 측정값(`vth`,`bv`)과 저장된 `spec`을 대조해 `spec_verdict`(`in_spec`/`out_of_spec`/`bv_unconfirmed`/`spec_unavailable`)를 계산·저장해야 한다 | `tcad_candidate_worker.py`, migration `011_tcad_spec_verdict.sql` | 구현 |
| FR-TCAD-04 | `vth∈[1.7,2.6]`(±1e-6) **그리고** `bv≥40`(±1e-6)일 때만 `in_spec`이며, `bv`가 없으면 `bv_unconfirmed`, 규격 자체가 없으면 `spec_unavailable`이어야 한다 | `tcad_candidate_worker.py: evaluate_spec` (사용자 확정 기준) | 구현 |
| FR-TCAD-05 | 모든 후보가 terminal 상태가 되면 proposal group은 `batch_completed`를 거쳐, 성공 후보가 있으면 `review_required`로 전환되어야 한다 | `tcad_candidate_worker.py` | 구현 |
| FR-TCAD-06 | 후보 처리 재시작 시 동일 `tcad_request_id`로 DB lease를 이어서 조회해야 한다(재시작 안전) | `tcad_candidate_worker.py` (재시작 안전 수정, 커밋 `7cac46d`) | 구현 |

### 3.5 TCAD 후보 승인 (Unity 관리자 승인)

| ID | 요구사항 | 근거/구현 | 상태 |
| --- | --- | --- | --- |
| FR-APR-01 | Unity는 `GET /api/v1/tcad/proposals?status=review_required`로 검토 대기 중인 proposal group과 각 후보의 `process_parameters`,`result_payload`,`spec_verdict`를 조회할 수 있어야 한다 | `app.py: list_tcad_proposals` | 구현 |
| FR-APR-02 | Unity는 `POST /api/v1/tcad/proposals/{proposal_id}/decision`으로 후보 하나를 승인(`approved`)하거나 전체를 반려(`rejected`)할 수 있어야 한다 | `app.py: decide_tcad_proposal` | 구현 |
| FR-APR-03 | 승인 시 `selected_tcad_request_id`는 반드시 해당 proposal 소속 후보여야 하며, 아니면 400을 반환해야 한다 | `app.py:316-317` | 구현 |
| FR-APR-04 | 승인되면 group은 `status=completed`, `approved_by`,`approved_at`,`selected_tcad_request_id`가 채워지고, 응답 바디에 선택된 후보의 `process_parameters`가 그대로 포함되어야 한다 | `app.py:318-323,341-342` | 구현 |
| FR-APR-05 | 반려되면 group은 `status=failed`로 전환되고 `process_parameters`는 `null`로 응답해야 한다 | `app.py:324-329` | 구현 |
| FR-APR-06 | 모든 승인/반려 결정은 `tcad.verification.decided` 이벤트로 Aiven에 불변 기록되어야 한다(감사 추적) | `app.py:330-340` | 구현 |
| FR-APR-07 | (기존 경로, 참고) `POST /api/v1/proposals/{proposal_id}/approval`은 `correction_proposals`의 기존 제안을 승인하고 `/api/v1/commands` WS로 Unity에 명령을 push해야 한다. 이 경로는 FR-APR-01~06의 신규 TCAD 경로와 **연결되어 있지 않다** | `commands.py`, OpenAPI `/api/v1/proposals/{proposal_id}/approval` | 구현(별개 경로) |

### 3.6 이벤트 영속화·재생

| ID | 요구사항 | 근거/구현 | 상태 |
| --- | --- | --- | --- |
| FR-EVT-01 | 모든 Jetson/Gateway 발생 이벤트는 `event_id` 멱등 키로 중복 없이 Aiven에 저장되어야 한다 | `repository.py`, migration `001_create_events.sql` | 구현 |
| FR-EVT-02 | Unity는 `GET /api/v1/events?run_id&after_sequence`로 과거 이벤트를 조회하거나 `/api/v1/stream` WS로 `sequence` 순서대로 재생받을 수 있어야 한다 | `stream.py`, OpenAPI `/api/v1/events`, AsyncAPI `/api/v1/stream` | 구현 |
| FR-EVT-03 | Unity 연결이 끊겨도 백그라운드 작업은 계속되며 재접속 시 끊긴 지점부터 재생되어야 한다 | `stream.py`, 아키텍처 문서 7절 | 구현 |
| FR-EVT-04 | Aiven commit 실패 시 이벤트는 dead-letter로 격리되고 Jetson에는 `dead_lettered` ACK가 전달되어야 한다 | `dead_letters.py`, migration `003_create_dead_letters.sql` | 구현 |

### 3.7 명령 전달(기존 보정 경로)

| ID | 요구사항 | 근거/구현 | 상태 |
| --- | --- | --- | --- |
| FR-CMD-01 | 승인된 보정 명령은 `/api/v1/commands` WS로 Unity에 push되고, ROS `/fab/commands`로는 HMAC-SHA256(`command_mac`) 서명과 함께 발행되어야 한다 | `command_dispatcher.py`, AsyncAPI `/fab/commands` | 구현 |
| FR-CMD-02 | Unity가 적용 완료(`correction.applied`)를 보내면 Gateway는 이를 커밋하고 중복 적용을 `command_id`로 방지해야 한다 | `unity_delivery.py` | 구현 |

## 4. 비기능 요구사항 (NFR)

| ID | 요구사항 | 근거 |
| --- | --- | --- |
| NFR-01 | 모든 외부 요청/이벤트는 `request_id`/`event_id`/`command_id` 등 명시적 멱등 키로 중복 처리를 방지해야 한다 | 각 migration의 UNIQUE 제약, `ON CONFLICT DO NOTHING` 사용 패턴 |
| NFR-02 | TCAD 외부 실행(Silvaco)은 장시간 작업이므로 동기 대기 없이 비동기 접수+polling 구조여야 한다 (`TCAD_JOB_DEADLINE_SECONDS` 기본 6000초) | `config.py`, `tcad_client.py` |
| NFR-03 | `TCAD_LEASE_SECONDS`는 항상 `TCAD_REQUEST_TIMEOUT_SECONDS`보다 커야 한다(이중 제출 방지) | `config.py: Settings.load` 검증 로직 |
| NFR-04 | Unity↔Gateway, TCAD↔Gateway 간 통신은 각각 별도 토큰(`X-Unity-Token`,`X-Approval-Token`,`X-Fab-Token`)으로 인증해야 한다 | OpenAPI `securitySchemes` |
| NFR-05 | ROS `/fab/commands`는 애플리케이션 계층에서 HMAC 서명을 추가로 검증해야 한다(DDS 자체는 무인증) | AsyncAPI `/fab/commands: authentication` |
| NFR-06 | 자격 증명(`api_token`, DB 접속 URL 등)은 로그에 출력되지 않아야 한다 | `config.py` 상단 주석, AsyncAPI 예시의 "로그에 출력 금지" 명시 |
| NFR-07 | AOI 원본 이미지는 Jetson 로컬에만 보관하고 Aiven에는 경로·SHA-256·메타데이터만 저장해야 한다(대용량 바이너리 중앙 비적재) | 아키텍처 문서 5절 데이터 소유권 표 |
| NFR-08 | Gateway 재시작 후에도 TCAD 후보 처리는 동일 `tcad_request_id` 기준으로 이어져야 한다(at-least-once, 재시작 안전) | `tcad_candidate_worker.py` 재시작 안전 수정 |
| NFR-09 | 설정값(`TCAD_MODE=prod` 등) 전환 시 필수 값(`TCAD_PROD_URL`,`TCAD_API_TOKEN`)이 없으면 기동 시점에 실패해야 한다(런타임 중 조용한 오류 금지) | `config.py: Settings.load` |

## 5. 외부 인터페이스 요구사항 (요약)

상세 스펙은 별도 **인터페이스 정의서**(다음 산출물)에서 메시지별 필드/에러코드까지 다룬다.
이 절은 범위 식별만 수행한다.

| 경계 | 프로토콜 | 문서 |
| --- | --- | --- |
| Unity ↔ Jetson | WebSocket (binary JPEG + JSON) | AsyncAPI `jetsonPreview`,`jetsonAoi` |
| Unity ↔ Gateway | WebSocket + REST | AsyncAPI `gatewayWebSocket`, OpenAPI 전체 |
| Gateway ↔ Jetson | ROS 2 (DDS, domain 공유) | AsyncAPI `rosDomain` |
| Gateway Verification Worker ↔ TCAD 워크스테이션 | REST (별도 물리 PC) | OpenAPI `/api/v1/tcad/verify`,`/api/v1/tcad/jobs/{request_id}` |
| Jetson Worker ↔ ML HTTP Service | REST (localhost) | OpenAPI `/api/v1/predict` (diagnose는 동일 서비스, 문서 미기재 상태 — 인터페이스정의서에서 보완 필요) |

## 6. 제약사항 및 가정

- WSL2는 미러링 네트워킹 모드를 사용하며, Gateway의 LAN 접근 IP는 Windows 재부팅/네트워크
  변경 시 바뀔 수 있다. Unity 접속 주소는 매 기동 시 재확인이 필요하다.
- Gateway 서버 PC와 TCAD 워크스테이션 PC는 서로 다른 물리 장비이며 네트워크로 연결된다.
- Silvaco Atlas 라이선스와 실행 환경은 TCAD 워크스테이션에만 존재하며 본 저장소가 대체할
  수 없다.
- ML(Surrogate/Diagnosis) 실 모델은 외부 ML팀이 제공하며, 본 저장소는 `mock_surrogate`로
  계약을 모사할 수 있을 뿐 모델 정확도를 보증하지 않는다.
- `gm`,`id_on`은 사용자 결정에 따라 spec 판정에 사용하지 않고 원인 진단 참고용으로만
  남긴다.

## 7. 추적성 매트릭스 (요약)

| 요구사항 그룹 | 구현 파일 | 관련 테스트 |
| --- | --- | --- |
| FR-AOI-* | `jetson_ws/.../aoi_*.py`, `app.py` | `test_aoi_control.py`, `test_aoi_event_storage.py`, `test_aoi_image_migration.py` |
| FR-SUR-* | `surrogate.py`, `surrogate_worker.py` | `test_surrogate_flow.py` |
| FR-DIAG-*, FR-TCAD-* | `tcad_queue.py`, `tcad_candidate_worker.py`, `diagnosis_worker.py` | `test_tcad_candidate_queue.py`, `test_tcad_candidate_worker.py`, `test_diagnosis_flow.py` |
| FR-APR-01~06 | `app.py: list_tcad_proposals`, `decide_tcad_proposal` | `test_app_routes.py` (TCAD decision 케이스 보강 필요 — 8절 참고) |
| FR-APR-07 | `commands.py` | `test_approval.py` |
| FR-EVT-* | `repository.py`, `stream.py`, `dead_letters.py` | `test_events_migration.py`, `test_stream.py`, `test_dead_letters.py` |
| FR-CMD-* | `command_dispatcher.py`, `unity_delivery.py` | `test_command_delivery.py`, `test_unity_application.py` |

## 8. 미해결/후속 과제

- FR-APR-02의 `rejected` 분기는 코드상 구현되어 있으나 실제 호출 기준 테스트가 아직
  없다(E2E 미검증 — 아키텍처 문서 9절과 동일 항목).
- FR-APR-07(기존 경로)과 FR-APR-01~06(신규 경로)의 통합 여부는 제품 결정이 필요하다.
  현재는 설계상 분리된 상태를 "요구사항"으로 그대로 반영했다.
- `/api/v1/diagnose` 엔드포인트는 OpenAPI에 아직 별도 operation으로 기재되지 않았다
  (`/api/v1/predict`만 존재). 인터페이스 정의서 작성 시 보완이 필요하다.
