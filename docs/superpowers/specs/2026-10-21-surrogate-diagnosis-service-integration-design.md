# Jetson 서로게이트·진단 서비스 통합 설계

작성일: 2026-10-21  
대상 계약: `fab-ml-v1`  
모델 서비스 버전: `1.1.0`

## 1. 목적

Jetson에 배포된 실제 서로게이트·진단 모델 서비스를 기존 Gateway, ROS 2,
Aiven PostgreSQL, Unity 및 별도 TCAD 워크스테이션 흐름에 연결한다. 모델 내부
전처리와 추론은 Jetson 서비스가 담당하고, Gateway는 요청 전달, 계약 검증,
원형 응답 보존, 후속 TCAD 라우팅과 Unity 전달을 담당한다.

완료 기준은 다음과 같다.

- 실제 `/api/v1/predict` 요청이 ROS 2 왕복 후 Aiven DB에 저장된다.
- `/api/v1/diagnose` 요청이 서로게이트와 독립적으로 처리된다.
- 성공·실패 응답의 모델, 시간, 단계 메타데이터가 손실 없이 저장된다.
- `compensation.route`에 따라 TCAD 검증 여부가 결정된다.
- TCAD 검증과 관리자 승인 전에는 보정 명령이 생성되지 않는다.
- mock과 prod는 동일 계약을 사용하며 환경변수만으로 전환된다.

## 2. 책임 경계

| 구성요소 | 책임 |
|---|---|
| Unity | Gateway에 작업 요청, 커밋된 결과 표시, 승인된 명령 적용 및 ACK |
| Gateway | 인증, 작업 영속화, ROS dispatch, 계약 검증, DB 저장, TCAD/Unity 라우팅 |
| Jetson Surrogate Worker | 서로게이트 ROS 요청 영속 수신, `/api/v1/predict` 호출, 결과 outbox 발행 |
| Jetson Diagnosis Worker | 진단 ROS 요청 영속 수신, `/api/v1/diagnose` 호출, 결과 outbox 발행 |
| Jetson 모델 서비스 | 모델 1회 로드, 전처리, 예측·진단, 신뢰도·메타데이터 생성 |
| TCAD 워크스테이션 | Gateway의 HTTP 검증 요청 수행 및 검증 결과 반환 |

Unity와 Gateway는 `sqrt(body_dose)` 또는 `log(epi_doping)`을 계산하지 않는다.
모델의 내부 GP 연결과 물리 단위 변환은 모델 서비스의 책임이다.

## 3. 통신 구조

```text
Unity
  -> Gateway HTTP/WebSocket
  -> PostgreSQL inference_jobs + inference_dispatches
  -> ROS /fab/surrogate_requests 또는 /fab/diagnosis_requests
  -> Jetson Worker
  -> HTTP /api/v1/predict 또는 /api/v1/diagnose
  -> ROS /fab/events
  -> Gateway 계약 검증 + PostgreSQL 커밋
  -> ROS /fab/event_acks
  -> Unity /api/v1/stream
```

서로게이트와 진단은 별도 ROS 토픽과 별도 Worker 실행기로 분리한다. 진단이 오래
걸려도 서로게이트 요청이 차단되지 않으며, 재시도·timeout·관측값도 각각 관리한다.

## 4. 모델 서비스 계약

### 4.1 엔드포인트

- `GET /health/ready`
- `POST /api/v1/predict`
- `POST /api/v1/diagnose`

현재 모델 서비스의 `service_version`은 `1.1.0`이며 계약 버전은
`fab-ml-v1`이다. `/api/v1/predict`가 `task_type=diagnosis|diagnose`를 받을 수
있더라도 Gateway는 역할을 명확히 하기 위해 진단 시 `/api/v1/diagnose`를 사용한다.

### 4.2 공정 입력과 출력

입력은 `body_dose(cm^-2)`, `epi_doping(cm^-3)`,
`oxide_thickness(um)` 세 가지다. 출력은 `vth`, `gm`, `id_on`, `bv`를 사용한다.
Id 측정 조건은 `metadata.id_conditions`에 보존한다. 300 K에 해당하는
`temperature_c=26.85`를 유효한 값으로 취급하며 25도로 강제 변환하지 않는다.

### 4.3 진단 분류

`top_category`, `category_probabilities` 키 및 `candidates[].category`는 다음
영문 코드만 허용한다.

```text
normal, dose, epi, oxide,
dose+epi, dose+oxide, epi+oxide, dose+epi+oxide
```

한글은 `*_label` 표시 필드로만 보존한다.

### 4.4 보정 경로

`compensation.route` 허용값은 다음 세 가지다.

- `no_action`: 결과 저장, TCAD 요청 없음
- `manual`: 결과 저장, 관리자 검토 필요, 자동 TCAD 요청 없음
- `tcad_verify`: 유효한 `tcad_proposal`이 있을 때 TCAD 검증 작업 생성

`route=tcad_verify`일 때만 `tcad_proposal`이 객체여야 한다. 나머지 route에서는
항상 `null`이다. `requires_human_approval`은 항상 `true`이며,
`high_confidence`는 TCAD 생략 근거가 아닌 검증 우선순위·표시 정보로만 사용한다.

### 4.5 오류

허용 오류 코드는 다음과 같다.

```text
INVALID_INPUT, UNSUPPORTED_CONTRACT_VERSION, INFERENCE_FAILED,
OUT_OF_DOMAIN, UNSUPPORTED_TASK_TYPE, UNAUTHORIZED, MODEL_NOT_READY
```

`OUT_OF_DOMAIN`은 HTTP 200과 `status=failed` 조합을 허용한다. 모든 실패 응답은
최상위 `error_code`, `error_message`를 가져야 한다. 호환용 기존
`error: {code, message}`는 저장하지만 Gateway 분기는 최상위 필드를 사용한다.

### 4.6 관측 메타데이터

모든 성공·실패 응답은 `metadata.model`, `metadata.timing_ms`,
`metadata.stages`를 포함한다. 서로게이트가 `inference_total`만 제공하는 것은
유효하다. `git_commit=null`도 허용한다. 원형 응답은 JSONB로 보존하고 자주 조회할
필드만 실행 테이블에 추출한다.

## 5. Gateway 및 ROS 변경

### 5.1 작업 종류와 API

기존 `aoi`, `surrogate`에 `diagnosis`를 추가한다.

- HTTP: `POST /api/v1/diagnosis-jobs`
- Control WebSocket: `type=diagnosis.requested`
- ROS 요청: `/fab/diagnosis_requests`
- ROS 결과: `/fab/events`, `event_type=diagnosis.completed`
- ACK: `/fab/event_acks`

### 5.2 Worker

공통 영속 inbox/outbox와 HTTP 계약 검증은 재사용하되 실행자는 분리한다.

- `fab_surrogate_worker`: `/predict`, 단일 실행기
- `fab_diagnosis_worker`: `/diagnose`, 단일 실행기

두 Worker는 별도 프로세스로 병렬 실행할 수 있다. 모델 서비스의 실제 동시 실행
정책은 팀원이 선언한 thread-safety와 자원 한도에 맞춘다.

### 5.3 응답 검증

Worker는 요청/응답의 `request_id`, `job_id`, `model_contract_version`,
`result_origin`, `status`를 검증한다. Gateway는 업무 enum, 실패 필드,
route와 proposal의 조합을 추가 검증한다. 잘못된 결과는 성공으로 위장하지 않으며
영속 재시도 또는 dead-letter 정책으로 이동한다.

## 6. DB 설계

기존 `surrogate_results.response_body`와 신규 `diagnosis_results.response_body`에는
응답 원형을 JSONB로 저장한다.

신규 `diagnosis_results` 주요 컬럼:

- `job_id`, `source_event_id`, `response_body`
- `top_category`, `top_probability`
- `compensation_route`, `high_confidence`
- `routing_status`, `proposal_id`, `created_at`

신규 `ml_inference_executions`는 재시도마다 한 행을 기록한다.

- 식별: `execution_id`, `job_id`, `attempt`, `task_type`
- 모델: 이름, 버전, artifact hash, 학습 데이터 버전, 장치, 정밀도
- 상태: `status`, `error_code`
- 시간: queue wait, inference, service duration, 시작·완료 시각
- 원형 보조 정보: `stage_metrics`, `runtime_metadata` JSONB

원형 JSON과 추출 컬럼은 같은 DB 트랜잭션으로 저장한다.

## 7. TCAD 어댑터

모델의 3변수 후보를 기존 4변수 `CorrectionProposal`로 직접 검증하지 않는다.
Gateway에 모델 후보 계약과 TCAD 요청 계약 사이의 명시적 mapper를 둔다.

```text
body_dose, epi_doping, oxide_thickness
  -> versioned TCAD request mapper
  -> TCAD 워크스테이션 HTTP 계약
```

`diffusion_time`을 모델 응답에 합성하지 않는다. `route=tcad_verify`인데 proposal이
없거나 무효이면 결과를 보존하고 `review_required`로 두며 TCAD를 호출하지 않는다.

## 8. 시험 전략

1. 모델 단독 계약 시험: health, predict, diagnose, 세 route, OUT_OF_DOMAIN
2. Worker 계약 시험: identity, origin, status, 새 오류 코드, nullable proposal
3. ROS 통합 시험: 각 요청 토픽의 publisher/subscriber 및 committed ACK
4. DB 통합 시험: 원형 응답과 추출 메타데이터의 원자적 저장
5. TCAD 경계 시험: `tcad_verify + valid proposal`에서만 작업 1건 생성
6. 전체 mock E2E: no_action, manual, tcad_verify, failed
7. 실제 모델 E2E: 학습 영역 중심값 `7.7e12`, `1.7e16`, `0.06` 근처 입력

첫 실제 E2E는 `anomaly_detected=false`, `tcad_proposal=null`인 서로게이트 요청으로
통신과 저장만 확인한다. 이후 진단 및 TCAD 경로를 검증한다.

## 9. 범위 밖

- 모델 학습·정확도 개선
- Silvaco deck 구현
- `high_confidence`를 이용한 TCAD 생략
- 관리자 승인 없는 자동 보정
- `TIMEOUT`, `RESOURCE_EXHAUSTED` 모델 오류 생성

