# Jetson · TCAD · Unity 최종 TDD 구현 계획

작성일: 2026-10-14
상태: 구현 진행 중 / 실제 Jetson·TCAD·Unity 실연동은 미검증
언어: 문서·설명은 한국어, 코드 식별자·프로토콜은 원문 유지

## 목표

TCAD와 Unity가 없어도 mock/mock으로 Jetson→ROS 2→Gateway→PostgreSQL→HTTP 검증→WebSocket 결과 전달을 시험한다.
두 서비스가 준비되면 TCAD_MODE와 UNITY_MODE를 각각 prod로 바꿔 같은 계약으로 연결한다.
현재 단계에서는 실제 Silvaco 실행과 Unity 화면 구현을 완료 조건에 넣지 않는다.

2026-10-14 구현 기록: `feat/jetson-mock-integration`에서 설정·계약·DDL·ROS 발신함/브리지·모의 TCAD·Gateway WebSocket·가상 승인/서명 명령·dead-letter 코드를 작성했다. 개발 PostgreSQL의 기존 `events` 구조를 검증해 001 이력을 채택하고 002/003을 적용했다. 최신 검증은 42개 통과, 로컬 소켓 시험 3개는 현재 Windows 실행 환경의 `socket.socketpair()` 오류로 미검증이다. 세 시험은 이전 실행에서 각각 통과했으나 최신 코드 전체 통과로 표시하지 않는다. 실제 Jetson 패키지 배포/ROS 왕복, 서비스 재시작 E2E, 실제 TCAD/Unity 연동은 아직 수행하지 않았다.

기준 문서:

- [통합 아키텍처](../architecture/jetson-ros2-tcad-unity-integration.md)
- [DDL 변경 명세](../database/integration-schema.md)
- [태스크별 파일 모음](../tasks/jetson-integration/README.md)

## 1. 구현 시작 시 반드시 확인할 저장소 상태

기존 계약·001 DDL·5개 테스트는 feat/event-contract의 66adde9에 있다.
현재 docs/jetson-tcad-integration은 그 코드 커밋을 포함하지 않은 문서 브랜치다.
구현자는 두 이력을 확인하고 feat/jetson-mock-integration 브랜치에 문서와 기존 코드를 통합한다.
문서 브랜치를 기준으로 코드를 삭제하거나 001을 새로 생성하지 않는다. main에 직접 커밋하지 않는다.
기존 테스트의 DROP TABLE events와 하드코딩 DSN은 태스크 03에서 안전한 테스트 스키마 방식으로 교체한다.

현재 로컬 실제 비밀을 포함한 .env가 있다고 가정하지 않는다.
태스크 01에서 존재 여부만 확인하고 제공받은 값으로 생성·보완하되 Git 제외를 먼저 확인한다.
prod TCAD 주소는 미제공이므로 빈 값으로 두고 mock으로 실행한다.

## 2. 공통 구현 규칙

1. Red → Green → Refactor를 행동 단위로 반복하고 관찰한 실패·성공을 기록한다.
2. Jetson OS·JetPack·DDS·ROS 설치와 시스템 Python은 유지한다. 프로젝트 경로 내 코드·데이터만 수정한다.
3. ROS_DOMAIN_ID/RMW_IMPLEMENTATION은 현재 셸 값 상속이다. 설정 로더가 기본값을 강제로 덮어쓰지 않는다.
4. 이벤트 생산자는 발신함 커밋→발행→DB 커밋 ACK 순서를 지킨다.
5. mock 결과는 출처를 표시하고 prod Unity 승인 경로에 섞지 않는다.
6. PostgreSQL은 모든 모드에서 실제 사용한다. 외부 모드와 저장소 mock 여부를 연결하지 않는다.
7. 기존 계약 EventCreate/StoredEvent를 이어받고 severity 등 기존 필드를 삭제하지 않는다.
8. 명령·검증은 트랜잭션과 영속 작업을 통해 복구한다. 네트워크 I/O 중 DB 잠금을 유지하지 않는다.
9. 테스트 비밀값은 가짜 fixture만 사용한다. 실제 접속값이 traceback·Git·문서에 남지 않게 한다.
10. 각 태스크 완료 후 체크박스·검증 결과·커밋 해시를 기록한다. 전체 구현은 executing-plans 방식으로 순차 실행한다.

## 3. 태스크 순서

| 순서 | 구현 문서 | 산출물 |
|---|---|---|
| 01 | [설정과 실행 모드](../tasks/jetson-integration/01-configuration.md) | 모드·.env 설정 |
| 02 | [공통 이벤트·보정·HTTP 계약](../tasks/jetson-integration/02-contracts.md) | JSON 계약 |
| 03 | [추가 DDL과 멱등 저장](../tasks/jetson-integration/03-database.md) | 추가 DDL·트랜잭션 |
| 04 | [Jetson 발신함과 WSL 구독·커밋 ACK](../tasks/jetson-integration/04-ros-durability.md) | ROS 발신함·ACK |
| 05 | [TCAD mock HTTP 서버와 prod 클라이언트](../tasks/jetson-integration/05-tcad-adapters.md) | 모의 TCAD·prod 어댑터 |
| 06 | [Unity 모의 수신기와 공통 WebSocket](../tasks/jetson-integration/06-unity-adapters.md) | 모의 Unity·WS 재생 |
| 07 | [가상 승인과 Jetson 보정 적용](../tasks/jetson-integration/07-approval.md) | 사람 승인·가상 적용 |
| 08 | [모드별 인수 시험과 배포 안내](../tasks/jetson-integration/08-acceptance.md) | E2E·실행 안내 |

태스크 의존성: 01→02→03→04→05→06→07→08.
각 상세 문서에 대상 파일, 인터페이스, 실패 사례, 검증 명령, 완료 기준, 커밋 타입을 기재했다.

## 4. 실행 환경과 테스트 준비

- Gateway는 Python 3.10 호환 코드를 작성한다. 로컬 테스트 런타임과 실제 Jetson 런타임 버전을 각각 기록한다.
- 기존 pyproject.toml에 pytest, httpx, WebSocket 테스트 의존성을 추가하고 프로젝트 가상환경에서 설치한다.
- 루트 pytest 설정에서 Gateway src와 Jetson 패키지 경로를 등록해 위 태스크 명령이 동일하게 동작하게 한다.
- ROS import는 경계 모듈에 한정하여 비ROS 환경에서도 계약·저장소·worker 단위 테스트를 실행한다.
- TEST_DATABASE_URL을 이용한 전용 테스트 DB·임시 스키마를 사용한다. PostgreSQL 없이 통합 테스트를 통과했다고 표시하지 않는다.
- 실제 ROS 송수신 시험은 이미 연결 확인된 WSL↔Jetson에서 별도로 실행한다.
- fixture의 pass 결과는 각 targets의 중앙값, out_of_spec은 vth 상한 초과로 정의한다. seed는 재현 가능 식별용이며 물리 예측으로 쓰지 않는다.
- timeout과 재시도 시간은 주입 가능한 clock으로 단위 시험하고 실제 HTTP/WS E2E에서는 제한 시간을 둔다.

## 5. 중점 회귀 시험

| 위험 | 담당 태스크 | 기대 동작 |
|---|---|---|
| 기존 ROS 설정 덮어쓰기 | 01, 04 | 기존 세션 상속 |
| ROS 수신 전 Gateway 종료 | 04 | Jetson 발신함에서 재전송 |
| DB 성공 후 ACK 유실 | 03, 04 | 한 행 유지, 같은 receipt 재응답 |
| DB 성공 후 TCAD 호출 전 종료 | 05 | DB queued 작업 재개 |
| TCAD 접수 응답 유실 | 05 | 같은 request_id와 원격 job 유지 |
| mock→prod 설정 변경 | 05, 07 | 기존 작업 모드 고정, mock 운영 승인 거부 |
| 두 DB 트랜잭션 커밋 역전 | 03, 06 | 커서 누락 방지 공통 이벤트 잠금 |
| sequence 번호 공백 | 06 | 연속성 오류로 처리하지 않음 |
| Unity 연결 단절 | 06 | DB 커서 재생 |
| 중복 승인·명령 적용 | 07 | command 1개, 가상 레시피 적용 1회 |
| 실제 DB 테스트 실행 | 03, 08 | 기존 데이터 삭제 없음 |

## 6. 모드별 완료 판정

- [ ] mock/mock: 실제 PostgreSQL + 모의 HTTP 서버 + 모의 WS 수신기로 전체 E2E 통과.
- [ ] 네 조합: 로컬 계약 서버로 prod 어댑터 설정·오류·모드 선택 시험 통과.
- [ ] 실제 Jetson: 이벤트 발행·DB ACK·단절 후 재전송 확인.
- [ ] 실제 TCAD: API와 기준값·단위 매핑 제공 후 별도 실연동 시험. 현재 미실행.
- [ ] 실제 Unity: 클라이언트 완성 후 화면·재연결·승인 시험. 현재 미실행.

prod 플래그 설정만으로 실제 서비스 검증 완료라고 표시하지 않는다.

## 7. 이번 문서 검토에서 변경한 점

- TCAD/Unity 독립 플래그와 네 조합을 확정했다.
- Unity 서버라는 표현을 Gateway WebSocket 서버와 Unity 수신 클라이언트로 구체화했다.
- Jetson 발신함·영속 저장 ACK를 추가해 DDS 연결 확인과 이벤트 보존을 구분했다.
- 실행 모드·결과 출처·lease를 위한 추가 DDL을 정의했다.
- 기존 DDL은 보존하고 마이그레이션 이력 및 데이터 보호 시험을 추가했다.
- TCAD 성공 응답과 공정 스펙 합격을 별도 상태로 구분했다.
- 실제 ML·TCAD·Unity 미완성은 명시하고 현재 구현은 모의 입력과 계약 연결에 집중한다.
