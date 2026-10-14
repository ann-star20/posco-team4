# Jetson ROS 2 → WSL Gateway → Aiven DB 직접 확인

이 문서는 실제 Jetson에서 토픽을 발행하고 Aiven PostgreSQL의 `events` 테이블까지 저장되는지 직접 확인하는 절차다. 기본 검사는 가상 이벤트 한 건만 사용하며, 실제 ML·TCAD·Unity나 물리 장비를 제어하지 않는다. Jetson의 ROS 2·DDS·네트워크 시스템 설정을 변경하지 않는다.

## 0. 먼저 확인할 것

- Windows 저장소: `C:\posco_project`. 아래 WSL 예시는 같은 저장소가 `/mnt/c/posco_project`에 보인다고 가정한다. 다른 위치라면 `cd` 경로만 바꾼다.
- 저장소 루트의 Git 제외 `.env`에서 `DATABASE_URL`은 Aiven PostgreSQL을 가리키고 `sslmode=require`를 포함해야 한다. 로컬 Docker DB는 사용하지 않는다. `ROS_COMMAND_KEY`도 비어 있지 않아야 ROS 브리지가 시작된다. 접속 문자열과 키를 화면 공유·Git·명령 인자에 출력하지 않는다.
- Aiven의 `public` 스키마에는 001~003 마이그레이션이 적용되어 있어야 한다. 이 프로젝트의 2026-10-14 점검에서는 적용을 확인했다. 다른 Aiven DB를 쓰게 되었다면 [기존 실행 가이드](jetson-ros2-integration.md)의 마이그레이션 절차를 먼저 확인한다.
- Jetson과 WSL의 ROS 2 토픽 통신이 되어야 한다. 이미 `/fab/events`의 `hello` 수신을 확인했다면 DDS 기본 연결은 확인된 상태다. 단, `hello`는 Gateway 이벤트 JSON 계약에 맞지 않아 `events`에 정상 저장되지 않는다.
- 아래 `/opt/ros/humble/setup.bash`는 ROS 2 Humble 예시다. 실제 설치 버전이 다르면 이전에 토픽 수신을 확인할 때 사용한 setup 경로로 바꾼다.

`ROS_COMMAND_KEY`가 아직 비어 있다면 WSL에서 `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`로 임의값을 만든 뒤 저장소 루트 `.env`의 해당 항목에 넣는다. 이 값은 최소 검사에서 ROS 브리지 시작 조건으로만 필요하며, 수동 토픽 발행을 위해 Jetson에 복사할 필요는 없다. 출력값을 채팅이나 Git에 붙여넣지 않는다.

## 1. WSL: Gateway ROS 브리지 시작

WSL 터미널 A에서 실행한다. Jetson에서 토픽을 보내기 **전에** 브리지를 켠다. 이 최소 검사에서는 HTTP Gateway, 모의 TCAD, Unity를 켤 필요가 없다.

```bash
cd /mnt/c/posco_project
source /opt/ros/humble/setup.bash

# 최초 1회만: ROS Python 패키지를 볼 수 있는 WSL 전용 가상환경을 준비한다.
# 이미 필요한 패키지가 설치된 WSL Python 환경이라면 생성·설치는 생략할 수 있다.
python3 -m venv --system-site-packages "$HOME/posco-gateway-venv"
source "$HOME/posco-gateway-venv/bin/activate"
python -m pip install --no-cache-dir -e ./services/event_gateway

# 이후 실행 시에는 source "$HOME/posco-gateway-venv/bin/activate"부터 반복한다.
python -c 'import rclpy, std_msgs, psycopg, pydantic; print("Python 의존성 확인")'
export PYTHONPATH="$PWD/services/event_gateway/src"
python -m event_gateway.ros_adapter
```

`rclpy` import가 실패하면 기존 WSL ROS 환경의 Python 버전과 가상환경 Python이 같은지 확인한다. ROS 설치를 다시 하거나 Jetson의 시스템 설정을 바꾸지 않는다. `.env`는 브리지가 직접 읽는다. 이미 통신되던 `ROS_DOMAIN_ID`·`RMW_IMPLEMENTATION` 셸 환경을 그대로 유지한다.

`Failed building editable for fab-event-gateway`가 나왔던 경우에는 현재 저장소의 `services/event_gateway/pyproject.toml`에 두 패키지 경로가 명시되어 있는지 확인하고 위 `pip install --no-cache-dir -e` 명령만 다시 실행한다. 가상환경을 삭제하거나 Jetson 설정을 바꿀 필요는 없다. 다시 실패하면 마지막 `Failed building` 줄보다 앞에 있는 첫 `ValueError` 또는 `error:`부터 오류를 확인한다.

WSL 터미널 B에서는 ROS 환경을 소싱하고 ACK를 먼저 관찰한다.

```bash
source /opt/ros/humble/setup.bash
ros2 node list | grep /fab_gateway_bridge
ros2 topic echo /fab/event_acks
```

노드가 목록에 없으면 터미널 A의 오류를 먼저 해결한다. `ros2 topic echo`는 계속 실행한 채 Jetson 발행 단계로 넘어간다.

## 2. Jetson: 유효한 가상 이벤트 한 건 발행

Jetson의 기존 ROS 2 환경을 소싱한 셸에서 실행한다. 이 방법은 Jetson 프로젝트 패키지 설치나 파일 변경이 필요 없다. `RUN_ID`와 `EVENT_ID`는 매번 새로 만든다.

```bash
source /opt/ros/humble/setup.bash
export RUN_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
export EVENT_ID="$(python3 -c 'import uuid; print(uuid.uuid4())')"
EVENT_JSON="$(python3 -c 'import datetime,json,os; print(json.dumps({"schema_version":1,"event_id":os.environ["EVENT_ID"],"run_id":os.environ["RUN_ID"],"event_type":"anomaly.detected","source":"jetson.virtual_lot","severity":"warning","occurred_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"payload":{"lot_id":"MANUAL-001","input_origin":"synthetic"}},separators=(",",":")))')"

printf 'RUN_ID=%s\nEVENT_ID=%s\n' "$RUN_ID" "$EVENT_ID"
ros2 topic pub --once /fab/events std_msgs/msg/String "{data: '$EVENT_JSON'}"
```

출력된 `EVENT_ID`를 복사해 둔다. 정상 경로는 Jetson 발행 → WSL 브리지 수신 → Aiven 트랜잭션 커밋 → `/fab/event_acks`에 같은 `event_id`와 `status: committed`, 양수 `sequence` 발행이다. 수동 `ros2 topic pub --once`에는 재전송 발신함이 없으므로 브리지나 DB가 끊긴 상태에서 보내면 다시 새 이벤트로 발행해야 한다.

## 3. WSL: Aiven 실제 적재 확인

WSL 터미널 C에서 저장소 루트와 위 가상환경을 사용한다. `EVENT_ID`에 Jetson에서 출력된 값을 붙여 넣는다. 아래 코드는 `.env`의 실제 `DATABASE_URL`로 Aiven에 접속하며 비밀번호를 출력하지 않는다.

```bash
cd /mnt/c/posco_project
source "$HOME/posco-gateway-venv/bin/activate"
export PYTHONPATH="$PWD/services/event_gateway/src"
export EVENT_ID='Jetson에서 출력된 EVENT_ID'
python - <<'PY'
import os
from pathlib import Path
from uuid import UUID

import psycopg
from event_gateway.config import Settings

settings = Settings.load(Path('.env'))
with psycopg.connect(settings.database_url, connect_timeout=10) as db:
    row = db.execute(
        'SELECT sequence, run_id, event_id, event_type, source, received_at '
        'FROM public.events WHERE event_id = %s',
        (UUID(os.environ['EVENT_ID']),),
    ).fetchone()
print(row if row else '미적재: 브리지 로그와 ACK를 확인하세요')
PY
```

한 행이 나오고 `event_type`이 `anomaly.detected`, `source`가 `jetson.virtual_lot`이면 실제 Aiven 적재를 확인한 것이다. 이 최소 검사에서는 `correction_proposals`나 `verification_jobs`가 생성되지 않는 것이 정상이다.

## 4. 선택: Jetson 데모 발행기와 모의 TCAD까지

이 단계는 Jetson 프로젝트 경로에 `fab_virtual_lot` 패키지를 안전하게 배치한 뒤에만 실행한다. 배치 전 확인·백업 기준은 [기존 실행 가이드](jetson-ros2-integration.md)를 따른다. 데모 발행기는 시작할 때 `anomaly.detected`와 `correction.proposed`를 한 건씩 로컬 SQLite 발신함에 넣고, Aiven 커밋 ACK를 받을 때까지 재발행한다. 이 SQLite는 네트워크 장애 대비 발신함이지 중앙 DB가 아니다.

WSL에서는 `.env`에 `DATABASE_URL`, `ROS_COMMAND_KEY`, `APPROVAL_OPERATOR`, `APPROVAL_TOKEN`을 설정한다. `APPROVAL_TOKEN`은 `ROS_COMMAND_KEY`와 다른 임의값으로 만든다. `TCAD_MODE=mock`, `UNITY_MODE=mock`으로 두고, 브리지를 포함한 전체 로컬 프로세스를 **한 번만** 시작한다. 1번에서 단독 실행한 브리지는 먼저 `Ctrl+C`로 종료한다.

```bash
cd /mnt/c/posco_project
source /opt/ros/humble/setup.bash
source "$HOME/posco-gateway-venv/bin/activate"
bash scripts/run-integration.sh
```

Jetson에서는 프로젝트의 기존 `.env`에 WSL과 **동일한** `ROS_COMMAND_KEY`를 안전하게 설정한다. 이번에는 데모 발행기만 실행하며 명령 구독자나 승인 단계는 필요하지 않다.

```bash
cd /home/jetson/project/smart_factory/jetson_ws
source /opt/ros/humble/setup.bash
set -a
source ../.env
set +a
colcon build --packages-select fab_virtual_lot
source install/setup.bash
ros2 run fab_virtual_lot fab_demo_publisher
```

다른 Jetson 셸에서 `cat /home/jetson/project/smart_factory/data/demo-run-id`로 `RUN_ID`를 확인한다. WSL의 `/fab/event_acks`에서 두 이벤트의 커밋을 보고, 다음처럼 Aiven 상태를 조회한다. 모의 TCAD가 정상 실행 중이면 `verification_jobs`가 `succeeded`, `correction_proposals`가 `verified`가 되는지 확인한다. 결과가 `verified`여도 사람 승인 전에는 가상 레시피가 자동 적용되지 않는다.

```bash
cd /mnt/c/posco_project
source "$HOME/posco-gateway-venv/bin/activate"
export PYTHONPATH="$PWD/services/event_gateway/src"
export RUN_ID='Jetson의 data/demo-run-id 값'
python - <<'PY'
import os
from pathlib import Path
from uuid import UUID

import psycopg
from event_gateway.config import Settings

settings = Settings.load(Path('.env'))
run_id = UUID(os.environ['RUN_ID'])
with psycopg.connect(settings.database_url, connect_timeout=10) as db:
    print('events:', db.execute(
        'SELECT sequence, event_type FROM public.events WHERE run_id=%s ORDER BY sequence',
        (run_id,),
    ).fetchall())
    print('proposals:', db.execute(
        'SELECT proposal_id, status, result_origin FROM public.correction_proposals '
        'WHERE run_id=%s', (run_id,),
    ).fetchall())
    print('jobs:', db.execute(
        'SELECT j.request_id, j.status, j.attempt_count '
        'FROM public.verification_jobs j '
        'JOIN public.correction_proposals p USING (proposal_id) WHERE p.run_id=%s',
        (run_id,),
    ).fetchall())
PY
```

## 결과가 없을 때

1. WSL에서 `/fab/events`가 보이지 않으면 Jetson·WSL의 ROS 환경, 기존 DDS 통신, 토픽 이름을 확인한다. 이미 동작하던 OS 네트워크 설정은 임의로 바꾸지 않는다.
2. 토픽은 보이나 ACK가 없으면 WSL 브리지 터미널의 오류를 확인한다. `.env`의 `ROS_COMMAND_KEY`와 Aiven `DATABASE_URL` 설정, WSL에서 Aiven 접속 가능 여부를 점검한다.
3. ACK가 `dead_lettered`이면 `public.dead_letters`의 `error_code`를 확인한다. `hello`나 필드가 빠진 JSON은 정상 이벤트로 적재되지 않는다.
4. ACK가 `committed`인데 조회가 비어 있으면 복사한 `EVENT_ID`와 조회 환경의 `.env`가 발행 때 사용한 것과 같은지 확인한다.
5. `correction.proposed`가 저장됐지만 검증이 진행되지 않으면 모의 TCAD 서버와 verification worker가 실행 중인지 확인한다. 최소 검사에는 이 두 프로세스가 필요하지 않다.
