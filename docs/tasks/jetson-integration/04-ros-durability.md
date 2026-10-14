# 태스크 04: Jetson 발신함과 WSL 구독·커밋 ACK

상태: 구현 전
선행 작업: 02, 03
기준: [최종 계획](../../plans/jetson-tcad-unity-integration-tdd-plan.md), [아키텍처](../../architecture/jetson-ros2-tcad-unity-integration.md)

## 수정 대상

- `jetson_ws/src/fab_virtual_lot/package.xml`
- `jetson_ws/src/fab_virtual_lot/setup.py`
- `jetson_ws/src/fab_virtual_lot/setup.cfg`
- `jetson_ws/src/fab_virtual_lot/resource/fab_virtual_lot`
- `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/__init__.py`
- `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/outbox.py`
- `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/publisher.py`
- `jetson_ws/src/fab_virtual_lot/test/test_outbox.py`
- `services/event_gateway/src/event_gateway/ros_adapter.py`
- `services/event_gateway/tests/unit/test_ros_adapter.py`

기존 파일이면 수정한다. feat/event-contract에 이미 존재하는 기능을 덮어쓰거나 처음부터 재작성하지 않는다.
패키지 내부 __init__.py와 실행 진입점은 해당 기능 구현에 함께 포함한다.

## 제공 인터페이스

Outbox.enqueue(event) -> None; Outbox.pending() -> list[Event]; Outbox.ack(receipt) -> None; RosAdapter.receive(raw) -> None; ACK topic /fab/event_acks.

## 실패부터 작성할 테스트

- test_persist_before_publish: 발행 실패·프로세스 재시작 후에도 이벤트가 남는다.
- test_ack_only_after_commit: DB 실패 시 committed ACK가 없다.
- test_lost_ack_retries_same_id: ACK 유실 시 같은 ID로 재발행하고 DB는 한 행이다.
- test_receipt_matches_event_and_run: 다른 event/run ACK는 발신함을 삭제하지 않는다.
- test_full_queue_no_success_ack: 작업 큐 포화 시 성공을 거짓 보고하지 않는다.
- test_disk_full_stops_production: 발신함 기록 실패 시 이벤트 생산·발행을 중단한다.

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
python -m pytest jetson_ws/src/fab_virtual_lot/test/test_outbox.py services/event_gateway/tests/unit/test_ros_adapter.py -v
```

DB 테스트는 설정 로더가 로컬 .env의 TEST_DATABASE_URL을 읽는다. 명령에 실제 비밀번호를 넣지 않는다.
기대 결과는 해당 태스크 모든 테스트 PASS이며 아직 존재하지 않는 파일의 명령은 구현 후 사용한다.

## 구현 결정

Jetson은 Python 표준 sqlite3로 프로젝트 경로에 발신함을 만든다. WSL ROS callback은 유한 크기 큐에 입력을 넘기고 별도 worker가 DB I/O를 수행한다. 검증 오류는 dead-letter로 보존한다. ROS import는 adapter 경계로 분리한다. 현재 QoS를 조회하고 양쪽 노드 옵션만 호환되게 설정하며 전역 DDS 설정은 바꾸지 않는다.

## 완료 조건과 커밋

위 테스트 전체 통과, 인터페이스 일치, 기존 동작 회귀 없음이 완료 기준이다.
Jetson·실제 외부 서비스가 없어서 실행하지 못한 항목은 완료로 체크하지 않는다.
기능 브랜치에서 다음 타입의 커밋으로 기록한다.

```text
feat(ros): 영속 이벤트 발행과 DB 커밋 ACK 연결
```
