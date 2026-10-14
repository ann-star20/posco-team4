# 태스크 07: 가상 승인과 Jetson 보정 적용

상태: 일부 구현 / 실제 Jetson 적용 왕복 미검증
선행 작업: 04~06
기준: [최종 계획](../../plans/jetson-tcad-unity-integration-tdd-plan.md), [아키텍처](../../architecture/jetson-ros2-tcad-unity-integration.md)

## 수정 대상

- `services/event_gateway/src/event_gateway/commands.py`
- `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/command_subscriber.py`
- `services/event_gateway/tests/integration/test_approval.py`
- `jetson_ws/src/fab_virtual_lot/test/test_command_subscriber.py`

기존 파일이면 수정한다. feat/event-contract에 이미 존재하는 기능을 덮어쓰거나 처음부터 재작성하지 않는다.
패키지 내부 __init__.py와 실행 진입점은 해당 기능 구현에 함께 포함한다.

## 제공 인터페이스

POST /api/v1/proposals/{id}/approval {approved_by, effective_from_lot}; Commands.publish_due() -> Summary; apply(command) -> AppliedReceipt.

## 실패부터 작성할 테스트

- test_only_verified_approval: proposed/verifying/rejected/failed는 409.
- test_mock_not_approved_for_prod_unity: mock 검증+prod Unity는 409, mock/mock은 명시적 사람 demo 승인만 허용.
- test_duplicate_approval_one_command: 동시 승인에서 command 하나·동일 ID 반환.
- test_recipe_and_command_commit_atomic: 로컬 레시피와 적용 ID 기록 사이 종료에도 이중 적용 없음.
- test_lost_apply_ack: 재발행 명령은 다시 적용하지 않고 동일 ACK 반환.
- test_effective_lot: 요청된 다음 로트에만 레시피가 적용되고 에피 도핑 변경 불가.

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
python -m pytest services/event_gateway/tests/integration/test_approval.py jetson_ws/src/fab_virtual_lot/test/test_command_subscriber.py -v
```

DB 테스트는 설정 로더가 로컬 .env의 TEST_DATABASE_URL을 읽는다. 명령에 실제 비밀번호를 넣지 않는다.
기대 결과는 해당 태스크 모든 테스트 PASS이며 아직 존재하지 않는 파일의 명령은 구현 후 사용한다.

## 구현 결정

모든 명령은 scope=simulation. 승인자·시간 기록과 command 생성은 DB 트랜잭션, ROS 전달은 커밋 이후다. 적용 완료 ACK도 /fab/events의 영속 발신함으로 보낸다. 사람이 승인하지 않은 mock 자동 적용을 만들지 않는다.

## 완료 조건과 커밋

위 테스트 전체 통과, 인터페이스 일치, 기존 동작 회귀 없음이 완료 기준이다.
Jetson·실제 외부 서비스가 없어서 실행하지 못한 항목은 완료로 체크하지 않는다.
기능 브랜치에서 다음 타입의 커밋으로 기록한다.

```text
feat(commands): 가상 보정 승인과 멱등 적용 연결
```
