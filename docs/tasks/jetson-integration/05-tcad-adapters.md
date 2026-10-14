# 태스크 05: TCAD mock HTTP 서버와 prod 클라이언트

상태: 일부 구현 / 실제 TCAD 미검증
선행 작업: 01~03
기준: [최종 계획](../../plans/jetson-tcad-unity-integration-tdd-plan.md), [아키텍처](../../architecture/jetson-ros2-tcad-unity-integration.md)

## 수정 대상

- `services/event_gateway/src/event_gateway/tcad_client.py`
- `services/event_gateway/src/event_gateway/verification_worker.py`
- `services/mock_tcad/app.py`
- `services/mock_tcad/store.py`
- `services/event_gateway/tests/unit/test_tcad_client.py`
- `services/event_gateway/tests/integration/test_verification_worker.py`

기존 파일이면 수정한다. feat/event-contract에 이미 존재하는 기능을 덮어쓰거나 처음부터 재작성하지 않는다.
패키지 내부 __init__.py와 실행 진입점은 해당 기능 구현에 함께 포함한다.

## 제공 인터페이스

TcadClient.submit(request, endpoint) -> AcceptedJob; TcadClient.poll(job_id, endpoint) -> VerificationResult; Worker.run_once() -> Summary; Repository.claim_job() -> JobLease.

## 실패부터 작성할 테스트

- test_modes_use_same_http_contract: 실제 로컬 HTTP 서버에서 mock/prod 선택을 같은 계약으로 시험한다.
- test_mock_restart_preserves_request: 모의 서버 재시작 후 동일 ID가 같은 job_id를 반환한다.
- test_lost_acceptance_response: POST 응답 유실 재시도에서 중복 작업이 없다.
- test_lease_expiry_and_stale_result: 만료 worker 결과가 새로운 lease 작업을 덮어쓰지 않는다.
- test_switch_keeps_pinned_endpoint: 설정을 prod로 바꿔도 과거 mock 작업은 mock 주소와 출처를 유지한다.
- test_failure_scenarios: timeout/5xx 재시도, 잘못된 본문·4xx 실패 기록, out_of_spec은 rejected.
- test_prod_never_falls_back: prod 실패 시 mock 호출 0회, mock 결과를 prod로 저장하지 않는다.

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
python -m pytest services/event_gateway/tests/unit/test_tcad_client.py services/event_gateway/tests/integration/test_verification_worker.py -v
```

DB 테스트는 설정 로더가 로컬 .env의 TEST_DATABASE_URL을 읽는다. 명령에 실제 비밀번호를 넣지 않는다.
기대 결과는 해당 태스크 모든 테스트 PASS이며 아직 존재하지 않는 파일의 명령은 구현 후 사용한다.

## 구현 결정

공통 HTTP 어댑터와 endpoint 선택만 분리한다. 네트워크 중 잠금을 유지하지 않고 lease 결과 갱신을 조건부 수행한다. 202 접수 후 queued/running 조회, succeeded라도 모든 targets를 검사한다. 모의 서버 fixture는 seed 기반이며 pass/out_of_spec/timeout/server_error/malformed_response를 제공한다. 실제 TCAD API가 준비되기 전에는 prod=계약 검증 완료로만 기록한다.

## 완료 조건과 커밋

위 테스트 전체 통과, 인터페이스 일치, 기존 동작 회귀 없음이 완료 기준이다.
Jetson·실제 외부 서비스가 없어서 실행하지 못한 항목은 완료로 체크하지 않는다.
기능 브랜치에서 다음 타입의 커밋으로 기록한다.

```text
feat(tcad): mock/prod HTTP 검증 어댑터와 복구 worker 추가
```
