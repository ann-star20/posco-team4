# 태스크 06: Unity 모의 수신기와 공통 WebSocket

상태: 구현 전
선행 작업: 03, 05
기준: [최종 계획](../../plans/jetson-tcad-unity-integration-tdd-plan.md), [아키텍처](../../architecture/jetson-ros2-tcad-unity-integration.md)

## 수정 대상

- `services/event_gateway/src/event_gateway/app.py`
- `services/event_gateway/src/event_gateway/stream.py`
- `tools/mock_unity/client.py`
- `services/event_gateway/tests/integration/test_stream.py`

기존 파일이면 수정한다. feat/event-contract에 이미 존재하는 기능을 덮어쓰거나 처음부터 재작성하지 않는다.
패키지 내부 __init__.py와 실행 진입점은 해당 기능 구현에 함께 포함한다.

## 제공 인터페이스

GET /api/v1/events?run_id=&after_sequence=&limit=; WS /api/v1/stream?run_id=&after_sequence=; MockUnity.connect(url, cursor_path) -> None.

## 실패부터 작성할 테스트

- test_mock_receives_real_websocket: 메모리 함수 대체 없이 실제 WebSocket에서 보정값 수신.
- test_disconnect_restart_replays: Gateway·수신기 종료 후 DB에서 재생.
- test_sequence_gap_is_valid: rollback·run 필터로 비는 번호를 오류나 무한 재조회로 처리하지 않는다.
- test_commit_before_crash: 커밋 후 알림 전 종료해도 재시작하면 이벤트 수신.
- test_slow_client_recovery: 느린 수신기 연결 종료 후 마지막 처리 커서부터 복구.
- test_unity_prod_starts_no_mock: prod에서 Gateway 엔드포인트는 같고 자동 모의 수신기만 실행하지 않는다.

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
python -m pytest services/event_gateway/tests/integration/test_stream.py -v
```

DB 테스트는 설정 로더가 로컬 .env의 TEST_DATABASE_URL을 읽는다. 명령에 실제 비밀번호를 넣지 않는다.
기대 결과는 해당 태스크 모든 테스트 PASS이며 아직 존재하지 않는 파일의 명령은 구현 후 사용한다.

## 구현 결정

초기 스트림은 PostgreSQL 커서 polling을 사용한다. 응답에는 mode, input_origin, result_origin, current/delta/recommended, y_verified, approval_allowed를 포함한다. 커서는 run_id별로 저장하고 실제 처리 후에만 갱신한다. Unity C# 구현은 이번 태스크에서 만들지 않고 HTTP/WS 계약 예시를 제공한다.

## 완료 조건과 커밋

위 테스트 전체 통과, 인터페이스 일치, 기존 동작 회귀 없음이 완료 기준이다.
Jetson·실제 외부 서비스가 없어서 실행하지 못한 항목은 완료로 체크하지 않는다.
기능 브랜치에서 다음 타입의 커밋으로 기록한다.

```text
feat(unity): 모의 수신기와 커밋 이벤트 재생 구현
```
