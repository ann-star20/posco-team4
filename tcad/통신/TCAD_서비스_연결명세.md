# TCAD 검증 서비스 연결 명세 (초안): HTTP 쪽과 WebSocket 쪽의 경계

목적: 진단 에이전트가 낸 보정 후보(`tcad_proposal`)를 TCAD로 다시 계산해 검증한다. 역할 분담은 이렇다.

| 담당 | 만들 것 |
|---|---|
| HTTP 담당 | TCAD 워크스테이션의 **검증 서비스** (요청 접수, 큐, 실행, 결과 조회) |
| WebSocket 담당 | Gateway: 모델 응답을 받아 TCAD 서비스에 요청하고, 진행 상황과 결과를 Unity에 WebSocket으로 전달 |

TCAD는 샘플 하나에 약 30분이 걸린다 (IV 약 8분 + BV 약 20분). 그래서 **요청을 접수하고 바로 응답한 뒤 나중에 결과를 가져가는 비동기 방식**으로 한다. 한 번의 HTTP 요청이 30분을 기다리게 하면 안 된다.

이 문서는 팀이 합의해야 할 초안이다. 확정되면 `계약_보완.md`에 옮긴다.

---

## 1. 전체 흐름

```
Unity ─WS─▶ Gateway ─▶ Worker ─HTTP─▶ 모델 서비스 (Jetson)
                         │
         응답의 compensation.route 가 tcad_verify 이고 tcad_proposal 이 있으면
                         │
Gateway ──① POST /api/v1/tcad/verify──────────────▶ TCAD 서비스 (워크스테이션)
        ◀─② 202 Accepted (접수, queued)──────────────┘
Gateway ─WS─▶ Unity   "TCAD 검증 대기/진행 중" 알림
Gateway ──③ GET /api/v1/tcad/jobs/{request_id} (주기적으로 조회)──▶
        ◀─④ status: queued → running(iv) → running(bv) → succeeded
Gateway: 결과로 규격 판정(Vth 1.7~2.6 V, BV 40 V 이상) + 예측값과 비교 → DB 저장
Gateway ─WS─▶ Unity   "TCAD 검증 완료: 규격 안/밖" → 관리자 승인 화면
```

- TCAD 서비스는 모델 서비스를 호출하지 않는다. Gateway만 둘 다 호출한다.
- 조회(③)는 **폴링**을 기본으로 한다 (30초~1분 간격). 완료 알림을 서버가 보내는 콜백은 선택 사항(5-4).

---

## 2. 엔드포인트

| 메서드·경로 | 용도 | 응답 |
|---|---|---|
| `POST /api/v1/tcad/verify` | 검증 요청 접수 | 202 (접수) / 200 (같은 `request_id` 재요청) / 4xx |
| `GET /api/v1/tcad/jobs/{request_id}` | 상태·결과 조회 | 200 |
| `POST /api/v1/tcad/jobs/{request_id}/cancel` | 대기·실행 중 작업 취소 | 200 |
| `GET /health/ready` | 준비 점검 (TCAD 실행 파일, 라이선스, 큐 상태) | 200 |

인증: 모델 서비스와 같게 선택적 헤더 `X-Fab-Token`. 문자 인코딩은 UTF-8 JSON.

---

## 3. 요청 `POST /api/v1/tcad/verify`

```json
{
  "request_id": "tcad-0001",
  "job_id": "job-2",
  "run_id": "run-1",
  "lot_id": "LOT-001",
  "model_contract_version": "fab-ml-v1",
  "source": {"candidate_name": "보정 후 (사후 평균 상태)", "high_confidence": false},
  "process_parameters": {"body_dose": 7.012e12, "epi_doping": 1.7e16, "oxide_thickness": 0.06375},
  "requested_outputs": ["vth", "gm", "id_on", "bv"],
  "predicted_outputs": {"vth": 2.229, "gm": 4.456, "id_on": 5.15, "bv": 41.81},
  "options": {"priority": "normal", "timeout_seconds": 5400}
}
```

| 필드 | 필수 | 설명 |
|---|---|---|
| `request_id` | 필수 | 요청 식별자. **같은 값이 다시 오면 새로 계산하지 않고 기존 작업을 돌려준다** (재시도 안전) |
| `job_id`, `run_id`, `lot_id` | 선택 | Gateway가 추적하는 값. 그대로 응답에 돌려준다 |
| `process_parameters` | 필수 | 모델의 `tcad_proposal.candidates[i].process_parameters`를 그대로. 단위: `body_dose` cm⁻², `epi_doping` cm⁻³, `oxide_thickness` µm. **공정 변수는 이 3개뿐** (확산 시간은 deck 고정값, `diffusion_time`은 받지 않는다) |
| `requested_outputs` | 선택 | 기본 4개. `bv`를 빼면 BV 계산(약 20분)을 생략해 시간이 약 8분으로 줄어든다 |
| `predicted_outputs` | 선택 | 모델이 예측한 값. 주면 결과에 예측 오차를 같이 계산해 준다 (모델 정확도 감시용) |
| `source.high_confidence` | 선택 | 모델의 `high_confidence`. 큐 우선순위 판단에 쓸 수 있다 |
| `options.priority` | 선택 | `normal` 또는 `high` |
| `options.timeout_seconds` | 선택 | 작업 하나의 제한 시간. 기본 5400 (90분) |

### 요청 검증 (거절 규칙)
접수할 때 바로 거절해야 TCAD 30분을 낭비하지 않는다. 범위 검사는 서로게이트의 영역 규칙과 같은 것을 쓴다 (`최종ML/2단_GP.py`의 `Domain`).

| 조건 | 응답 |
|---|---|
| 필드 누락, 음수, 숫자가 아님, 알 수 없는 필드 | 400 `INVALID_INPUT` |
| 기준값 대비 비율이 검증 범위 밖 (도즈 0.7~1.7, 에피 0.3~1.7, 산화막 0.5~1.4), 두 변수 이상이 ±30 % 밖, punch-through 구석(도즈 < 0.80 이고 에피 > 1.40) | 422 `OUT_OF_RANGE` |
| 큐가 가득 참 | 429 `QUEUE_FULL` |
| 토큰 불일치 | 401 `UNAUTHORIZED` |

---

## 4. 응답

### 4-1. 접수 응답 (202)
```json
{"request_id": "tcad-0001", "job_id": "job-2", "status": "queued",
 "queue_position": 2, "estimated_seconds": 5400, "accepted_at": "2026-10-21T14:00:00+09:00"}
```

### 4-2. 조회 응답 `GET /api/v1/tcad/jobs/{request_id}` (200)

진행 중:
```json
{"request_id": "tcad-0001", "job_id": "job-2", "status": "running",
 "progress": {"stage": "bv", "stages": [{"stage": "iv", "status": "succeeded", "seconds": 491}, {"stage": "bv", "status": "running", "seconds": 300}]},
 "started_at": "2026-10-21T14:20:00+09:00"}
```

성공:
```json
{"request_id": "tcad-0001", "job_id": "job-2", "status": "succeeded",
 "result_payload": {"vth": 2.231, "gm": 4.452, "id_on": 5.148, "bv": 41.79},
 "metadata": {
   "units": {"vth": "V", "gm": "uS/um", "id_on": "uA/um", "bv": "V"},
   "id_conditions": {"vgs_v": 4.0, "vds_v": 0.1, "temperature_c": 26.85},
   "bv_criterion": "1e-9 A/um",
   "leakage_a_per_um": 5.1e-16,
   "seconds_iv": 491, "seconds_bv": 1234, "attempts": 1,
   "mesh_factor": 1.0, "sweep_v": 4.0, "warnings": []},
 "prediction_error": {"vth": 0.002, "gm": -0.004, "id_on": -0.002, "bv": -0.02},
 "finished_at": "2026-10-21T14:41:00+09:00"}
```

실패:
```json
{"request_id": "tcad-0001", "job_id": "job-2", "status": "failed",
 "error_code": "TCAD_NO_CONVERGENCE", "error_message": "Vth 를 구하지 못했다 (재시도 2회 후)",
 "result_payload": null, "metadata": {"attempts": 3, "seconds_iv": 900}}
```

| `status` | 의미 |
|---|---|
| `queued` | 대기 중 |
| `running` | 실행 중 (`progress.stage`: `iv` 또는 `bv`) |
| `succeeded` | 완료 |
| `failed` | 실패 (`error_code` 참고) |
| `cancelled` | 취소됨 |

- `prediction_error`는 요청에 `predicted_outputs`가 있을 때만 있다. 값은 **예측 − TCAD** (같은 단위).
- **규격 판정(`in_spec`)은 TCAD 서비스가 하지 않는다.** 결과 `vth`와 `bv`로 Gateway가 한다 (Vth 1.7~2.6 V, BV 40 V 이상, gm·id_on은 판정 안 함). 서비스가 값을 해석하지 않아야 규격이 바뀌어도 서비스를 고칠 필요가 없다.
- BV 계산이 건너뛰어진 경우(`requested_outputs`에서 제외하거나, Vg=0 누설이 커서 소자가 꺼지지 않아 BV를 못 구한 경우)는 `result_payload.bv`가 `null`이고 `metadata.warnings`에 사유(`BV_SKIPPED`, `B4_LEAKAGE`)를 적는다.

### 4-3. 오류 코드

| 코드 | HTTP·상태 | 의미 |
|---|---|---|
| `INVALID_INPUT` | 400 | 요청 형식 오류 |
| `OUT_OF_RANGE` | 422 | TCAD 검증 범위 밖 공정값 |
| `QUEUE_FULL` | 429 | 대기열이 가득 참 |
| `UNAUTHORIZED` | 401 | 토큰 불일치 |
| `NOT_FOUND` | 404 | 모르는 `request_id` |
| `TCAD_NO_CONVERGENCE` | 작업 `failed` | 계산이 수렴하지 않음 |
| `TCAD_TIMEOUT` | 작업 `failed` | 제한 시간 초과 |
| `TCAD_LICENSE_UNAVAILABLE` | 작업 `failed` | Silvaco 라이선스를 못 얻음 |
| `INTERNAL` | 500 / 작업 `failed` | 예기치 못한 오류 |

---

## 5. 서비스 구현 시 알아둘 것 (HTTP 담당용)

### 5-1. 기존 실행 코드를 어떻게 쓰나
이미 돌아가는 코드가 있다 (`대량작업2/대량실행/대량실행.py`). 서비스는 이 코드를 감싸면 된다.

| 필요한 일 | 기존 코드 |
|---|---|
| 샘플 하나를 IV(→BV)까지 계산 | `process(row)` (결과를 `runs/<번호>/결과.json`으로 저장하고, 끊겨도 이어서 계산, 실패 재시도 규칙 포함) |
| 공정값 → 비율 | `비율 = 공정값 ÷ 기준값` (기준값: 도즈 7.7e12, 에피 1.7e16, 산화막 0.06) |
| 범위 검사 | `최종ML/2단_GP.py`의 `Domain` |
| 동시 실행 수 | 환경변수 `TCAD_WORKERS` (기본 3) |
| 제한 시간 | 환경변수 `TCAD_TIMEOUT` (기본 3600초, BV가 길면 5400) |
| 실행 파일 | `DBASCII` (기본 `C:\sedatools\lib\deckbuild\5.0.10.R\x86_64-windows\dbascii.exe`) |

`process(row)`는 계획표 한 줄(딕셔너리)을 받는다. 필요한 키: `번호`(작업 번호), `층`, `확장축`, `바디도즈비율`, `에피도핑비율`, `산화막비율`, `스윕(V)`(보통 4), `BV계산`(`Y` 또는 `N`).

### 5-2. 단위 변환 (결과 → 응답)
실행기는 SI(per µm) 단위로 저장한다. 응답은 모델 서비스와 같은 단위로 환산한다.

| 응답 필드 | 실행기 결과 (`결과.json`) | 환산 |
|---|---|---|
| `vth` (V) | `vth` | 그대로 |
| `gm` (µS/µm) | `gm` (S/µm) | × 1e6 |
| `id_on` (µA/µm) | `id4v` (A/µm) | × 1e6 |
| `bv` (V) | `bvt_levels["1e-09"]` | 그대로 (전류 1e-9 A/µm 기준) |
| `leakage_a_per_um` | `i_leak` | 그대로 |
| `seconds_iv` / `seconds_bv` | `seconds` / `bvt_seconds` | 그대로 |
| `attempts` | `len(시도)` | |

### 5-3. 상태와 큐
- 작업 상태는 파일(`runs/`)로도 남지만, 서비스가 재시작되면 `queued`/`running` 상태를 잃지 않도록 **작업 목록을 따로 저장**한다 (JSON 파일이나 SQLite 등). 재시작 후 `running`이던 작업은 `queued`로 되돌리거나 `failed`로 표시한다.
- 동시에 계산하는 수는 라이선스와 CPU로 제한한다 (현재 3개). 3개를 넘으면 큐에 쌓는다.
- 같은 `request_id`는 한 번만 계산한다 (결과가 있으면 그대로 돌려줌).

### 5-4. 폴링과 콜백
- 기본: Gateway가 `GET /jobs/{request_id}`를 30초~1분 간격으로 조회.
- 선택(나중): 요청에 `options.callback_url`을 받아, 완료 시 서비스가 그 주소로 4-2의 결과 JSON을 `POST`한다. 콜백이 실패해도 폴링으로 가져갈 수 있어야 한다.

### 5-5. 보안·네트워크
- 모델 서비스는 `127.0.0.1`에만 열려 있지만, TCAD 서비스는 **다른 장치(Gateway)가 접속**해야 하므로 외부에서 접근할 수 있는 주소·포트가 필요하다. 이때는 `X-Fab-Token`을 반드시 쓰고, 사내망에서만 열도록 방화벽을 설정한다.
- Silvaco 라이선스와 이 PC가 항상 켜져 있어야 한다.

---

## 6. WebSocket 담당(Gateway)이 알아둘 것

- 모델 응답에서 `compensation.route == "tcad_verify"` 이고 `tcad_proposal`이 있을 때만 TCAD 요청을 만든다. 후보가 여러 개면(`candidates`가 2개) 후보마다 `request_id`를 따로 만든다 (예: `<모델 request_id>-c0`, `-c1`).
- `no_action`이면 TCAD 요청을 만들지 않는다. `manual`이면 관리자 검토 대기.
- 결과 판정은 Gateway가 한다: `vth`가 1.7~2.6 V 안이고 `bv`가 40 V 이상이면 보정 성공. TCAD 결과와 `prediction_error`는 DB에 저장한다 (모델 정확도 추적).
- 제안하는 Unity 알림(WebSocket 이벤트) 상태: `tcad_queued`, `tcad_running`(stage iv/bv), `tcad_succeeded`(규격 안/밖 포함), `tcad_failed`(`error_code` 포함). 이름과 메시지 형식은 Gateway 담당이 정한다.
- 관리자 승인 전에는 공정값을 자동으로 바꾸지 않는다 (프로젝트 정책).
- TCAD 요청 제한 시간은 작업당 90분 이상. 폴링 간격은 30초~1분.

---

## 7. 시험 방법 (서비스를 만든 뒤)

1. `GET /health/ready` → ready.
2. 기준값(도즈 7.7e12, 에피 1.7e16, 산화막 0.06)으로 요청 → `queued` → `running(iv)` → `running(bv)` → `succeeded`. 결과가 기준값 `vth 2.2583`, `bv 41.117`과 같아야 한다 (기존 실행과 같은 값).
3. 같은 `request_id`로 다시 요청 → 새로 계산하지 않고 같은 작업 반환.
4. 범위 밖 요청(예: 도즈 3.2e13) → 422 `OUT_OF_RANGE`, 큐에 들어가지 않음.
5. 취소: 대기 중 작업 취소 → `cancelled`.
6. 서비스 재시작 중 작업이 있는 상태에서 재시작 → 작업 목록이 보존됨.
7. `requested_outputs`에서 `bv`를 빼고 요청 → 약 8분 안에 끝나고 `bv`가 `null`.
8. 모델 서비스 `tcad_proposal`의 실제 후보 하나를 그대로 요청 → 결과와 `prediction_error` 확인.

빠른 시험용으로 BV를 빼고(약 8분) 먼저 흐름만 확인하고, 마지막에 BV 포함 전체를 한 번 돌리는 것을 권한다.

---

## 8. 합의가 필요한 것
1. TCAD 서비스의 주소·포트와 인증 방식 (토큰 사용 여부).
2. 폴링만 쓸지, 콜백도 쓸지.
3. 후보가 둘일 때 둘 다 검증할지, 첫 번째만 할지 (시간이 2배).
4. 작업 하나의 제한 시간 (기본 90분)과 큐 최대 길이.
5. TCAD 결과가 규격 밖이면 Gateway가 모델에 재진단을 요청할지, 관리자에게만 알릴지.
