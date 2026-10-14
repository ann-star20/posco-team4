# 태스크 02: 공통 이벤트·보정·HTTP 계약

상태: 일부 구현 / 전체 완료 기준 검토 중
선행 작업: 01
기준: [최종 계획](../../plans/jetson-tcad-unity-integration-tdd-plan.md), [아키텍처](../../architecture/jetson-ros2-tcad-unity-integration.md)

## 수정 대상

- `services/event_gateway/src/event_gateway/contracts.py`
- `services/event_gateway/tests/unit/test_contracts.py`
- `contracts/examples/correction-proposed.json`
- `contracts/examples/verification-result.json`

기존 파일이면 수정한다. feat/event-contract에 이미 존재하는 기능을 덮어쓰거나 처음부터 재작성하지 않는다.
패키지 내부 __init__.py와 실행 진입점은 해당 기능 구현에 함께 포함한다.

## 제공 인터페이스

EventCreate와 StoredEvent는 기존 호환 유지; CorrectionProposal, VerificationRequest, VerificationResult, ApplyCommand 추가. parse_event(raw: str) -> EventCreate.

## 실패부터 작성할 테스트

- test_existing_event_fields_preserved: 기존 severity와 event_id 계약이 유지된다.
- test_candidate_arithmetic: delta 가산 오차 1e-9 이내 허용, 그 밖은 거부한다.
- test_uncontrollable_epi: epi_doping 변화량이 0이 아니면 거부한다.
- test_finite_values_and_targets: NaN/Infinity, X<=0, min>max를 거부한다.
- test_result_requires_all_outputs: vth/gm/id_on/bv 누락·잘못된 request_id·출처는 거부한다.
- test_invalid_json_does_not_stop_next: hello 문자열을 저장하지 않고 다음 정상 이벤트를 처리한다.

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
python -m pytest services/event_gateway/tests/unit/test_contracts.py -v
```

DB 테스트는 설정 로더가 로컬 .env의 TEST_DATABASE_URL을 읽는다. 명령에 실제 비밀번호를 넣지 않는다.
기대 결과는 해당 태스크 모든 테스트 PASS이며 아직 존재하지 않는 파일의 명령은 구현 후 사용한다.

## 구현 결정

schema_version=1, run_id, baseline_version, normalized_ratio를 추가한다. 기존 구버전 이벤트 이력과 신규 실행 입력을 구분한다. y_predicted는 선택이며 실제 ML 없는 예시임을 표시한다. mock seed의 고정 fixture에 테스트용 targets를 사용한다. 모든 예시는 실행 가능한 완전한 JSON이며 {} placeholder를 두지 않는다. 예시 정답 원인과 보정값은 물리적 타당성을 주장하지 않는다.

## 완료 조건과 커밋

위 테스트 전체 통과, 인터페이스 일치, 기존 동작 회귀 없음이 완료 기준이다.
Jetson·실제 외부 서비스가 없어서 실행하지 못한 항목은 완료로 체크하지 않는다.
기능 브랜치에서 다음 타입의 커밋으로 기록한다.

```text
feat(contracts): 가상 공정 이벤트와 검증 계약 정의
```
