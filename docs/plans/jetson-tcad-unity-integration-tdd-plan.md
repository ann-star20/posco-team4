# Jetson ROS 2 · TCAD · Unity 통합 구현 계획

> **에이전트 작업 지침:** 구현 시 `superpowers:executing-plans` 또는 `superpowers:subagent-driven-development`를 사용하고, 각 단계의 RED→GREEN 결과를 기록한다.

**목표:** Jetson의 이상·보정 이벤트를 ROS 2로 수신해 PostgreSQL에 보존하고, 별도 TCAD 워크스테이션에서 검증한 뒤 Unity에 전달하며 승인된 보정 명령을 Jetson에 돌려보낸다.

**구조:** WSL Gateway가 `/fab/events`를 구독한다. DB 커밋 후 TCAD에 비동기 HTTP 요청을 보내고 Unity에는 WebSocket으로 알린다. Unity 승인도 DB에 먼저 저장한 뒤 `/fab/commands`로 발행한다.

**기술:** Python 3.10, ROS 2 Humble, FastAPI, Pydantic 2, psycopg 3, httpx, PostgreSQL 16, pytest, Unity 2022.3 LTS, NUnit

**설계:** `docs/architecture/jetson-ros2-tcad-unity-integration.md`

## 공통 제약

- Jetson의 OS, JetPack, CUDA, ROS 2, DDS, 방화벽, `/opt/ros`, 시스템 Python, systemd를 변경하지 않는다.
- Jetson에서는 `/home/jetson/project/smart_factory` 아래만 수정한다.
- 실제 접속값은 Git에서 제외된 `.env`에만 두고 `.env.example`에는 변수명만 기록한다.
- PostgreSQL 커밋 전에는 TCAD·Unity·ROS 2로 후속 데이터를 보내지 않는다.
- `event_id`, `request_id`, `command_id`는 재시도에서도 유지한다.
- 첫 연동은 `std_msgs/msg/String` JSON을 사용한다.

## 태스크 1: 환경변수와 비밀 관리

**파일:** `.env.example`, `.gitignore`, `services/event_gateway/src/event_gateway/config.py`, `tests/unit/test_config.py`, `docs/runbooks/jetson-ros2-integration.md`

- [ ] 실제 비밀값 없이 설정 로딩·필수값·기본 ROS 토픽·비밀번호 마스킹 테스트를 작성한다.
- [ ] `python -m pytest services/event_gateway/tests/unit/test_config.py -v`가 `Settings` 부재로 실패하는지 확인한다.
- [ ] `Settings.from_env()`를 구현한다. 기본값은 `/fab/events`, `/fab/commands`, `ROS_DOMAIN_ID=0`, TCAD timeout 10초, polling 5초다.
- [ ] `.env.example`과 Jetson 무변경 배포 문서를 작성하고 `.env`가 무시되는지 검사한다.
- [ ] 테스트 통과 후 `build: add safe integration configuration`으로 커밋한다.

## 태스크 2: 이벤트 계약과 WSL ROS 2 Subscriber

**파일:** `contracts.py`, `ros_adapter.py`, `test_contracts.py`, `test_ros_adapter.py`

- [ ] `anomaly.detected`, `diagnosis.completed`, `correction.proposed`의 실패 테스트를 작성한다.
- [ ] UUID, UTC 시각, `normalized_ratio`, X/Y 키 4개, `x_candidate = x_current + delta_x`를 검증한다.
- [ ] 유형별 Pydantic 모델을 구현하고 추가 필드를 거부한다.
- [ ] 정상 메시지 전달, 잘못된 JSON 건너뛰기, 오류 후 다음 메시지 처리 테스트를 먼저 실패시킨다.
- [ ] ROS import를 adapter 경계에만 두고 callback에서는 네트워크 I/O를 하지 않는다.
- [ ] 전체 단위 테스트 후 `feat: subscribe to validated fab ROS events`로 커밋한다.

## 태스크 3: PostgreSQL 트랜잭션 저장

**파일:** `database/migrations/001_create_events.sql`, `002_create_correction_workflow.sql`, `repository.py`, `test_event_ingestion.py`

- [ ] 신규 이벤트, 동일 재전송, 내용이 다른 중복, 원자적 보정안 저장, rollback 테스트를 작성한다.
- [ ] 실제 PostgreSQL 16에서 RED를 확인한다.
- [ ] `events`, `correction_proposals`, `verification_jobs`, `commands`와 repository를 구현한다.
- [ ] `event_id`, `request_id`, `command_id`에 고유 제약을 둔다.
- [ ] 통합 테스트 통과 후 `feat: persist ROS correction workflow`로 커밋한다.

## 태스크 4: 비동기 TCAD 검증

**파일:** `tcad_client.py`, `verification_worker.py`, 관련 단위·통합 테스트, `docs/runbooks/tcad-workstation-api.md`

- [ ] `202 + job_id`, 동일 요청, timeout, `5xx`, `4xx`, 잘못된 응답 테스트를 작성한다.
- [ ] `TcadClient.submit()`과 `TcadClient.get()`을 구현하고 `request_id`를 유지한다.
- [ ] DB 커밋 후 종료, TCAD 접수 후 종료, polling 성공, 실패, 재시작 복구 테스트를 작성한다.
- [ ] worker는 `FOR UPDATE SKIP LOCKED`로 작업을 가져오고 상태 전이마다 커밋한다.
- [ ] `y_verified` 저장 후에만 `verified` 또는 `rejected`를 결정한다.
- [ ] 전체 통과 후 `feat: add durable TCAD verification worker`로 커밋한다.

## 태스크 5: Gateway와 Unity WebSocket

**파일:** `stream.py`, `app.py`, `test_unity_stream.py`

- [ ] DB 커밋 후 broadcast, 순서 재생, 재생 중 신규 이벤트, 중복, 느린 client 테스트를 작성한다.
- [ ] `GET /api/v1/events?after_sequence={n}`과 `WS /api/v1/stream?after_sequence={n}`을 구현한다.
- [ ] `correction.proposed`는 `approval_allowed=false`로 전달한다.
- [ ] replay high-water 경합을 제거하고 테스트 후 `feat: stream verified corrections to Unity`로 커밋한다.

## 태스크 6: Unity 보정 데이터와 승인

**파일:** Unity `CorrectionDataset`, `EventStreamCoordinator`, `CorrectionApprovalClient`, NUnit 테스트, Gateway `commands.py`, 승인 API 테스트

- [ ] 산화막 두께·바디 도즈·확산 시간·에피 도핑의 현재값·변화량·권장값 테스트를 작성한다.
- [ ] sequence 누락·중복 및 알 수 없는 스키마를 거부한다.
- [ ] `POST /api/v1/proposals/{id}/approval`의 실패 테스트를 작성한다.
- [ ] DB 상태가 `verified`일 때만 승인하고 그 외에는 `409`를 반환한다.
- [ ] 명령과 감사 이벤트를 한 트랜잭션으로 저장한다.
- [ ] Python·Unity 테스트 후 `feat: approve verified corrections from Unity`로 커밋한다.

## 태스크 7: Jetson Publisher·명령 Subscriber·ACK

**파일:** `jetson_ws/src/fab_virtual_lot` ROS 2 Python 패키지와 Gateway command publisher

- [ ] 가상 이상·진단·보정안 publisher의 스키마 테스트를 작성한다.
- [ ] 기존 `rclpy`, `std_msgs`만 사용하고 시스템 패키지나 서비스를 추가하지 않는다.
- [ ] `correction.apply` 명령, 중복 `command_id`, 잘못된 명령, ACK 테스트를 작성한다.
- [ ] 적용 ID를 프로젝트 경로 아래 보존해 재시작 후 중복 적용을 막는다.
- [ ] Jetson에서 `colcon test --packages-select fab_virtual_lot`가 통과하는지 확인한다.
- [ ] `feat: exchange correction commands with Jetson`으로 커밋한다.

## 태스크 8: 전체 장애 복구 시험

**파일:** `tests/e2e/test_virtual_fab_flow.py`, fake TCAD·Unity, Windows/Linux 실행 스크립트, runbook

- [ ] 이상 → 진단 → 보정안 → DB → TCAD → Unity → 승인 → ROS 명령 → ACK 테스트를 작성한다.
- [ ] Gateway 재시작, TCAD 중단, 중복 ROS 이벤트, Unity 단절, 중복 승인·명령을 추가한다.
- [ ] 로컬에서는 fake TCAD·Unity를 사용하고 실제 Jetson 시험은 시스템을 변경하지 않는다.
- [ ] Python·Unity·Jetson 테스트를 모두 실행한다.
- [ ] `test: verify virtual fab correction flow`로 커밋한다.

## 최종 인수 조건

- [ ] Jetson 이벤트가 원래 `event_id`로 DB에 한 번 저장된다.
- [ ] 보정안은 TCAD HTTP 요청 전에 DB 작업으로 저장된다.
- [ ] TCAD 중단 후에도 원래 작업이 중복 없이 완료된다.
- [ ] Unity가 산화막 두께와 바디 도즈의 현재값·변화량·권장값을 받는다.
- [ ] `verified` 보정안만 승인 명령을 생성한다.
- [ ] Jetson이 동일 `command_id`를 한 번만 적용하고 ACK를 반환한다.
- [ ] 실제 비밀번호, IP, DB URL이 Git에 없다.
- [ ] Jetson 시스템 설정과 프로젝트 경로 밖 파일을 변경하지 않는다.
