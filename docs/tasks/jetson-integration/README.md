# 태스크별 코딩 안내

[최종 계획](../../plans/jetson-tcad-unity-integration-tdd-plan.md)을 먼저 읽고 아래 순서대로 구현한다.
문서 상태는 모두 구현 전이다. 각 태스크의 테스트를 먼저 실패시키고 구현 후 통과 여부를 기록한다.

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
