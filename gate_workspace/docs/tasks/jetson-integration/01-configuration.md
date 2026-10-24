# 태스크 01: 설정과 실행 모드

상태: 일부 구현 / 전체 완료 기준 검토 중
선행 작업: 기존 feat/event-contract 코드와 문서 브랜치를 기능 브랜치에 통합한 상태
기준: [최종 계획](../../plans/jetson-tcad-unity-integration-tdd-plan.md), [아키텍처](../../architecture/jetson-ros2-tcad-unity-integration.md)

## 수정 대상

- `.gitignore`
- `.env.example`
- `services/event_gateway/pyproject.toml`
- `services/event_gateway/src/event_gateway/config.py`
- `services/event_gateway/tests/unit/test_config.py`

기존 파일이면 수정한다. feat/event-contract에 이미 존재하는 기능을 덮어쓰거나 처음부터 재작성하지 않는다.
패키지 내부 __init__.py와 실행 진입점은 해당 기능 구현에 함께 포함한다.

## 제공 인터페이스

Settings.load(path: Path) -> Settings; select_tcad_url(settings) -> str; 실행 모드 enum IntegrationMode(mock, prod).

## 실패부터 작성할 테스트

- test_default_modes_are_mock: 두 모드 모두 mock이고 선택 주소가 TCAD_MOCK_URL이다.
- test_modes_are_independent: 네 조합에서 선택 주소와 모의 Unity 실행 여부가 표와 일치한다.
- test_prod_missing_url_fails: prod URL 누락·알 수 없는 플래그를 시작 오류로 처리한다.
- test_inherits_ros_environment: 기존 ROS_DOMAIN_ID/RMW_IMPLEMENTATION을 덮어쓰지 않는다.
- test_secrets_are_redacted: 설정 표현·오류 문자열에 테스트 비밀번호가 없다.

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
python -m pytest services/event_gateway/tests/unit/test_config.py -v
```

DB 테스트는 설정 로더가 로컬 .env의 TEST_DATABASE_URL을 읽는다. 명령에 실제 비밀번호를 넣지 않는다.
기대 결과는 해당 태스크 모든 테스트 PASS이며 아직 존재하지 않는 파일의 명령은 구현 후 사용한다.

## 구현 결정

설정 검증을 네트워크 연결 전에 실행한다. env 파일은 명시 경로로 읽고 기존 환경변수가 우선한다. .env*는 제외하되 !.env.example은 추적한다. Jetson용 설정과 Gateway용 비밀을 분리한다. 실제 .env를 만들 때 기존 키를 보존하고 제공된 값만 사용한다. TCAD_PROD_URL은 빈 값으로 두며 mock에서 허용한다. Python 패키지 버전은 기존 pyproject를 보완하고 프로젝트 가상환경에만 설치한다.

## 완료 조건과 커밋

위 테스트 전체 통과, 인터페이스 일치, 기존 동작 회귀 없음이 완료 기준이다.
Jetson·실제 외부 서비스가 없어서 실행하지 못한 항목은 완료로 체크하지 않는다.
기능 브랜치에서 다음 타입의 커밋으로 기록한다.

```text
build(config): mock/prod 환경변수 계약 추가
```
