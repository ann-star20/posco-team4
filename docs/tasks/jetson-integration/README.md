# 태스크별 코딩 안내

[최종 계획](../../plans/jetson-tcad-unity-integration-tdd-plan.md)을 먼저 읽고 아래 순서대로 구현한다.
코드는 `feat/jetson-mock-integration`에서 구현 중이다. 아래 체크박스는 각 태스크 문서의 모든 완료 기준(실제 장비 및 복구 인수 시험 포함)을 만족했을 때만 체크한다. 현재는 전체 기준 미충족이므로 미체크를 유지한다.

현재 확인한 범위: 설정 4모드 단위 시험, PostgreSQL 001/002/003과 임시 스키마 통합 시험, ROS 발신함/명령 멱등 단위 시험, 승인·적용 ACK DB 통합 시험. 최신 검증은 42 passed, 로컬 소켓 시험 3개 제외(호스트 Windows `socket.socketpair()` 오류)이다. 세 시험은 앞선 실행에서 각각 통과했으나 최신 코드 기준 재검증이 필요하다. 실제 Jetson 설치/ROS 왕복과 전체 재시작 E2E는 미실행이다. [실행 안내](../../runbooks/jetson-ros2-integration.md)를 참고한다.

- [ ] [01 설정과 실행 모드](01-configuration.md)
- [ ] [02 공통 이벤트·보정·HTTP 계약](02-contracts.md)
- [ ] [03 추가 DDL과 멱등 저장](03-database.md)
- [ ] [04 Jetson 발신함과 WSL 구독·커밋 ACK](04-ros-durability.md)
- [ ] [05 TCAD mock HTTP 서버와 prod 클라이언트](05-tcad-adapters.md)
- [ ] [06 Unity 모의 수신기와 공통 WebSocket](06-unity-adapters.md)
- [ ] [07 가상 승인과 Jetson 보정 적용](07-approval.md)
- [ ] [08 모드별 인수 시험과 배포 안내](08-acceptance.md)

## Codex 실행 요청 예시

> 최종 TDD 계획과 통합 아키텍처를 기준으로 태스크 01부터 순서대로 구현해줘.
> 기존 feat/event-contract 구현을 이어받고 기능 브랜치에서 작업해줘.
> 태스크마다 RED/GREEN 증거와 커밋을 기록하고 문서는 한국어로 작성해줘.
> Jetson 시스템 설정을 유지하고 실제 비밀값은 .env에만 관리해줘.
> TCAD와 Unity는 기본 mock으로 검증하고 실제 서비스가 없는 prod 실연동은 별도 미실행으로 보고해줘.

실제 DB의 DDL 적용은 태스크 03의 안전 절차와 전용 테스트 스키마 검증 이후 수행한다.
