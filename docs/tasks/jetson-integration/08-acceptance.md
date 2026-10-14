# 태스크 08: 모드별 인수 시험과 배포 안내

상태: 구현 전
선행 작업: 01~07
기준: [최종 계획](../../plans/jetson-tcad-unity-integration-tdd-plan.md), [아키텍처](../../architecture/jetson-ros2-tcad-unity-integration.md)

## 수정 대상

- `tests/e2e/test_integration_modes.py`
- `scripts/run-integration.ps1`
- `scripts/run-integration.sh`
- `docs/runbooks/jetson-ros2-integration.md`
- `docs/runbooks/prod-cutover.md`

기존 파일이면 수정한다. feat/event-contract에 이미 존재하는 기능을 덮어쓰거나 처음부터 재작성하지 않는다.
패키지 내부 __init__.py와 실행 진입점은 해당 기능 구현에 함께 포함한다.

## 제공 인터페이스

실행 스크립트는 동일 .env를 로딩하고 TCAD_MODE/UNITY_MODE에 따라 필요한 모의 프로세스만 실행한다.

## 실패부터 작성할 테스트

- test_mock_mock_full_flow: 가상 이벤트→DB→모의 HTTP→DB→모의 WS→사람 승인 요청 fixture→가상 명령 ACK.
- test_four_mode_factory_contracts: 네 조합을 로컬 계약 서버·수신기로 검증하고 실제 prod 증거와 분리.
- test_gateway_and_tcad_restart: 각각 종료·재시작해 이벤트와 작업 수가 중복되지 않는다.
- test_jetson_disconnected: WSL 단절 중 발신함 유지, 복구 후 모두 저장.
- test_secrets_not_tracked: 실제 .env Git 제외와 오류 출력 마스킹을 검증한다.

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
python -m pytest tests/e2e/test_integration_modes.py -v
```

DB 테스트는 설정 로더가 로컬 .env의 TEST_DATABASE_URL을 읽는다. 명령에 실제 비밀번호를 넣지 않는다.
기대 결과는 해당 태스크 모든 테스트 PASS이며 아직 존재하지 않는 파일의 명령은 구현 후 사용한다.

## 구현 결정

스크립트가 시작한 프로세스만 종료한다. 기존 postgres-db는 재사용하고 다른 컨테이너를 지우지 않는다. 실제 Jetson 접속은 현재 IP와 프로젝트 상태를 읽기 전용 점검 후 수행한다. ROS_DOMAIN_ID/RMW와 JetPack·시스템 Python은 변경하지 않는다. WSL→Windows DB 연결 주소를 검증해 .env에 설정한다. 실제 TCAD/Unity 주소가 없으면 prod 실연동은 '미실행: 대상 미완성'으로 보고한다.

## 완료 조건과 커밋

위 테스트 전체 통과, 인터페이스 일치, 기존 동작 회귀 없음이 완료 기준이다.
Jetson·실제 외부 서비스가 없어서 실행하지 못한 항목은 완료로 체크하지 않는다.
기능 브랜치에서 다음 타입의 커밋으로 기록한다.

```text
test(integration): 모드별 복구 인수 시험과 실행 안내 추가
```
