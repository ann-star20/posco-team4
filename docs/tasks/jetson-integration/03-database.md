# 태스크 03: 추가 DDL과 멱등 저장

상태: 일부 구현 / 전체 완료 기준 검토 중
선행 작업: 01, 02
기준: [최종 계획](../../plans/jetson-tcad-unity-integration-tdd-plan.md), [아키텍처](../../architecture/jetson-ros2-tcad-unity-integration.md)

## 수정 대상

- `database/migrations/002_create_integration_workflow.sql`
- `services/event_gateway/src/event_gateway/repository.py`
- `services/event_gateway/src/event_gateway/migrate.py`
- `services/event_gateway/tests/integration/conftest.py`
- `services/event_gateway/tests/integration/test_workflow_storage.py`
- `services/event_gateway/tests/integration/test_events_migration.py`

기존 파일이면 수정한다. feat/event-contract에 이미 존재하는 기능을 덮어쓰거나 처음부터 재작성하지 않는다.
패키지 내부 __init__.py와 실행 진입점은 해당 기능 구현에 함께 포함한다.

## 제공 인터페이스

Repository.ingest(event, run_id) -> Receipt(event_id, run_id, sequence); Repository.list_after(run_id, cursor, limit) -> list[StoredEvent]; migrate(dsn) -> MigrationReport.

## 실패부터 작성할 테스트

- test_002_preserves_001_rows: 기존 데이터·인덱스 보존, legacy run_id NULL.
- test_migration_repeat_is_noop: 동일 checksum 재실행은 무작업, 변조 checksum은 거부.
- test_retry_idempotency: 동일 event_id 재전송은 행 하나·같은 receipt, 다른 내용은 충돌.
- test_proposal_job_event_atomic: 저장 중 오류 시 세 테이블 변경이 함께 rollback.
- test_cursor_commit_order: 두 DB 연결에서 첫 트랜잭션을 지연시켜도 후행 이벤트 커서가 선행 이벤트를 건너뛰지 않는다.
- test_schema_isolation: 테스트가 만든 스키마 밖의 sentinel 테이블은 변화가 없다.

## TDD 실행 단계

- [ ] 위 테스트를 **행동 하나씩** 작성한다. 해당 행동을 구현하기 전에 아래 명령으로 RED를 확인한다.
- [ ] 누락된 동작 때문에 실패했는지 확인한다. 의존성·설정 오류는 RED 증거와 구분한다.
- [ ] 해당 테스트를 통과시키는 최소 코드만 구현한다.
- [ ] 같은 테스트를 실행해 GREEN을 확인한다. 이후 다음 행동으로 반복한다.
- [ ] 리팩터링 후 해당 태스크 전체와 기존 관련 회귀 테스트를 실행한다.
- [ ] 코드·테스트·문서만 명시적으로 stage하고 비밀값과 생성물을 제외한다.
- [ ] 검증 명령·성공/실패 수·미실행 환경을 기록한 뒤 커밋한다.

검증 명령(저장소 루트):

```powershell
python -m pytest services/event_gateway/tests/integration/test_workflow_storage.py services/event_gateway/tests/integration/test_events_migration.py -v --tb=short
```

DB 테스트는 설정 로더가 로컬 .env의 TEST_DATABASE_URL을 읽는다. 명령에 실제 비밀번호를 넣지 않는다.
기대 결과는 해당 태스크 모든 테스트 PASS이며 아직 존재하지 않는 파일의 명령은 구현 후 사용한다.

## 구현 결정

docs/database/integration-schema.md의 SQL을 사용한다. 001을 재작성하거나 events를 DROP하지 않는다. 모든 이벤트 삽입은 advisory lock 경유. 신규 이벤트 run_id 필수 및 proposal/job/run 일치 검사. 통합 테스트 DSN 미설정은 명확한 사전조건 실패로 보고하고 통과로 처리하지 않는다. 전용 테스트 스키마에서만 생성·정리한다.

## 완료 조건과 커밋

위 테스트 전체 통과, 인터페이스 일치, 기존 동작 회귀 없음이 완료 기준이다.
Jetson·실제 외부 서비스가 없어서 실행하지 못한 항목은 완료로 체크하지 않는다.
기능 브랜치에서 다음 타입의 커밋으로 기록한다.

```text
feat(db): 실행 모드와 검증 작업 영속화
```
