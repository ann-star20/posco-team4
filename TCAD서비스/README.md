# TCAD 검증 서비스: 아키텍처 · HTTP API 명세 · 데이터 플로우

실시간 확인판 (2026-10-23). 기존 `통신/TCAD_서비스_연결명세.md`는 구현 전 초안이고
미합의 항목이 있었다 (8장). 이 문서는 실제로 떠 있는 서버·Gateway를 직접 호출해서
확인한 내용만 적은 확정판이다. 서비스 자체 코드는 `서비스.py`(HTTP) + `계산.py`(계산 어댑터).

---

## 1. 아키텍처

### 1-1. 전체 시스템에서의 위치

```
Unity ──WS /api/v1/control, /api/v1/stream──▶ Gateway (FastAPI, 192.168.11.237:8000)
                                                   │
                                   ROS2(DDS) ──────┤── HTTP(폴링, 사람 승인) ──┐
                                      │                                      │
                           /fab_gateway_bridge 노드                          │
                                      │                                      ▼
                     ┌────────────────┴────────────────┐          TCAD 검증 서비스
                     ▼                                  ▼          (이 PC, 서비스.py)
        /fab/surrogate_requests, /fab/diagnosis_requests   /fab/events (결과, ack)
                     │                                  ▲
                     ▼                                  │
     Jetson: fab_surrogate_worker / fab_diagnosis_worker │
                     │                                  │
                     ▼                                  │
     Jetson: 모델 서비스 (127.0.0.1:8300, surrogate+diagnosis) ──┘
```

- **Jetson** (`192.168.10.253`): 모델 서비스(`fabrx-model`, systemd, :8300) + ROS2 워커 2개
  (`fab_surrogate_worker`, `fab_diagnosis_worker`, `DIAGNOSIS_MODE=prod`). 응답 전체
  (`compensation.route`, `tcad_proposal` 포함)를 `/fab/events`로 그대로 발행한다.
- **Gateway** (`192.168.11.237:8000`): ROS 이벤트를 구독해 ack하고, `route == "tcad_verify"`면
  자동으로 `tcad_proposal_groups` + `tcad_verification_candidates`를 만들어 TCAD 서비스에
  순수 HTTP로 제출·폴링한다. Unity와는 REST + WS로 통신한다 (2장 참고).
- **TCAD 워크스테이션** (이 PC, `192.168.10.82`): `서비스.py`가 `0.0.0.0:<포트>`에서 요청을 받는다.
  Gateway가 직접 접속하는 유일한 지점.

### 1-2. 지금 실제 배치 상태 (확인됨)

| 포트 | 모드 | 상태 | 비고 |
|---|---|---|---|
| 8401 | **fake** (`TCAD_CALC` 미설정) | 가동 중 | Gateway가 현재 이 주소를 본다 (담당자 확인) |
| 8400 | real | **꺼짐** | 이전에 떠 있던 걸 작업 없음 확인하고 종료함. 필요시 `$env:TCAD_CALC="real"; python 서비스.py --port 8400` |

토큰: `X-Fab-Token: <토큰값>` (환경변수 `TCAD_SERVICE_TOKEN`으로 설정, 운영자에게 별도 전달받을 것 — 이 문서/git에는 실제 값을 적지 않는다).

### 1-3. 내부 구조 (`서비스.py`)

- `Service`: 요청 검증(`validate`, 영역은 `최종ML/2단_GP.py`의 `Domain`) → `JobStore`에 작업 기록 →
  `ThreadPoolExecutor(TCAD_WORKERS, 기본 3)`로 비동기 실행.
- `JobStore`: 작업 목록을 JSON 파일(기본 `상태/작업목록.json`, `TCAD_STATE_FILE`로 변경 가능)에
  저장해서 서비스 재시작에도 `queued`/`running`이 보존된다 (재시작 시 `running`은 `queued`로 되돌림).
- `계산.py.get_calc_fn()`: `TCAD_CALC` 환경변수를 **요청 실행마다** 다시 읽어서 `fake_calc` 또는
  `real_calc`를 고른다 — 단, 이미 켜져 있는 프로세스의 환경변수는 외부에서 바꿀 수 없으므로
  실질적으로 **모드는 기동 시점에 고정**된다 (바꾸려면 그 포트 프로세스를 재시작해야 함).
  - `fake_calc`: 입력을 쓰지 않는 고정값(vth≈2.258, bv≈41.12 등) + 0.3초 sleep. **흐름 시험용,
    값은 의미 없음.**
  - `real_calc`: `대량작업2/대량실행/대량실행.py`의 `process(row)`로 실제 Silvaco(`dbascii.exe`) 실행.
    IV 약 8분 + BV 약 20분 ≈ **총 20~30분/샘플**, 동시 작업 수만큼 라이선스 필요.

---

## 2. HTTP API 명세

### 2-1. TCAD 검증 서비스 (이 PC)

| 메서드·경로 | 용도 |
|---|---|
| `POST /api/v1/tcad/verify` | 검증 요청 접수 (202 신규 / 200 같은 request_id 재조회 / 400·422·429·401) |
| `GET /api/v1/tcad/jobs/{request_id}` | 상태·결과 조회 |
| `POST /api/v1/tcad/jobs/{request_id}/cancel` | 취소 (`queued`만 실제로 끊김, `running`은 real이면 못 끊음) |
| `GET /health/ready` | 준비 점검 — `calc_mode`(fake/real), `dbascii_found`, 큐 상태. **토큰 필요** (모델 서비스와 달리 예외 없음) |

요청 최상위 필드(그 외는 400): `request_id`(필수), `job_id`, `run_id`, `lot_id`,
`model_contract_version`, `source`, `process_parameters`(필수: `body_dose` cm⁻², `epi_doping` cm⁻³,
`oxide_thickness` µm만), `requested_outputs`, `predicted_outputs`, `options`.

응답 `result_payload`: `vth`(V), `gm`(µS/µm), `id_on`(µA/µm), `bv`(V, 1e-9 A/µm 기준).
**규격 판정은 이 서비스가 하지 않는다** — Gateway가 한다(2-2 참고).

오류 코드: `INVALID_INPUT`(400), `OUT_OF_RANGE`(422), `QUEUE_FULL`(429), `UNAUTHORIZED`(401),
`NOT_FOUND`(404), 작업 실패는 `TCAD_NO_CONVERGENCE` / `TCAD_TIMEOUT` / `TCAD_LICENSE_UNAVAILABLE` / `INTERNAL`.

상세 요청/응답 JSON 예시는 기존 `통신/TCAD_서비스_연결명세.md` 3~4장 그대로 유효함 (코드와 대조 확인됨).

### 2-2. Gateway (`http://192.168.11.237:8000`) — openapi.json으로 실측 확인

| 메서드·경로 | 용도 | 인증 |
|---|---|---|
| `GET /health/live` | 상태 확인 (`{"status":"ok"}`) | 없음 |
| `POST /api/v1/surrogate-jobs` / `/diagnosis-jobs` / `/inspection-jobs` | 작업 생성 | `x-unity-token` |
| `GET /api/v1/jobs/{job_id}`, `/api/v1/inspection-jobs/{job_id}` | 작업 조회 | `x-unity-token` |
| `GET /api/v1/events?run_id=&after_sequence=&limit=` | 이벤트 폴링(REST) | - |
| `WS /api/v1/control` | (추정) 작업 제출용 소켓 — 토큰 없이 접속 시 **403** (라우트 존재 확인됨) | `x-unity-token` |
| `WS /api/v1/stream?run_id=...` | 이벤트 실시간 수신 — **101 Switching Protocols 확인됨** | - |
| `GET /api/v1/tcad/proposals?status=review_required`(기본값) | 승인 대기 중인 TCAD 검증 결과 목록 | `x-unity-token` |
| `POST /api/v1/tcad/proposals/{proposal_id}/decision` | 승인/반려 (`decided_by`, `decision: approved\|rejected`, `selected_tcad_request_id`) | `x-unity-token` |
| `POST /api/v1/proposals/{proposal_id}/approval` | (TCAD 외) 일반 보정 승인 (`approved_by`, `effective_from_lot`) | `x-approval-token` |

토큰: `x-unity-token: <토큰값>` (운영자에게 별도 전달받을 것 — 이 문서/git에는 실제 값을 적지 않는다).

`GET /api/v1/tcad/proposals` 응답 구조 (실측):
```json
{"proposals": [{
  "proposal_id": "...", "job_id": "...", "run_id": "...",
  "status": "review_required", "created_at": "...",
  "candidates": [{
    "tcad_request_id": "...", "candidate_index": 0,
    "process_parameters": {"body_dose": ..., "epi_doping": ..., "oxide_thickness": ...},
    "result_payload": {"vth": ..., "gm": ..., "id_on": ..., "bv": ...},
    "spec_verdict": {"vth_pass": true, "bv_pass": true, "overall": "in_spec", "spec_source": "datasheet_AOI4184"}
  }, ...]
}]}
```
**판정 규칙**: 후보의 `spec_verdict.overall == "in_spec"`이면 정상. 프로포절은 후보 중 하나라도
`in_spec`이면 승인 가능(그 `tcad_request_id`를 `selected_tcad_request_id`로), 전부 아니면 반려.
(이 Gateway가 **후보 2개를 다 TCAD에 제출/검증**하는 것도 실측으로 확인됨 — 연결명세 8장의
미합의 3번 항목 해소.)

---

## 3. 데이터 플로우 (실측 확인 기준)

```
① Unity → Gateway: WS /api/v1/control 또는 POST /api/v1/diagnosis-jobs (x-unity-token)
② Gateway → ROS(DDS) /fab/diagnosis_requests → Jetson fab_diagnosis_worker
③ Jetson worker → 모델 서비스 POST /api/v1/diagnose (127.0.0.1:8300)
④ Jetson worker → ROS /fab/events (diagnosis.completed, 응답 전체 포함) → Gateway가 ack(/fab/event_acks)
⑤ Gateway: compensation.route 확인
     apply       → TCAD 호출 없음, 보정값 바로 관리자 승인 큐로
     tcad_verify → ⑥
     no_action / manual → 결과 저장 / 관리자 검토 대기
⑥ Gateway(자동) → TCAD서비스 POST /api/v1/tcad/verify (후보마다, 보통 2개 다)
⑦ Gateway → TCAD서비스 GET /api/v1/tcad/jobs/{request_id} 폴링 (fake: 초 단위, real: 20~30분)
⑧ succeeded → Gateway가 vth/bv로 spec_verdict 계산 → tcad_proposal_groups.status = review_required
⑨ Unity → Gateway GET /api/v1/tcad/proposals?status=review_required 로 후보 목록 조회
⑩ Unity(사람) → Gateway POST /api/v1/tcad/proposals/{id}/decision (approved/rejected)
⑪ Gateway → WS /api/v1/stream?run_id=... 로 전체 과정을 Unity에 실시간 중계 (④~⑩ 각 단계)
```

### 지금 상태 (fake 기준 실데이터로 ①~⑪ 전부 확인됨)
- Jetson: surrogate 48건, diagnosis 54건 처리·ack 완료.
- Gateway: `review_required` 프로포절 4건, 후보 2개씩 모두 fake 결과로 `in_spec` 판정됨.

### fake 전용 한계 — real 2차 검증이 필요한 이유
`fake_calc`는 입력 공정값을 쓰지 않고 항상 같은 값을 돌려준다. 그래서 위 플로우로는
**"배선이 도는지"만** 검증되고 **"이 보정값이 실제로 맞는지"는 검증되지 않는다.** 승인
직전에만 선택된 후보 1개를 real TCAD(8400)로 재제출해서 확인하는 방식을 제안 중
(아직 Gateway 코드에 반영 안 됨 — 지금은 운영자가 수동으로 8400에 재요청 후 그 결과를
근거로 ⑩ 승인/반려를 결정해야 함).

---

## 4. 아직 안 끝난 것 (연결명세 8장 대비 갱신)

| 항목 | 상태 |
|---|---|
| 주소·포트·인증 | **확인됨** (1-2, 2-1, 2-2) |
| 폴링 vs 콜백 | **확인됨: 폴링만** (`options.callback_url` 미구현) |
| 후보 2개 다 검증? | **확인됨: 둘 다** |
| 제한시간/큐 길이 | 기본값(`timeout_seconds` 5400, `queue_max` 50, `workers` 3) 그대로 사용 중, 변경 논의 없음 |
| 규격 밖일 때 재진단 여부 | **미확인** — `review_required`까지만 보임, 전부 out_of_spec인 프로포절을 아직 못 봄 |
| real 2차 검증 자동화 | **미구현** — 3장 참고, Gateway 코드 수정 필요 (그쪽 접근 권한 있는 사람 작업) |
