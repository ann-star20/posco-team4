# Jetson 카메라·AOI 공정 검사 TDD 구현 순서

2026-10-18 실행 갱신: 전기적 ML mock/prod HTTP adapter·ROS Worker, 원형 응답 보존, 후보 기반 TCAD 라우팅, Unity WS 적용 ACK 및 전체 mock runner를 구현했다. [현재 실행 가이드](../runbooks/full-mock-process.md)를 따른다. 아래 목록은 전체 확장 요구까지 포함하므로 모든 장애/fencing/실장비 검증 완료 선언은 아니다.

기준: 2026-10-17. [확장 설계](../architecture/process-inspection-orchestration.md)와 [시험 절차](../runbooks/process-inspection-test.md)를 따른다. Unity C# 앱은 개발 범위 밖이다. 아래 태스크는 요구사항 전체의 완료 여부를 나타내며 부분 구현이 있다. 정확한 현황과 남은 통합 시험은 [최신 구현/검증 상태](../runbooks/integration-status-and-latency.md)를 우선한다.

추가 필수 범위: [동시 요청·Unity 적용 설계의 TDD 시나리오](../architecture/concurrent-stage-and-unity-approval.md). 요청 멱등성/활성 작업 제약은 AOI에 구현됐다. 자원별 큐·fencing, Unity 명령 outbox·실제 적용 ACK, 전체 병렬·재시작·유실 시험은 남아 있다. 기존 통신 점검 통과와 구분한다.

| 태스크 | 먼저 실패시킬 시험 | 구현 범위 | 상태 |
|---|---|---|---|
| 0. 원격 HTTP/WS 경계 | mock readiness, 변경 본문의 request_id 충돌, prod 미준비, 실제 HTTP/WS 재생 일치 | TCAD 서비스 틀·mock 바인드 env·통신 점검 CLI | 구현/시험 완료 |
| 1. 카메라·모델 조사 | 알려진 원본의 해상도·채널·모델 입력 호환 확인 | 기존 jetson_phone_camera_rec.py와 모델 메타데이터 읽기 | 모델/스크립트 조사 및 WSL 실제 best.pt·원본 이미지 추론 확인. 실제 카메라 프레임은 미검증 |
| 2. 요청·DB 계약 | 중복 request_id, 같은 ID의 다른 본문, 낡은 stage version, 모드·모델 불일치 거부 | 신규 migration, inference job·공정 상태·감사 이벤트 원자적 기록 | 부분 구현: 004/005, AOI 요청 멱등성·활성 범위 제약·작업/dispatch 원자적 저장. stage version 검증·모델 고정 미완료 |
| 3. 이미지 보관 | 업로드 실패, hash 불일치, 용량 초과, 재시도, orphan 복구 | artifact ready 계약·인증된 업/다운로드·local/S3 저장 adapter | 미구현. S3 공급자는 미선정 |
| 4. 제어 WS | accepted는 DB commit 뒤, 끊긴 세션 재요청은 같은 job | /api/v1/control, /api/v1/inspection-jobs, Python 제어 시험 클라이언트 | AOI HTTP·WS 접수 및 HTTP 조회 구현. 전체 재접속/적용 ACK 클라이언트 미완료 |
| 5. Jetson mock capture/inference | inbox 저장 후 accepted, 같은 job 프레임 고정, 재시작·중복 결과 방어 | /fab/inference_requests, CAMERA_MODE=mock, AOI_MODE=mock, inbox/outbox | fixture·inbox/outbox·결과 커밋 ACK 구현. 별도 수신 accepted/실행 running 이벤트·캡처 시점 영속 고정 미완료 |
| 6. IP 카메라 prod | stale frame·연결 끊김·timeout·재연결·캡처 보존 | 확인된 스크립트 기반 capture adapter, CAMERA_SOURCE_URL | 단순 OpenCV adapter 있음. freshness·재연결·안정 캡처·실카메라 검증 미완료 |
| 7. AOI prod | 부품 없음·정상·결함·낮은 score·잘못된 ROI/전처리 | 두 모델 사전 로드, version/hash/threshold 고정, 결과 이미지·DB 결과 | WSL CPU 실모델·JPG/JSON·DB 저장 구현. 모델 버전/hash 고정·전체 평가세트·Jetson GPU 검증 미완료 |
| 8. 진단/TCAD 라우팅 | 부족한 X/Y에서 검증 금지, 외관 불량 무조건 TCAD 호출 금지 | 진단 mock·입력 계약·보정안 생성 경계 | 미구현 |
| 8a. 팀원 ML 계약 연계 | 요청/응답 JSON·Id 메타데이터 무변환 보존, 중복/늦은 결과, DB 커밋 후 ACK, 조건 충족 시 TCAD 요청 1개 | Jetson mock/prod adapter 경계·ROS 전달·DB 보존·버전별 TCAD 매핑. 모델 내부 개발 제외. [계약](../architecture/ml-integration-contract.md) | 미구현. 8의 TCAD 전달 구현 전에 수행 |
| 9. 장애 시험 | DB·HTTP·ROS·WS 단절과 재시작 시 상태·이벤트 복구 | 시험 run별 감사 추적·문서 실측 결과 | 미구현 |

태스크 0에서 현재 확인한 결과:

- Gateway 전체 pytest: 46 passed (추가 CLI 테스트 파일 생성 전 수집된 전체 suite).
- 추가 subprocess 테스트: 2 passed. 실제 HTTP 서버가 `.env` 포트에 바인드되고 CLI가 mock 성공 또는 prod 미준비를 판정했다.
- 실제 Aiven 테스트는 고유 임시 스키마를 사용했다. public 기록 삭제 없음.
- Starlette TestClient의 httpx 관련 deprecation 경고 1개가 있었으며 실패는 없었다.
- Jetson 카메라·모델·실제 Unity·Silvaco 실연동 성공을 뜻하지 않는다.

실행 명령(WSL):

```bash
cd /mnt/c/posco_project/services/event_gateway
source "$HOME/posco-gateway-venv/bin/activate"
python -m pytest -q
```

현재 시험 함수는 `tests/unit/test_tcad_service_boundary.py`, `tests/unit/test_transport_entrypoints.py`, `tests/integration/test_mock_http.py`, `tests/integration/test_stream.py`에 있다. 다음 태스크에서도 실패 시험 → 최소 구현 → 통과 확인 순서를 유지한다.
