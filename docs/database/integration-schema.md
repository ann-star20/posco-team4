# 통합 이벤트 DB 변경 명세

기준: PostgreSQL 16, 기존 001_create_events.sql은 feat/event-contract에 구현되어 있다.
상태: 적용 전 설계. 이번 작업에서는 SQL 파일 생성·DB 실행을 하지 않는다.
연결: [아키텍처](../architecture/jetson-ros2-tcad-unity-integration.md), [태스크 03](../tasks/jetson-integration/03-database.md).

## 1. 변경 이유

기존 events는 이벤트 원문만 저장하므로 실행 모드 구분, TCAD 재시도, 보정안 상태,
미확인 Jetson 명령을 복구할 테이블이 필요하다. 기존 001은 수정하지 않고 002를 추가한다.

| 테이블 | 목적 | 핵심 제약 |
|---|---|---|
| integration_runs | 실행 모드·입력 출처 고정 | mock/prod 값 제한 |
| correction_proposals | 후보값·스펙·검증 및 승인 상태 | 이벤트·실행 FK, 상태 CHECK |
| verification_jobs | HTTP 제출·조회 재시도 | request_id PK, proposal 1:1, lease |
| commands | 승인 후 ROS 전달·적용 확인 | proposal당 명령 1개 |
| events | 감사 기록과 Unity 재생 | 기존 보존, 신규 run_id FK |

## 2. 002 마이그레이션 초안

아래 SQL을 구현 태스크에서 database/migrations/002_create_integration_workflow.sql로 옮긴다.
기존 events 행은 legacy 기록으로 run_id=NULL을 유지한다. 신규 Gateway 쓰기는 run_id를 필수 검증한다.

```sql
CREATE TABLE integration_runs (
    run_id UUID PRIMARY KEY,
    tcad_mode TEXT NOT NULL CHECK (tcad_mode IN ('mock', 'prod')),
    unity_mode TEXT NOT NULL CHECK (unity_mode IN ('mock', 'prod')),
    input_origin TEXT NOT NULL CHECK (input_origin IN ('synthetic', 'model')),
    baseline_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE events ADD COLUMN run_id UUID REFERENCES integration_runs(run_id);
CREATE INDEX events_run_sequence_idx ON events(run_id, sequence);

CREATE TABLE correction_proposals (
    proposal_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES integration_runs(run_id),
    source_event_id UUID NOT NULL UNIQUE REFERENCES events(event_id),
    representation TEXT NOT NULL CHECK (representation = 'normalized_ratio'),
    x_current JSONB NOT NULL CHECK (jsonb_typeof(x_current) = 'object'),
    delta_x JSONB NOT NULL CHECK (jsonb_typeof(delta_x) = 'object'),
    x_candidate JSONB NOT NULL CHECK (jsonb_typeof(x_candidate) = 'object'),
    y_observed JSONB NOT NULL CHECK (jsonb_typeof(y_observed) = 'object'),
    targets JSONB NOT NULL CHECK (jsonb_typeof(targets) = 'object'),
    y_verified JSONB,
    result_origin TEXT CHECK (result_origin IN ('mock', 'prod')),
    status TEXT NOT NULL DEFAULT 'proposed'
      CHECK (status IN ('proposed', 'verifying', 'verified', 'rejected', 'failed', 'approved', 'applied')),
    approved_by TEXT,
    approved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status NOT IN ('verified','rejected','approved','applied')
           OR (y_verified IS NOT NULL AND result_origin IS NOT NULL)),
    CHECK (status NOT IN ('approved','applied')
           OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);

CREATE TABLE verification_jobs (
    request_id UUID PRIMARY KEY,
    proposal_id UUID NOT NULL UNIQUE REFERENCES correction_proposals(proposal_id),
    tcad_mode TEXT NOT NULL CHECK (tcad_mode IN ('mock','prod')),
    endpoint_url TEXT NOT NULL,
    remote_job_id TEXT,
    request_body JSONB NOT NULL,
    response_body JSONB,
    status TEXT NOT NULL DEFAULT 'queued'
      CHECK (status IN ('queued','running','succeeded','failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    last_error_code TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((lease_token IS NULL) = (lease_until IS NULL))
);
CREATE INDEX verification_jobs_due_idx ON verification_jobs(next_attempt_at)
    WHERE status IN ('queued','running');

CREATE TABLE commands (
    command_id UUID PRIMARY KEY,
    proposal_id UUID NOT NULL UNIQUE REFERENCES correction_proposals(proposal_id),
    run_id UUID NOT NULL REFERENCES integration_runs(run_id),
    scope TEXT NOT NULL CHECK (scope = 'simulation'),
    effective_from_lot TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
      CHECK (status IN ('pending','sent','applied','failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_token UUID,
    lease_until TIMESTAMPTZ,
    applied_event_id UUID UNIQUE REFERENCES events(event_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at TIMESTAMPTZ,
    CHECK ((lease_token IS NULL) = (lease_until IS NULL)),
    CHECK (status <> 'applied' OR
           (applied_event_id IS NOT NULL AND applied_at IS NOT NULL))
);
CREATE INDEX commands_due_idx ON commands(next_attempt_at)
    WHERE status IN ('pending','sent');
```

JSONB 내부의 숫자·4개 키·가산 관계는 애플리케이션 계약으로 검증한다.
endpoint_url에는 비밀번호나 토큰을 넣지 않는다. 인증정보는 별도 환경변수로 참조한다.
테이블 간 run_id 일치는 repository에서 잠금 후 확인한다. 모든 상태 쓰기는 repository를 경유한다.

## 3. 트랜잭션 규칙

- 신규 입력 이벤트·proposal·verification job 생성은 하나의 트랜잭션이다.
- 동일 event_id와 동일 정규화 본문이면 기존 sequence로 ACK한다. 다른 본문은 충돌로 보존·보고한다.
- 결과 저장·proposal 상태·감사 이벤트는 하나의 트랜잭션이다.
- 승인 시 proposal을 FOR UPDATE로 잠그고 모드·결과 출처·상태를 검증한다. command와 감사 이벤트를 함께 커밋한다.
- 모든 이벤트 생성 경로는 pg_advisory_xact_lock(4184, 1)을 **sequence 할당 전에** 획득한다.
  잠금 순서는 공통 이벤트 잠금 → proposal → job/command로 통일한다.
  이로써 커서가 먼저 커밋된 큰 sequence 뒤의 늦은 작은 sequence를 놓치지 않게 한다.
- DB 트랜잭션 안에서 HTTP 또는 ROS 전송을 기다리지 않는다.
- 작업 claim 후 lease_token을 가진 worker만 결과를 쓸 수 있다. 만료된 worker의 업데이트 건수는 0이어야 한다.
- mock 결과는 prod Unity 승인 대상으로 승격하지 않는다. 모드를 바꿔 재검증하려면 새 proposal/request를 만든다.

## 4. 안전한 적용 절차

1. 기존 컨테이너와 DB의 현재 테이블·마이그레이션 이력을 읽기 전용으로 확인한다.
2. feat/event-contract의 001 구현을 통합한다. 이미 events가 있으면 구조 일치를 확인하고 001을 재실행하지 않는다.
3. schema_migrations(version PK, checksum, applied_at) 이력을 관리한다. 기존 001 baseline 등록은 구조가 일치할 때만 수행한다.
4. TEST_DATABASE_URL로 별도 테스트 DB에 연결한다. 테스트별 임시 스키마를 생성하고 search_path를 한정한다.
5. 002는 한 트랜잭션으로 적용하고 버전·checksum을 기록한다. 재실행은 같은 checksum이면 무작업, 다르면 실패한다.
6. 기존 events 데이터가 남는지, legacy run_id가 NULL인지, 잘못된 상태·FK가 거부되는지 시험한다.
7. 대상 DB 백업과 적용 결과를 기록한 뒤 지정된 개발 DB에 적용한다. 운영 데이터가 있는 기본 postgres DB의 events를 DROP하지 않는다.
8. 장애 시 미커밋 002는 rollback한다. 이미 커밋된 뒤에는 데이터 삭제형 down migration 대신 전진 수정한다.

테스트 정리는 해당 테스트가 생성한 고유 스키마만 대상으로 한다. 이전 테스트의 DROP TABLE events는 폐기한다.
실제 DB 적용 완료라는 표현은 마이그레이션 실행·검증 증거가 생긴 후에만 사용한다.
