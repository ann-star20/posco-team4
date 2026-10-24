# Unity → Gateway 비동기 TCAD 연동 테스트

2026-10-21 설계 기준. **기존 설비 검사 버튼의 연동은 변경하지 않는 독립 테스트**입니다.

## Unity에서 열기

Play를 끈 상태에서 새 파일을 가져온 뒤 메뉴 **MOSFET → Gateway → TCAD 비동기 연동 테스트**를 선택합니다.

1. **오프라인 계약 테스트 실행**: 서버에 전송하지 않습니다.
2. Gateway 주소에는 `ws://192.168.213.12:8000`을 입력합니다. 경로는 테스트 코드가 붙입니다.
3. Gateway 요청 토큰을 입력합니다. 토큰은 파일에 저장하지 않습니다. TCAD 토큰은 Unity에 필요 없습니다.
4. **팀원 확인 예시 불러오기**를 누르면 제공받은 통신 시험값을 채웁니다. 실제 검사 시험에는 해당 검사의 input_payload로 바꾸세요.
5. **새 진단 요청 JSON 만들기**로 전송 내용을 확인합니다. 이 단계에서는 전송하지 않습니다.
6. **Gateway에 한 번 전송 + 결과 구독**을 누릅니다. 서버 설정에 따라 실제 TCAD 작업이 생성될 수 있습니다.
7. 중지 후 **결과만 재접속**하면 마지막 sequence 이후를 받습니다. 진단 요청은 다시 보내지 않습니다.
8. Unity를 다시 열었다면 **저장된 테스트 다시 열기**에서 Runs/<request_id>/request.json을 선택한 뒤 결과만 재접속합니다. 이때 sequence 0부터 재생해 후보 상태를 복원합니다.

`request.accepted`는 접수 확인입니다. TCAD 완료나 승인으로 취급하지 않습니다. 접수 응답이 끊겨 확인되지 않았다면 저장된 request_id로 Gateway 담당자에게 조회를 요청하세요. 자동 재전송은 없습니다.

## Unity 요청

요청 연결: `ws://192.168.213.12:8000/api/v1/control`

헤더: `X-Unity-Token: <Gateway 요청 토큰>`

```json
{
  "type": "diagnosis.requested",
  "schema_version": 1,
  "request_id": "<새 진단 UUID>",
  "run_id": "<공정 실행 UUID>",
  "lot_id": "LOT-001",
  "unit_id": "MOSFET-001",
  "stage_id": "electrical",
  "stage_attempt": 1,
  "model_contract_version": "fab-ml-v1",
  "input_payload": {
    "measurements": { "vth": 2.874, "gm": 3.767, "id_on": 3.468, "bv": 44.186 },
    "n_wafers": 25,
    "refine": false
  }
}
```

입력 형식은 사용자가 전달한 서비스 직접 시험 결과로 확인했습니다. 숫자는 팀원의 예시이며 현재 LOT의 실측값이라는 뜻은 아닙니다. `diagnosis-input.example.json`에 같은 입력을 저장했습니다.

- vth/BV: V, gm: µS/µm, id_on: µA/µm. 이미 µ 단위인 값을 1e6으로 다시 환산하지 않습니다. 기존 A/V/µm·A/µm 진단 워커 자료는 같은 값으로 취급하지 않습니다.
- 측정하지 않은 BV는 `"bv": null`로 명시합니다. 생략을 거절합니다.
- n_wafers는 실제 평균에 사용한 웨이퍼 장수(정수 1~100000)입니다. 한 장이면 1이며 신뢰도를 높이려고 임의로 25를 넣으면 안 됩니다.
- 현재 Jetson은 `refine:false`만 사용합니다.
- 테스트는 필수 필드·유한 숫자·장수·refine을 검증하지만 숫자만으로 단위 오류를 확정할 수는 없습니다.

### Gateway와 서비스의 task_type 차이

서비스에는 반드시 `task_type:"diagnosis"`가 도착해야 합니다. Unity가 쓰는 `type:"diagnosis.requested"`만으로는 서비스가 진단으로 인식하지 않습니다.

다만 저장된 Gateway DiagnosisRequest 스키마는 추가 필드를 거절하며 task_type을 정의하지 않습니다. 따라서 현재 테스트는 **Unity → Gateway에는 type, Gateway Worker → 서비스에는 task_type**을 쓰는 경계를 유지합니다. BuildWorkerRequest는 이 변환의 기대 결과를 생성하는 테스트 도우미이며 실제 Gateway Worker를 수정한 것이 아닙니다. 로컬 모의 Gateway가 이 도우미를 호출하는 시험만 통과했으므로, 실제 Worker의 매핑 여부는 Gateway 담당자가 확인해야 합니다. 최신 Gateway가 task_type을 Unity 요청에서도 허용하도록 변경됐다면 그 서버 명세에 맞춰 envelope를 조정해야 합니다.

서비스 응답에 run_id/unit_id가 없어도 Gateway는 저장된 작업의 request_id/job_id와 연결해 stream 이벤트에 원래 run_id 등을 붙여야 합니다.

테스트는 새 공정 실행을 만들므로 run_id를 새로 생성합니다. 실제 설비 연결에서는 원래 검사의 run_id를 끝까지 유지하고, 진단 request_id만 새로 생성해야 합니다.

결과 연결:
`ws://192.168.213.12:8000/api/v1/stream?run_id=<공정 실행 UUID>&after_sequence=<마지막 sequence>`

진단 후 Gateway가 후보를 저장하고 TCAD 작업을 관리합니다. Unity는 `tcad.verification.candidate_queued/running/succeeded/failed/cancelled`, `batch_completed`, `review_required` 이벤트를 수신합니다. 후보를 하나로 줄이지 않고 tcad_request_id별로 유지합니다. tcad_request_id 생성·TCAD HTTP 호출·상태 폴링·정책 판단은 Gateway 책임입니다. 이 테스트는 승인 요청이나 레시피 적용을 하지 않습니다.

## 확인한 계약과 아직 확인할 계약

- 요청 envelope는 프로젝트에 저장된 Gateway OpenAPI의 DiagnosisRequest와 기존 control의 type 규칙, 입력은 사용자가 전달한 서비스 계약을 사용했습니다. 현재 서버 배포를 실시간 조회한 결과는 아닙니다.
- 이벤트 테스트 fixture는 기존 stream envelope `{sequence,event_id,run_id,event_type,payload}`를 사용하고 후보 식별 필드를 payload에 둡니다. **첨부 설계는 이벤트의 전체 JSON 예시와 세부 중첩 구조를 정하지 않았습니다.** Gateway 담당자의 실제 이벤트 JSON과 대조해야 합니다. 구조가 다르면 오류를 표시하며 추측해 변환하지 않습니다.
- `succeeded` fixture는 result_payload에 4개 출력을 둡니다. 테스트 값은 통신 시험용이며 실제 모델 결과가 아닙니다.
- 진단 결과는 payload.response.result_payload.compensation.route에서 읽고 원형 응답을 유지합니다. `tcad_verify`는 후보 큐 경로이며, `apply`는 사용자가 전달한 서비스 계약상 tcad_proposal이 null일 수 있습니다. target_process_parameters를 잃지 않고 표시하되 자동 적용하지 않습니다. **첨부 Gateway 설계의 '모든 보정은 TCAD 검증 후 승인' 정책과 서비스의 apply 분기는 별도 조율이 필요합니다. Unity가 apply를 tcad_verify로 바꾸거나 후보를 임의 생성하지 않습니다.**

## 오프라인 테스트와 증거

`run-offline-tests.cmd` 실행. Unity 설치에 포함된 .NET과 프로젝트에 이미 있는 JSON 라이브러리를 사용하며 패키지를 추가하지 않습니다. 로컬 모의 Gateway는 `127.0.0.1:18765`만 사용합니다.

검사 항목: 요청 UUID·형식, 모델 입력 원형 보존, 후보 여러 개 유지, ID/상태 불일치 거절, 실패 null 보존, metadata 보존, batch/review/cancelled 처리, 중복 sequence, 다른 RUN 격리, 실제 WebSocket 인증 헤더, 한글 UTF-8을 쪼갠 분할 수신, 연결 중단 후 커서 재생, 진단 중복 전송 방지.

보고서: offline-result.txt. 실제 전송 시험 증거는 Runs/<request_id>/request.json, accepted.json, events.jsonl, cursor.json에 남습니다. 토큰은 기록하지 않습니다. 검사 데이터가 포함되므로 팀 내 시험 자료로 취급하세요.

**오프라인 통과는 Gateway DB 저장, ROS, Jetson 진단, 외부 TCAD 실행 성공을 증명하지 않습니다.** DB 원자성·후보 UUIDv5·동시 실행 1개·90분 작업 복구·승인 차단은 Gateway 서버 테스트에서 검증해야 합니다. 이 테스트는 기존 레거시 후보 surrogate 경로를 새 TCAD 검증으로 오인하지 않습니다.

## 실제 Gateway 단건 시험

Program의 `--live`는 Unity 창과 같은 C# WebSocket 전송·수신 코드를 실제 Gateway에 사용합니다. Unity Editor 내부에서 버튼을 누른 시험과는 구분합니다. 인증은 프로세스 환경변수 TCAD_TEST_UNITY_TOKEN으로만 받고 파일에 기록하지 않습니다. 팀원이 제공한 예시 입력으로 LOT-UNITY-INTEGRATION-TEST를 사용하며 실제 생산 측정으로 기록하지 않습니다.

LiveRuns/active.json에 ID를 먼저 기록하고 한 번만 전송합니다. 이 파일이 있으면 재실행해도 추가 요청을 만들지 않습니다. 접수 후 최대 210초 동안 진단을 관찰하고 진단 완료 시 추가 35초 동안 TCAD 이벤트를 관찰합니다. 관찰 종료는 서버 작업 취소가 아닙니다. 결과가 없으면 큐/ROS/Worker 상태 확인이 필요하며, TCAD 완료를 추정하지 않습니다.

`Check-LiveResult.ps1`은 같은 RUN의 DB 이벤트를 다시 조회하기만 합니다. 진단 요청을 새로 만들지 않습니다. accepted.json은 접수 증거이며, summary.json의 websocket_diagnosis_received와 same_event_replayed_from_db가 모두 true여야 진단 결과의 WebSocket 수신 및 DB 재생 확인입니다. status=succeeded와 결과 출처도 별도로 확인하세요.
