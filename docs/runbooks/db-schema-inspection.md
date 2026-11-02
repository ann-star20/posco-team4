# DB 구조 조회 방식

이 프로젝트의 DB 스키마는 코드가 아니라 **`database/migrations/*.sql`이 유일한 정답(source of truth)**입니다.
ORM 모델이나 별도 스키마 정의 파일은 없고, `event_gateway.migrate`가 이 SQL 파일들을 순서대로 적용하며 적용 이력을 `schema_migrations` 테이블에 기록합니다.

## 1. 지금 구조가 뭔지 알고 싶을 때 — 마이그레이션 파일부터 본다

```
database/migrations/
  001_create_events.sql
  002_create_integration_workflow.sql
  ...
  012_tcad_result_origin.sql
  013_capa_sessions.sql
```

파일명 번호가 적용 순서다. 테이블 하나의 "현재 최종 구조"를 알고 싶으면, 그 테이블이 등장하는 모든 마이그레이션 파일을 **번호 순서대로** 읽어서 머릿속으로 합쳐야 한다 (예: `events` 테이블은 001에서 만들어지고 002에서 `run_id` 컬럼이 `ALTER TABLE`로 추가됨). 한 파일만 보고 판단하면 안 된다.

```bash
grep -rln "ALTER TABLE events\|CREATE TABLE events" database/migrations/
```

## 2. 실제 DB에 뭐가 적용돼 있는지 확인 — 읽기 전용 점검

`migrate.py`를 `--apply` 없이 실행하면 **쓰기 없이** 현재 테이블 목록만 보여준다.

```bash
cd services/event_gateway
PYTHONPATH=src python -m event_gateway.migrate
```

출력 예:
```
기존 테이블: aoi_image_artifacts, ..., events, ..., tcad_proposal_groups, ...
읽기 전용 점검입니다. 적용하려면 --apply를 지정하세요.
```

이 명령은 운영 DB(`.env`의 `DATABASE_URL`)에 연결해서 `pg_catalog.pg_tables`만 조회한다 — 안전하다.

## 3. 어떤 마이그레이션이 이미 적용됐는지 확인 — `schema_migrations`

```sql
SELECT version, checksum, applied_at FROM schema_migrations ORDER BY applied_at;
```

- `version`: 적용된 파일명 (예: `012_tcad_result_origin.sql`)
- `checksum`: 적용 당시 그 파일의 `sha256` — **지금 디스크의 파일과 체크섬이 다르면 `migrate.py --apply`가 즉시 에러를 내고 멈춘다** (어떤 마이그레이션이든, 나중 번호 포함 전부 중단). 디스크 파일을 임의로 고치면 안 되는 이유가 이것이다.

체크섬이 안 맞을 때 원인 후보: 1) 누군가 적용된 과거 마이그레이션 파일을 수정함(실제 구조 드리프트 — 위험), 2) 파일 내용은 그대로인데 `schema_migrations`에 기록된 체크섬 자체가 stale함(구조는 코드와 일치하는 기록 오류 — 비교적 안전).

**실제로 겪은 사례(2026-10-24)**: `002`~`010` 9개 파일 전부가 DB 기록과 체크섬이 달랐고, `011`/`012`는 아예 `schema_migrations`에 행이 없었다(라이브로는 이미 적용돼 있었음에도). 원인을 확정하기 전에 반드시 아래 순서로 먼저 확인한다 — **체크섬만 보고 구조가 깨졌다고 단정하지 않는다.**

1. `git diff <파일>`로 git HEAD와 다른지 확인한다. 다르면 실제로 누가 수정한 것 — 구조 드리프트 가능성이 높으니 섹션 4의 조회로 실제 운영 테이블 구조와 대조한다.
2. git과 동일한데도 체크섬이 다르면, §4의 `information_schema.columns`/`pg_constraint` 조회로 **그 파일이 만드는 테이블의 실제 운영 구조**를 직접 찍어서 파일 내용과 한 줄씩 대조한다. 일치하면 "기록만 stale"이 맞다 — 실제 구조는 코드 기준과 같다.
3. 기록만 stale임을 확인했다면, 파일을 기준으로 체크섬을 다시 계산해 `schema_migrations.checksum`을 `UPDATE`한다(재적용 아님, SQL을 다시 실행하지 않는다). 이미 라이브인데 행이 없는 경우(011/012 사례)는 `INSERT ... ON CONFLICT (version) DO NOTHING`으로 **추적 테이블에만 등록**한다 — 이게 `migrate.py`의 `adopt_existing_001`과 같은 원리다.
4. 이 교정은 운영 DB의 이력 테이블을 직접 쓰는 작업이므로, 실행 전 사람에게 확인받고 전/후 값을 로그로 남긴다. 구조 자체(테이블/컬럼/CHECK)는 절대 손으로 맞추지 않는다 — 구조가 다르면 그건 체크섬 문제가 아니라 별도 마이그레이션으로 풀어야 하는 진짜 드리프트다.

## 4. 특정 테이블의 실제 컬럼/제약조건을 직접 조회

```sql
-- 컬럼 목록
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = current_schema() AND table_name = '테이블명'
ORDER BY ordinal_position;

-- 인덱스
SELECT indexname, indexdef FROM pg_indexes
WHERE schemaname = current_schema() AND tablename = '테이블명';

-- CHECK/FK 등 제약조건
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conrelid = '테이블명'::regclass;
```

`migrate.py`의 `adopt_existing_001`이 정확히 이 패턴(`information_schema.columns` + `pg_indexes` + `pg_constraint`)을 코드로 검증하는 예시이니, 참고용으로 `services/event_gateway/src/event_gateway/migrate.py:11-49`를 봐도 된다.

## 5. 연결 정보

- 운영 DB: `.env`의 `DATABASE_URL`
- 테스트 전용 DB: `.env`의 `TEST_DATABASE_URL` — 통합 테스트(`tests/integration/`)는 매 테스트마다 `test_<uuid>` 스키마를 새로 만들고 끝나면 삭제한다(`tests/integration/conftest.py`의 `test_connection` 픽스처). 운영 데이터와 절대 섞이지 않는다.
- 토큰/비밀번호가 포함된 연결 문자열을 터미널에 그대로 echo/print 하지 않는다 — 스크립트 안에서 읽어서 연결에만 쓰고, 조회 결과만 출력한다.

## 6. 요약: 질문별로 어디를 볼지

| 궁금한 것 | 어디를 본다 |
|---|---|
| "이 테이블이 왜 이렇게 생겼지?" | `database/migrations/`에서 그 테이블명으로 grep, 번호 순서대로 누적 적용 |
| "지금 운영 DB에 이 테이블이 진짜 있나?" | `python -m event_gateway.migrate` (읍기 전용) |
| "마이그레이션이 다 적용됐나?" | `SELECT * FROM schema_migrations` |
| "이 컬럼의 정확한 타입/제약이 뭐지?" | `information_schema.columns` / `pg_constraint` 직접 조회 |
| "테스트에서 DB 건드려도 되나?" | `TEST_DATABASE_URL`만 쓴다, 운영 `DATABASE_URL`은 절대 테스트에서 안 씀 |
| "체크섬이 안 맞는다고 나온다" | §3의 4단계 절차 — 먼저 git diff, 그다음 실제 구조 대조, 구조가 같으면 기록만 교정 |

## 7. 현재 적용 이력 (2026-10-24 기준)

| 파일 | 상태 |
|---|---|
| 001_create_events.sql | 적용됨 |
| 002_create_integration_workflow.sql | 적용됨 (체크섬 기록 교정함, 구조 변경 없음) |
| 003_create_dead_letters.sql | 적용됨 (체크섬 기록 교정함) |
| 004_create_aoi_image_artifacts.sql | 적용됨 (체크섬 기록 교정함) |
| 005_create_inference_jobs.sql | 적용됨 (체크섬 기록 교정함) |
| 006_surrogate_and_unity_delivery.sql | 적용됨 (체크섬 기록 교정함) |
| 007_create_aoi_inference_metrics.sql | 적용됨 (체크섬 기록 교정함) |
| 008_diagnosis_and_ml_executions.sql | 적용됨 (체크섬 기록 교정함) |
| 009_ml_execution_attempts.sql | 적용됨 (체크섬 기록 교정함) |
| 010_create_tcad_candidate_queue.sql | 적용됨 (체크섬 기록 교정함) |
| 011_tcad_spec_verdict.sql | 적용됨 (라이브 구조는 이미 존재, 추적 테이블에 신규 등록) |
| 012_tcad_result_origin.sql | 적용됨 (라이브 구조는 이미 존재, 추적 테이블에 신규 등록) |
| 013_capa_sessions.sql | 적용됨 (`factory_sessions`/`factory_session_equipment`/`factory_lots` 신규) |
| 014_capa_state_versions.sql | 적용됨 (`factory_object_versions` 신규 — 작업 2A: 설비/LOT 상태 이벤트 순서 보장) |
| 015_capa_intervals.sql | 적용됨 (`equipment_state_intervals`/`lot_activity_intervals` 신규 — 작업 2B: 상태 구간 저장) |

`SELECT version, checksum, applied_at FROM schema_migrations ORDER BY version;`으로 언제든 최신 상태를 다시 확인할 수 있다. 이 표는 스냅샷이므로, 새 마이그레이션을 추가했으면 이 표도 함께 갱신한다.
