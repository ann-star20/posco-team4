# 전체 연동 구현 상태와 WSL 지연 점검

2026-10-18 갱신: 아래 내용은 10월 17일의 미완료 상태와 지연 조사 기록이다. 이후 ML adapter·조건부 TCAD 라우팅·Unity 적용 ACK를 구현했고 실제 ROS/HTTP/WS+Aiven 전체 mock 시험이 통과했다. 현재 실행 기준은 [전체 mock 공정 가이드](full-mock-process.md)다. 아래 과거 표의 미구현 항목을 현재 상태로 읽지 않는다.

## 1. 현재 구현 상태

| 경로 | 상태 | 확인 근거와 제한 |
|---|---|---|
| HTTP/제어 WS → AOI 작업 DB → ROS 요청 | 구현 | `app.py`, `inference_jobs.py`, `ros_adapter.py`. HTTP 실제 요청 시험, 제어 WS TestClient 시험. |
| WSL/Jetson 역할 AOI → 이미지 저장 → ROS 결과 | 구현 | 모델 1회 로드, fixture 이미지, 부품·결함 bbox/score 및 JPG/JSON 저장. 실제 Jetson GPU·카메라 시험은 아님. |
| AOI 결과 → Aiven → ROS 커밋 ACK → Unity용 WS | 구현·개별 실통신 확인 | 실제 Aiven 행/이미지 메타데이터, SQLite ACK, HTTP/WS 재생 일치. 실제 Unity 앱은 범위 밖. |
| 전기적 특성 ML 요청 → Jetson 모델/mock → 결과 DB·WS | 구현·실서비스 미기동 | Gateway WebSocket/ROS dispatch, `fab_surrogate_worker`, mock HTTP 모델, DB 결과 저장은 구현됐다. 실행 순서는 `surrogate-ml-websocket-e2e.md`를 따른다. 실제 GP 모델 연결·실측 E2E는 별도 수행해야 한다. |
| ML 결과 → 조건 판정 → TCAD 검증 작업 생성 | 미구현 | 현재는 `correction.proposed` 보정안이 이미 만들어져 들어와야 검증 작업을 생성함. ML 응답만으로 생성하지 않음. |
| 보정안 → TCAD HTTP → 결과 DB → Unity용 WS | 구현·mock 시험 있음 | `verification_worker.py`, `tcad_client.py`, `mock_tcad/app.py`. VerificationWorker 별도 실행 필요. |
| TCAD HTTP Service → 실제 Silvaco | 서비스 틀만 구현 | 실제 실행·덱 생성·결과 파싱은 미구현. prod readiness는 미준비를 반환함. |
| 관리자 HTTP 승인 → 보정 명령 | 기존 경로 구현 | 현재 적용 대상은 ROS `/fab/commands`의 Jetson 가상 레시피. |
| 관리자 승인 → Unity 가상 적용 → Unity 적용 ACK → DB | 미구현 | `concurrent-stage-and-unity-approval.md`의 목표 경로. 기존 Jetson 적용 시험과 구분해야 함. |
| 모든 경로 병렬·장애·재시작 종단 간 시험 | 미완료 | 개별 중복/재시도 시험은 있으나 전체 그래프 시험은 없음. |

`test_full_flow.py`는 보정안 fixture를 repository에 직접 입력한 뒤 실제 mock HTTP, DB, WS, 승인 API와 로컬 RecipeStore를 시험한다. 실제 ROS 송수신, AOI, 팀원 ML, Unity 적용 ACK를 포함하지 않는다. 84개 pytest 통과 이력은 위 미구현 구간의 통과 증거가 아니다.

AOI 외관 불량은 전기적 ML/TCAD 검증과 별개다. 외관 결함만으로 산화막/도즈 보정 검증을 호출하지 않는다. 전기적 ML 이상 결과, 유효한 공정 입력, 검증 대상 후보와 계약이 준비된 경우에 TCAD 검증으로 연결한다. 후보 생성 책임/계약이 없는 경우 임의 값을 생성하지 않고 보류해야 한다.

## 2. 이번 지연의 관측값

작업 `bcca81a5-df67-410b-9eb2-1755314d7e3f`:

- Gateway 접수: 2026-10-17 17:29:25 KST.
- Worker SQLite 수신함 저장: 17:49:06 KST.
- 결과 JSON 저장: 17:49:08.837 KST.
- 결과 이벤트 생성: 17:49:09.089 KST.
- Aiven `received_at`: 17:49:15.832 KST.
- Gateway 디스패치 시도 548회. 완료 이벤트 sequence 15, Worker ACK 15.

약 19분 40초는 Worker 수신 전 지연이다. 약 3초는 Worker 수신 이후 이미지 읽기·대기·추론·JPG/JSON 저장을 합친 시간이며 순수 predict 계측값이 아니다. 이벤트 생성→DB received_at 약 6.7초도 ROS·Gateway 큐·DB 연결/처리를 합친 시간이며 DB 자체 실행 시간으로 단정할 수 없다.

Gateway/Worker는 같은 ROS_DOMAIN_ID=0, ROS_LOCALHOST_ONLY=0이며 `/home/user/fastdds.xml`을 상속했다. 초기 peer 주소 192.168.0.76은 당시 Windows/WSL 주소와 같았다. 오래된 IP라고 확정할 수 없다. 세 대기 작업이 발견 관찰 시점에 함께 수신됐지만, 관찰 노드가 연결을 복구했다고 인과관계를 확정할 수는 없다.

별도 도메인 87에서 기본 DDS 환경과 localhost-only 환경을 각각 시험했으나 8초 안에 구독자를 발견하지 못했다. 명시적인 loopback UDP 프로필도 별도 도메인 88~90에서 6초 안에 발견하지 못했다. 일반 localhost UDP 송수신은 성공했다. 이는 운영 도메인 0의 동일 원인을 재현했다고 단정할 수 없으며, 단일 환경변수 변경의 해결 효과도 입증하지 못한 결과다. 실패한 시험용 프로필은 제거했고 실행 중 서비스나 시스템 설정은 변경하지 않았다.

## 3. 개선 순서

1. WSL 한 PC 시험용 ROS 환경을 프로젝트 실행 스크립트 하나로 고정한다. 기존 shell 전역 DDS 설정과 구분하고, 두 프로세스의 실제 env/RMW/도메인/프로필을 출력한다. 비밀정보는 제외한다.
2. 독립 프로세스 왕복 probe로 discovery, 메시지 전달, 응답 시간을 구분한다. 현재 설정과 loopback 명시 설정을 같은 도메인 조건에서 비교하고, 실패하면 UDP discovery 패킷/포트와 WSL·Hyper-V 방화벽을 확인한다. 방화벽 전체 해제는 진단 방법으로 사용하지 않는다.
3. 멀티 호스트 환경에서는 검증된 unicast peer 또는 Discovery Server 방식을 비교한다. 설정만 바꾸고 성공으로 간주하지 않고 양방향 요청/결과/ACK를 재시작 반복 시험한다.
4. Gateway에 Worker readiness·heartbeat·미발견 사유를 노출한다. 구독자 없음은 사용자에게 `waiting_worker`로 보여야 하며, 현재처럼 재발행 횟수만 계속 증가하고 UI는 queued인 상태를 개선한다. 구독자 수만으로 모델 준비/정상 처리를 보증하지 않는다.
5. 요청 inbox 저장 ACK, 실행 시작, 결과 생성, Gateway 수신, DB 커밋, Unity 수신 시각과 구간별 소요 시간을 기록한다. 현재 미구현인 accepted/running 상태를 실제 이벤트와 연결한다.
6. 결과 ACK 전 재발행은 유지하되 재시도 간격/backoff와 진행 중 event ID 중복 큐 억제를 추가한다. 현재 Worker는 미확인 결과를 매초 보내고 Gateway는 이벤트마다 DB 연결을 새로 만든다. 중복 적재는 막혀도 큐/연결 비용이 발생하므로 계측 후 connection pool과 처리량을 조정한다.

## 4. 최종 통합 시험의 완료 조건

- AOI 정상/불량/부품 없음/파일 오류: 실제 ROS → 결과 DB → ACK → 실제 WS 수신. 정상은 pass, 결함은 fail, 검사 불능은 review/failed로 구분.
- 전기적 ML 정상: 실제 ROS 요청·mock 응답 → 요청/응답·측정 조건 DB 보존 → WS 표시, TCAD 호출 0회.
- 전기적 ML 이상 + 유효 후보: 예측 DB 보존 → 실제 TCAD mock HTTP 요청/조회 → 검증 결과 DB → WS 표시. 동일 request ID 중복 전송 시 논리적 검증 작업 1개.
- 전기적 ML 실패/입력·후보 부족: 실패/보류 DB·WS, TCAD 호출 0회.
- TCAD 통과/불합격/timeout/503: 상태와 재시도 기록, 검증 통과 전 승인·적용 금지.
- 관리자 승인: 검증된 후보와 버전에 결속 → Unity mock WS 명령 → 실제 적용 ACK → DB 완료. 표시 수신과 적용 완료를 구분.
- AOI와 ML 요청 동시 도착, 결과 순서 역전, ACK 유실, DB/ROS/HTTP/WS 단절·복구, 프로세스 재시작: 요청·결과 보존, 중복 적용 없음, 오래된 응답의 최신 상태 덮어쓰기 없음.

현재 실행 가능한 AOI 절차는 [WSL AOI 가이드](wsl-aoi-one-pc.md), TCAD HTTP 개별 시험은 [공정 검사 시험](process-inspection-test.md) 2절을 따른다. 이 목록 전체를 한 명령으로 실행하는 종단 간 runner는 아직 없다.
