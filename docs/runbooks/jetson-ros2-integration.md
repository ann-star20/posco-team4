# Jetson ROS 2 · Gateway · PostgreSQL 모의 통합 실행

Jetson에서 한 건을 발행하고 Aiven DB 적재를 직접 확인하려면 [단계별 수동 확인 가이드](manual-ros2-aiven-check.md)를 먼저 따른다.

## 범위와 안전 경계

이 절차는 가상 로트와 모의 TCAD/Unity 계약을 검증한다. 실제 ML, Silvaco, Unity 화면은 포함하지 않는다. Jetson의 JetPack, ROS 2, DDS, 네트워크, 시스템 Python 설정은 변경하지 않는다. Jetson에서는 `/home/jetson/project/smart_factory` 아래의 워크스페이스와 `data/`만 사용한다. 물리 장비 제어는 없다.

`.env`는 Git에서 제외한다. `.env.example`을 참고해 로컬에만 `DATABASE_URL`, `TEST_DATABASE_URL`, `JETSON_HOST`, `JETSON_USER`, `JETSON_PASSWORD`, `APPROVAL_OPERATOR`, 임의의 긴 `APPROVAL_TOKEN`, `ROS_COMMAND_KEY`를 설정한다. 두 비밀 토큰은 서로 다른 임의값을 사용한다. 비밀번호·토큰을 명령 인자나 문서에 붙여넣지 않는다. Jetson IP는 변경될 수 있으므로 매일 접속 전 `.env` 값을 확인한다. `ROS_DOMAIN_ID`, `RMW_IMPLEMENTATION`은 지정하지 않으면 현재 셸 값을 상속한다.

## 1. PC/WSL 준비

1. Gateway가 실제 사용하는 `.env`의 `DATABASE_URL`을 Aiven PostgreSQL 연결 문자열(`sslmode=require`)로 설정한다. 로컬 Docker PostgreSQL은 이 실행 경로에 필요하지 않다. 비밀번호가 포함된 URL은 Git이나 실행 로그에 출력하지 않는다.
2. `TEST_DATABASE_URL`도 Aiven을 사용할 수 있다. 테스트는 고유 임시 스키마를 만들어 해당 스키마만 제거하므로 기존 `public` 데이터와 분리된다. Gateway와 테스트를 실행하는 각각의 환경에서 Aiven 호스트·포트 및 TLS 연결을 확인한다.
3. Python 3.10 이상 환경에 `pip install -e "services/event_gateway[test]"`를 실행한다. WSL에서 ROS bridge를 실행할 Python에는 `rclpy`와 `std_msgs`가 이미 설치된 ROS 환경을 사용한다.
4. 저장소 루트에서 `python -m event_gateway.migrate`로 Aiven의 `public` 스키마를 읽기 전용 점검한다. 기존 001과 정확히 같은 `events` 테이블이 있다면 `python -m event_gateway.migrate --adopt-existing-001`을 한 번만 실행한다. 이후 `python -m event_gateway.migrate --apply`로 미적용 DDL만 적용한다. 운영 데이터 삭제·재생성은 하지 않는다.
5. `TCAD_MODE=mock`, `UNITY_MODE=mock`으로 시작한다. PowerShell에서는 `scripts/run-integration.ps1`, WSL에서는 ROS 환경을 먼저 소싱하고 `bash scripts/run-integration.sh`를 실행한다. 두 스크립트를 동시에 실행하지 않는다.

## 2. Jetson 프로젝트 코드 배치

Jetson 접속은 `.env`의 호스트/계정으로 현재 주소와 대상 경로를 읽기 전용 확인한 뒤 진행한다. 저장소의 `jetson_ws/src/fab_virtual_lot` 패키지만 Jetson의 프로젝트 경로 아래 `jetson_ws/src/fab_virtual_lot`에 복사한다. 기존 동일 경로 파일이 있으면 덮어쓰기 전에 diff와 백업을 확인한다. 시스템 경로에는 복사하지 않는다.

Jetson에서는 프로젝트 경로의 `.env`에 동일한 `ROS_COMMAND_KEY`를 안전하게 보관하고 실행 셸에서만 환경변수로 읽는다. 저장소로 커밋하지 않으며 전역 셸 프로필이나 OS 설정에는 추가하지 않는다. 기존 ROS 2 셸 환경을 소싱한 후 프로젝트 디렉터리에서 다음을 실행한다.

```bash
cd /home/jetson/project/smart_factory/jetson_ws
set -a
source ../.env
set +a
colcon build --packages-select fab_virtual_lot
source install/setup.bash
ros2 run fab_virtual_lot fab_demo_publisher
```

별도 셸에서 같은 환경을 소싱하고 `ros2 run fab_virtual_lot fab_command_subscriber`를 실행한다. 발신함은 프로젝트 `data/event-outbox.sqlite`, 가상 레시피는 `data/recipes.sqlite`에 보관한다. 둘은 PostgreSQL을 대체하지 않는다. DB 커밋 ACK가 올 때까지 이벤트를 재발행한다.

`ROS_COMMAND_KEY`가 없으면 브리지와 명령 구독자는 시작하지 않는다. 키가 다른 명령이나 적용 영수증은 거부되며, 처리 불가능한 ROS 메시지는 PostgreSQL `dead_letters`에 원문과 오류 코드로 보존한다. 식별 가능한 메시지는 격리 ACK 이후 Jetson 발신함에서 재전송을 멈추지만 발신함 원문은 유지한다. 식별자조차 없는 메시지는 ACK가 불가능하므로 `dead_letters`를 보고 수동 조치한다.

## 3. 경로 확인

- WSL: `ros2 topic echo /fab/events`와 `ros2 topic echo /fab/event_acks`로 발행과 커밋 확인.
- PostgreSQL: `integration_runs`, `events`, `correction_proposals`, `verification_jobs`, `commands` 건수와 상태 확인.
- Gateway: `GET /health/live`, `GET /api/v1/events?run_id=<UUID>&after_sequence=0` 확인.
- 모의 Unity: `FAB_RUN_ID`를 실제 run ID로 설정하고 `python tools/mock_unity/client.py` 실행. 수신 후 `data/mock-unity-cursor.txt`가 갱신된다. 재시작 시 해당 커서 이후 DB 이벤트를 재생한다.
- 승인은 자동으로 하지 않는다. 검증 결과가 `verified`일 때 운영자가 `POST /api/v1/proposals/{id}/approval`에 `{"approved_by":"<APPROVAL_OPERATOR>","effective_from_lot":"LOT-2"}`를 보내며 `X-Approval-Token` 헤더에 로컬 비밀값을 넣는다. 운영자 식별은 서버 설정과 일치해야 하며 토큰이 없으면 401 또는 503이다. mock 결과는 run의 `UNITY_MODE=prod`에서 승인할 수 없다.
- 가상 적용 이벤트가 ACK되면 `commands.status=applied`와 `correction_proposals.status=applied`가 된다.

## 테스트

`python -m pytest -q`는 `TEST_DATABASE_URL`의 DB에 고유 임시 스키마를 만들고 테스트 종료 시 그 스키마만 제거한다. `DATABASE_URL`과 같은 Aiven DB를 가리켜도 기존 `public.events`를 삭제하지 않는다. 실제 Jetson ROS 왕복, 실제 TCAD, 실제 Unity는 별도 실연동 시험이며 이 명령의 합격으로 대체하지 않는다.
