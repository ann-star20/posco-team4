# gate_workspace — Event Gateway & Jetson Bridge

Virtual Fab 통합 시스템에서 **Unity ↔ Jetson ↔ TCAD 워크스테이션을 중개하는 Gateway**와
**Jetson ROS2 워커 코드**를 담당하는 파트입니다. `tcad/`(TCAD 모델·진단 에이전트)와
`unity/`(Unity 디지털 트윈)는 각자 폴더에서 별도로 관리됩니다.

## 역할

- Unity의 AOI/Surrogate/Diagnosis 요청을 받아 DB(Aiven PostgreSQL)에 기록하고 ROS2로
  Jetson에 전달 (`services/event_gateway`)
- Jetson이 보낸 결과 이벤트를 at-least-once로 수신·커밋하고 Unity에 리플레이
  (`/api/v1/stream`, `/api/v1/events`)
- TCAD 워크스테이션에 보정 후보를 비동기로 제출·폴링하고, 규격(vth/bv) 판정 후
  Unity 승인 API(`GET/POST /api/v1/tcad/proposals(/decision)`) 제공
- Jetson 쪽 ROS2 노드(카메라 프리뷰, AOI 직접검사, Surrogate/Diagnosis 워커)
  (`jetson_ws/src/fab_virtual_lot`)

## 폴더 구조

| 경로 | 내용 |
|---|---|
| `services/event_gateway/` | FastAPI Gateway 본체 (REST + WebSocket + ROS bridge) |
| `jetson_ws/` | Jetson에서 실행되는 ROS2 패키지(`fab_virtual_lot`) 소스 |
| `database/migrations/` | PostgreSQL 스키마 마이그레이션 (001~012) |
| `scripts/` | 스택 기동 스크립트 (`ros-stack-wsl.sh`, `ros-stack-jetson.sh`) |
| `docs/` | 아키텍처, 요구사항 정의서, 인터페이스 정의서, ERD, WBS 등 |
| `tools/mock_unity/` | Unity 역할을 대신하는 시험용 클라이언트 (`full_cycle_probe.py` 등) |
| `config/`, `install/`, `build/`, `log/` | ROS2 colcon 빌드/런타임 산출물 |

## 실행

```bash
cd gate_workspace
./scripts/ros-stack-wsl.sh start --jetson-ip <Jetson IP>      # WSL(Gateway) 쪽
```
Jetson 쪽에서는:
```bash
cd project/smart_factory   # Jetson 로컬 경로
./scripts/ros-stack-jetson.sh start --wsl-ip <WSL IP>
```
둘 다 떠야 ROS2 DDS 디스커버리가 양방향으로 연결됩니다 (`./scripts/ros-stack-wsl.sh status`로 확인).

전체 사이클(노브 → Surrogate → Diagnosis → TCAD) 1회 시험:
```bash
python tools/mock_unity/full_cycle_probe.py --gateway ws://<Gateway IP>:8000 --token "$UNITY_API_TOKEN"
```

## 문서

- [`docs/architecture/current-system-architecture.md`](docs/architecture/current-system-architecture.md) — 전체 시퀀스/데이터 흐름
- [`docs/requirements/requirements-definition.md`](docs/requirements/requirements-definition.md) — 요구사항 정의서 (FR/NFR)
- [`docs/architecture/interface-definition.md`](docs/architecture/interface-definition.md) — REST/WebSocket/ROS 인터페이스 전체
- [`docs/architecture/erd.md`](docs/architecture/erd.md) — DB 스키마 ERD
- [`docs/architecture/diagnosis-routing-and-thresholds.md`](docs/architecture/diagnosis-routing-and-thresholds.md) — 진단 라우팅 기준/임계값
- [`docs/wbs/wbs.md`](docs/wbs/wbs.md) — 작업 분류 체계

## 환경 설정

Gateway는 `.env`(git에 커밋하지 않음, `.env.example` 참고)로 설정합니다. 핵심 모드 플래그:

| 변수 | 의미 |
|---|---|
| `TCAD_MODE` | `mock`/`prod` — TCAD 제출 대상(mock vs 실제 TCAD_PROD_URL) |
| `UNITY_MODE`, `SURROGATE_MODE`, `DIAGNOSIS_MODE` | 각 경계의 mock/prod 전환 |
| `TCAD_JOB_DEADLINE_SECONDS` | TCAD 작업 데드라인(실측 BV 포함 시 40분 이상 소요될 수 있음, 여유있게 설정) |
