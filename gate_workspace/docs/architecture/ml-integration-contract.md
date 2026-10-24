# Jetson ML 연계: 역할 분리와 요청·응답 보존

상태(2026-10-18): fab-ml-v1 HTTP adapter·ROS Worker·요청/응답 DB·조건부 TCAD 라우팅·mock 전체 공정 시험을 구현했다. 실제 팀원 모델은 동일 HTTP 계약의 Jetson 서비스로 교체한다. [실행과 env 전환](../runbooks/full-mock-process.md)이 현재 구현 기준이며 아래 fencing/모든 장애 시나리오는 확장 요구다.

## 1. 책임 경계

| 담당 | 책임 |
|---|---|
| ML 팀원 | 모델 학습·전처리·GP 단계 연결·추론·Id 측정 조건·출력 의미·모델/계약 버전 정의 |
| Jetson ML adapter | 팀원 모델의 호출 인터페이스 연결, 영속 작업 수신·결과 발신, mock/prod 전환 |
| Gateway | 요청 전달, 응답 계약 검증, DB 보존, ACK·중복·timeout·동시성 처리, 후속 TCAD/Unity 연계 |
| TCAD 서비스 | 합의된 검증 요청 실행과 결과 반환 |

모델 실행 위치는 Jetson이다. Gateway가 sqrt/log 변환, Vth 재계산, Id 조건 결정, GP 간 연결을 구현하지 않는다. 팀원이 설명한 구조(입력 3개, Vth/gm 예측, 입력+Vth로 Id 예측, 별도 BV GP)는 모델 내부 정보다. Gateway의 모델 내부 구현 의존성으로 만들지 않는다.

ML 측은 출력 의미와 측정 조건을 응답 메타데이터 또는 불변 버전의 계약으로 제공한다. Gateway는 이를 보존·연결하며 물리적 의미를 임의 해석하지 않는다. Id를 기존 Id_on 필드로 자동 치환하지 않는다. 예측 모델이 보정 후보까지 생성한다고 가정하지 않으며 후보 생성 책임은 별도 인터페이스 합의 대상이다.

## 2. 전기적 특성 경로

```text
Jetson 이상 이벤트 → Gateway DB 보존
  → ML 요청·전달 outbox DB 보존
  → ROS → Jetson adapter → 팀원 ML 실행
  → ROS 결과 → Gateway DB 보존 → committed ACK
  → 합의된 TCAD 요청 계약과 후보가 준비되었는지 검사
  → TCAD HTTP 검증 → 결과 DB 보존·Unity 표시
  → 관리자 승인 → Unity 가상 적용 → 적용 결과 DB 보존
```

AOI 완성품 외관 검사는 별개다. 모든 ML 응답이 자동 TCAD 호출을 뜻하지 않는다. 성공한 응답과 유효한 후보·TCAD 입력이 연결될 때만 검증 작업을 만든다. 입력이 없으면 보류 사유를 기록하고 임의 값을 생성하지 않는다.

## 3. 외부 계약안

공통 envelope만 Gateway가 관리하고 payload의 업무 의미는 ML 팀원이 정의한다. 최종 필드명은 팀 간 계약 시험으로 확정한다.

| 구분 | 필드 |
|---|---|
| 요청 식별 | schema_version, request_id, job_id, run_id, lot_id, candidate_id(후보 예측 시), attempt, fencing_token |
| 요청 내용 | model_contract_version, requested_model_version, input_payload |
| 응답 식별 | 동일 요청/작업/후보/attempt/fencing_token, event_id |
| 응답 내용 | status, model_version, model_contract_version, result_payload, metadata, error |
| 출처 | result_origin=mock 또는 model, 모델 측 완료 시각, Gateway 수신 시각 |

input_payload는 합의된 원본 공정값·단위를 담는다. result_payload에는 모델이 제공한 Vth/gm/Id/BV 결과를 변환 없이 담는다. 불확실성·측정 조건·단위는 팀원 계약에 따라 payload/metadata로 보존한다. Gateway의 검증은 인증, 크기 제한, JSON/버전/필수 필드, 요청 대응, 상태 형식 등 계약 검증이며 모델 정확도 검증이 아니다.

ML 응답을 그대로 TCAD HTTP 본문으로 복사하지 않는다. 모델 측·TCAD 측과 합의된 버전별 필드 매핑만 적용한다. 지원하지 않는 계약 버전, 실패 응답, 필수 TCAD 입력 누락은 TCAD 자동 전송을 차단한다.

## 4. DB와 신뢰성

- 요청 payload와 응답 payload 전체를 JSONB로 보존하고, 식별자·상태·버전·출처·송수신 시각·payload hash를 별도 조회 컬럼으로 둔다. JSONB는 JSON 의미를 보존하지만 원본 문자열의 공백·키 순서까지 보존하지 않는다. 바이트 단위 원문 감사가 필요하면 별도 raw text/hash를 설계한다.
- ML 예측과 TCAD 검증은 별도 결과 레코드로 저장하고 proposal/candidate/job ID로 연결한다. 어느 한쪽 결과로 다른 쪽을 덮어쓰지 않는다.
- 요청/outbox를 함께 커밋한다. 결과/inbox 중복 제거/job 상태/후속 TCAD outbox 생성도 필요한 조건하에 같은 트랜잭션에서 처리한다. 네트워크 호출은 트랜잭션 밖에서 수행한다.
- 같은 request_id의 동일 본문은 같은 작업을 반환하고 다른 본문은 충돌이다. event_id 및 작업별 최종 결과 제약으로 중복 수신을 방지한다. 같은 ID에 다른 결과가 오면 충돌 감사 기록을 남긴다.
- DB 커밋 전 committed ACK를 보내지 않는다. Jetson은 결과를 SQLite outbox에 보관하고 ACK까지 재전송한다. 거부된 메시지의 영속 보존과 업무 성공을 구분한다.
- timeout 이후 늦은 응답도 보존하되, 오래된 attempt/fencing token 결과는 현재 상태·TCAD 요청을 변경하지 못한다. 각 job은 독립 추적하고 기존 자원별 큐/동시성 제한을 따른다.
- 무효/과대/비인증 메시지를 무제한 원문 저장하지 않는다. 크기 제한과 보안 정책에 따라 거절 사유·허용된 감사 정보만 남긴다. DB 장애 중 중앙 보존을 약속하지 않고 송신자 영속 재시도로 복구한다.

## 5. mock/prod와 TDD

전기적 특성 예측 adapter는 `SURROGATE_MODE=mock|prod` 및 `SURROGATE_MOCK_URL`/`SURROGATE_PROD_URL`을 읽는다. 기존 DIAGNOSIS_MODE와 다른 기능이다. 팀원 모델은 Jetson HTTP 서비스에서 로드하고 Worker가 같은 fab-ml-v1 계약으로 호출한다. 모델 내부 개발은 포함하지 않는다.

- mock: 같은 요청/응답 계약의 고정 결과를 실제 ROS로 전달한다. Gateway DB 적재·ACK·후속 HTTP/WS를 시험한다.
- prod: Jetson에서 팀원 모델을 호출한다. 로드/추론 실패 시 mock 성공으로 바꾸지 않는다.
- 계약 시험: payload/metadata 보존, Id 값/조건 무변환, 모델 버전과 요청 대응, 미지원 버전 거절.
- 신뢰성 시험: 중복·동시 요청·응답 역전·오래된 결과·DB 장애·ACK 유실·재시작 후 복구.
- TCAD 경계 시험: 성공+합의된 후보/입력에서만 HTTP 검증 요청 1개 생성, 실패/누락/AOI 결과에서는 호출 없음.

모델 정확도·GP 연결·전처리·측정 조건 시험은 ML 담당 범위다. 우리는 계약 fixture로 통신·보존을 먼저 구현하고, 실제 모델 인수 시 같은 계약 시험을 적용한다.

관련: [동시성·승인·Unity 적용](concurrent-stage-and-unity-approval.md), [전체 설계](process-inspection-orchestration.md), [TDD 계획](../plans/process-inspection-tdd-plan.md).
