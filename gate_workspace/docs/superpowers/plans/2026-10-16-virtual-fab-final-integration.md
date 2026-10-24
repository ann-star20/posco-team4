# Virtual Fab 최종 연동 구현 계획

> **For agentic workers:** TDD로 태스크별 구현·검증한다. 현재 작업은 기존 feat 브랜치의 변경을 보존하며 이 저장소에서 진행한다.

**Goal:** Jetson 또는 WSL 한 PC에서 가상 AOI·전기적 ML 요청을 실제 ROS로 처리하고 Aiven DB, TCAD HTTP, Unity 시험 WebSocket까지 추적·재시도할 수 있게 한다.

**Architecture:** Gateway가 작업과 결과를 PostgreSQL에 영속화하고 ROS 토픽으로 Jetson Worker에 지시한다. Worker는 inbox/outbox를 사용해 중복 실행을 막고, AOI는 환경변수로 선택한 로컬 모델과 시험 이미지/카메라를 사용한다. ML 예측은 외부 팀 모델의 요청/응답 adapter로만 연결한다. Unity는 외부 앱이며 Python mock peer로 계약을 시험한다.

**Tech Stack:** Python 3.10, ROS 2 Humble, rclpy, FastAPI, psycopg 3, PostgreSQL, SQLite(장치 outbox), OpenCV, Ultralytics(실모델 모드), pytest.

**Spec:** [검사 구조](../../architecture/process-inspection-orchestration.md), [동시성·승인](../../architecture/concurrent-stage-and-unity-approval.md), [ML 계약](../../architecture/ml-integration-contract.md), [이미지 스키마](../../database/aoi-image-storage.md).

2026-10-18 구현 기록: 핵심 mock 연계(작업 1~3의 기본 흐름, 4의 DB 적재, 5의 HTTP adapter/ROS/응답 보존, 6의 Unity 적용 ACK, 7의 전체 mock runner)가 구현됐다. 실제 ROS+HTTP+WS+Aiven으로 AOI와 ML 4가지 결과 및 조건부 TCAD·테스트 승인·Unity 적용을 확인했다. [실행/전환 가이드](../../runbooks/full-mock-process.md). 아래 체크리스트에는 아직 남은 원격 이미지 조회·취소·전체 장애/fencing 요구도 포함된다.

## 공통 제약

- Jetson 시스템 설정 변경 없음. 모든 호스트·모델·결과 경로·임계값은 `.env`로 선택한다.
- WSL 한 PC 시험도 실제 ROS 토픽과 HTTP/WS를 통과한다.
- AOI는 완성품 외관 검사이며 전기적 TCAD 호출과 분리한다.
- DB 커밋 전 committed ACK 금지. 중복 요청은 새 사진·새 결과를 만들지 않는다.
- 팀원 GP 모델 내부·실제 TCAD 계산·Unity 앱은 개발 범위 밖이다. mock/prod 경계를 제공한다.
- 실제 모델 시험에는 표시가 없는 원본 이미지를 사용한다. 주석 표시된 결과 이미지는 모델 정확도 평가에 사용하지 않는다.

## 작업 1: AOI 작업·결과 DB 계약

**Files:** `database/migrations/005_create_inference_jobs.sql`, `services/event_gateway/tests/integration/test_inference_jobs.py`, `services/event_gateway/src/event_gateway/inference_jobs.py`

- [ ] RED: 같은 request_id/같은 본문은 동일 job, 다른 본문은 충돌, 동일 제품·단계 활성 작업은 하나, 독립 작업 병렬 접수.
- [ ] GREEN: job, dispatch outbox, result, detections 테이블과 저장 함수.
- [ ] Aiven 임시 스키마 회귀 확인 후 운영 migration 적용.

## 작업 2: 제어 API와 ROS 전달

**Files:** `services/event_gateway/src/event_gateway/app.py`, `ros_adapter.py`, 신규 control/dispatch 모듈·시험.

- [ ] RED: HTTP/WS 동등 접수, DB 커밋 후 accepted, backlog 재전송, 빈번한 중복·취소.
- [ ] GREEN: `/api/v1/control`, HTTP 작업 API, `/fab/inference_requests` publish.

## 작업 3: WSL/Jetson Worker와 이미지 저장

**Files:** `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_worker.py`, capture/inference/receipt 모듈, setup.py, 테스트.

- [ ] RED: 동일 작업 1회 처리, SQLite inbox/outbox 복구, 임계값 스냅샷, mock/실모델 모드 분리, 저장 실패.
- [ ] GREEN: env 기반 model path, fixture/camera capture, 원본·annotated JPG, 결과 JSON, `/fab/events` 재전송과 ACK.
- [ ] WSL workspace 빌드와 mock ROS 실통신 테스트.

## 작업 4: 결과 DB 적재와 이미지 조회

**Files:** `repository.py`, `ros_adapter.py`, `app.py`, 이미지 메타데이터 adapter와 테스트.

- [ ] RED: 결과·검출 목록·Jetson 경로/파일명/해시의 원자적 보존, 중복/늦은 결과 거절.
- [ ] GREEN: 004 이미지 테이블 연결, 인증된 HTTP 이미지 조회, WS 커밋 이벤트 표시.

## 작업 5: 전기적 ML 계약

**Files:** Gateway ML 요청/응답, Jetson adapter, 신규 migration/시험.

- [ ] RED: JSON 원형·측정 메타데이터·버전 보존, 실패/중복/늦은 결과, 임의 TCAD 호출 금지.
- [ ] GREEN: 팀원 모델용 callable/서비스 adapter 경계, mock, 실제 ROS 결과/ACK.

## 작업 6: TCAD 검증·사람 승인·Unity 적용

**Files:** 기존 TCAD worker/commands/app/stream 확장, mock Unity peer, migration/시험.

- [ ] RED: ML 결과 저장 뒤 TCAD HTTP 1회, 관리자 인증·버전·로트 경계, Unity 명령 중복/ACK 유실/재시작.
- [ ] GREEN: 검증 결과 DB, HTTP/WS 승인, Unity 적용 outbox/상태 조회 및 적용 결과 DB.

## 작업 7: 실행 문서와 최종 E2E

- [ ] WSL 한 PC에서 Gateway + ROS bridge + Worker + TCAD mock + Unity mock 실행 명령.
- [ ] 시험 이미지로 AOI 요청 → JPG/DB/ROS ACK/WS 이벤트 직접 확인.
- [ ] 실모델 의존성이 있으면 원본 이미지로 prod 결과를 확인하고, 불가능하면 원인을 명시.
- [ ] 전체 pytest 및 Jetson 패키지 테스트, 문서의 구현 상태 갱신.

## 사전 검토 항목

- WSL Python의 ROS site package와 venv 호환성.
- WSL C: 드라이브 용량(2026-10-16 확인 4.6GB 여유), 모델 의존성 설치 영향.
- 외부 ML 팀 호출 계약/실제 TCAD·Unity 완성 여부에 따른 prod 검증 범위.
- 원본 시험 이미지 확보. 주석 결과 이미지로 정확도를 주장하지 않기.
- 기존 `commands`가 Jetson 수신을 가정하므로 Unity 적용 계약으로 바꿀 때 기존 시험과 호환성 검사.
