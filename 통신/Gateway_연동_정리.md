# Gateway 연동 정리: 서버 확인·재기동, HTTP 명세, 호출 구조

대상: Gateway(WebSocket) 담당, 서버 운영 담당. 자세한 필드는 `계약_보완.md`, `운영_테스트_가이드.md`, `TCAD_서비스_연결명세.md`에 있고, 이 문서는 한곳에서 보는 요약이다.

표시: **[확인됨]** 실제로 실행해서 확인, **[표준 명령]** 일반 명령이라 처음 쓸 때 결과를 확인할 것.

---

## 1. 서버 두 개

| | 모델 서비스 (서로게이트 + 진단 에이전트) | TCAD 검증 서비스 |
|---|---|---|
| 어디서 | Jetson | TCAD 워크스테이션 (Silvaco가 설치된 PC) |
| 주소·포트 | `127.0.0.1:8300` (Jetson 안에서만 접속) | `0.0.0.0:8400` (Gateway가 다른 장치에서 접속) |
| 호출하는 쪽 | Jetson Worker | Gateway |
| 응답 속도 | 서로게이트 수 ms, 진단 수 초 | 접수 즉시, 결과는 약 20~30분 뒤 (조회) |
| 인증 | 선택 (`X-Fab-Token`), `/health`와 `/health/ready`는 토큰 없이 열림 | 선택 (`X-Fab-Token`), **`/health/ready`도 토큰 필요** |
| 코드 위치 | `통신/` (번들 `Jetson배포/fabrx/`) | `TCAD서비스/` |

---

## 2. 모델 서비스 (Jetson): 확인과 재기동

설치 폴더는 팀원 보고 기준 `/home/jetson/project/surrogate_ml/fabrx`다 (`ls`로 확인). 서비스 이름 `fabrx-model` (부팅 시 자동 시작 **[확인됨]**).

### 확인
```bash
sudo systemctl is-active fabrx-model                 # active 이면 동작 중
ss -ltnp | grep 8300                                 # 127.0.0.1:8300 LISTEN
curl -s http://127.0.0.1:8300/health/ready           # "status": "ready", surrogate_ready/diagnosis_ready true
```
### 재기동 **[표준 명령]**
```bash
sudo systemctl restart fabrx-model
until curl -s http://127.0.0.1:8300/health/ready | grep -q '"status": "ready"'; do sleep 2; done; echo ready     # 켠 직후 수 초 걸린다
sudo journalctl -u fabrx-model -n 50 --no-pager      # 안 뜨면 로그 확인
```
직접 켜서 보려면 먼저 `sudo systemctl stop fabrx-model` 후 `cd /home/jetson/project/surrogate_ml/fabrx && export LANG=C.UTF-8 LC_ALL=C.UTF-8 && python3 run_service.py`.

---

## 3. TCAD 서비스 (워크스테이션 PC): 확인과 재기동

### 확인 (어디서든 curl, 토큰을 쓰는 경우)
```bash
curl -s -H "X-Fab-Token: <토큰>" http://<TCAD PC 주소>:8400/health/ready
```
정상 응답 예: `"status": "ready"`, `"dbascii_found": true`, `"calc_mode": "real"`, `"queue": {"workers": 3, "queued": 0, "running": 0}`.

- `calc_mode`가 **`fake`면 가짜 계산**이다 (흐름만 시험하는 용도, 결과 값은 의미 없음). 운영에서는 반드시 `real`.
- `dbascii_found`가 false면 Silvaco 실행 파일을 못 찾은 것이다.
- 연결이 안 되면(응답 없음) 서버가 꺼져 있거나 방화벽이 8400을 막고 있다. 같은 PC에서 `curl http://127.0.0.1:8400/health/ready`가 되는데 다른 장치에서 안 되면 Windows 방화벽의 8400 인바운드 허용이 필요하다.

**[확인됨]** 지금(2026-10-22 기준) 이 PC에서는 8400 서비스가 꺼져 있다. 켜야 한다.

### 켜기 (PowerShell, PC에서)
```powershell
cd C:\Users\User\Downloads\TCAD_ML\TCAD서비스
$env:TCAD_CALC = "real"                    # 실제 TCAD. 빼면 가짜 계산
$env:TCAD_SERVICE_TOKEN = "<토큰>"         # --token 으로 주면 프로세스 목록에 토큰이 보이니 환경변수를 권장
$env:TCAD_WORKERS = "3"                    # 동시 계산 수 (라이선스·CPU에 맞춤)
python 서비스.py --port 8400
```
작업 목록은 `TCAD서비스\상태\작업목록.json`에 저장돼서 서비스를 껐다 켜도 이어진다 (재시작 때 `running`이던 작업의 처리는 명세 5-3 참고).

### 끄기·재기동 때 주의 **[확인됨: 이 PC에서 겪은 문제]**
서비스만 끄면 계산 중이던 `dbascii`/`atlas` 프로세스가 남아 라이선스와 작업 폴더를 잡을 수 있다. 끈 뒤 반드시 확인한다.
```powershell
Get-Process atlas*, dbascii* -ErrorAction SilentlyContinue      # 비어 있어야 한다
Get-Process atlas*, dbascii* -ErrorAction SilentlyContinue | Stop-Process -Force    # 남아 있으면 정리
```
### 이 서비스가 한 번 실제 계산으로 검증된 결과 **[확인됨]**
기준값(도즈 7.7e12, 에피 1.7e16, 산화막 0.06) 요청 → 실제 TCAD 결과 vth 2.25829 V, bv 41.117 V, gm 4.573 µS/µm, id_on 5.207 µA/µm. 배치에서 낸 기준값과 같다. 소요 시간은 IV 약 282초 + BV 약 946초, 합쳐 약 20분.

---

## 4. HTTP 명세 요약

### 4-1. 모델 서비스 (Jetson `127.0.0.1:8300`)

| 메서드·경로 | 용도 |
|---|---|
| `GET /health`, `GET /health/ready` | 상태, 준비 점검 |
| `POST /api/v1/predict` | `task_type`이 `surrogate` 또는 `diagnosis`/`diagnose` |
| `POST /api/v1/diagnose` | 진단 전용 (`task_type` 생략 가능) |

**서로게이트** 입력: `input_payload.process_parameters` {`body_dose` cm⁻², `epi_doping` cm⁻³, `oxide_thickness` µm}, `requested_outputs`. 출력: `result_payload` {`vth` V, `gm` µS/µm, `id_on` µA/µm, `bv` V}, `metadata.sigma`, `metadata.in_domain`.

**진단 에이전트** 입력: `task_type: "diagnosis"`(또는 `/api/v1/diagnose`), `input_payload.measurements` {`vth` V, `gm` µS/µm, `id_on` µA/µm, `bv` V 또는 null}, `n_wafers`, `refine`(false). 출력 핵심:

| 필드 | 의미 |
|---|---|
| `decision.top_category` | `normal`, `dose`, `epi`, `oxide`, `dose+epi`, `dose+oxide`, `epi+oxide`, `dose+epi+oxide` |
| `decision.top_probability`, `decision.decided` | 원인 확률, 판정 여부 |
| `knobs.*` | 공정 변수별 추정(`mean`, `ci90`, `mean_ratio`, `p_deviated`) |
| `next_measurement.recommendation_code` | `none_needed`, `no_improvement`, `measure_bv`, `more_wafers_2x`, `more_wafers_4x` |
| `compensation.route` | **`apply`, `tcad_verify`, `no_action`, `manual`** (분기 기준) |
| `compensation.target_process_parameters` | 보정 후 목표 공정값 (`apply`면 이것을 적용) |
| `compensation.high_confidence`, `confidence_blockers`, `thresholds` | 임계값 판정 정보 (임시 기준, `provisional`) |
| `tcad_proposal` | `tcad_verify`일 때만 값 (`candidates[i].process_parameters`, `predicted_outputs`), 나머지는 null |

공통: 모든 요청에 `schema_version: 1`, `model_contract_version: "fab-ml-v1"`, `request_id`(요청마다 새 UUID, 같으면 캐시 응답). 오류: `INVALID_INPUT`(400), `UNSUPPORTED_CONTRACT_VERSION`, `UNSUPPORTED_TASK_TYPE`, `OUT_OF_DOMAIN`(200, `status: failed`), `MODEL_NOT_READY`, `UNAUTHORIZED`, `INFERENCE_FAILED`. 모든 실패 응답에 최상위 `error_code`, `error_message`.

### 4-2. TCAD 검증 서비스 (PC `0.0.0.0:8400`)

| 메서드·경로 | 용도 | 응답 |
|---|---|---|
| `POST /api/v1/tcad/verify` | 검증 요청 접수 | 202 접수 / 200 같은 `request_id` 재요청 / 400·422·429·401 |
| `GET /api/v1/tcad/jobs/{request_id}` | 상태·결과 조회 | `queued`, `running`, `succeeded`, `failed`, `cancelled` |
| `POST /api/v1/tcad/jobs/{request_id}/cancel` | 취소 | 200 |
| `GET /health/ready` | 준비 점검 | 200 |

**요청에 보낼 수 있는 최상위 필드는 정해져 있다** (그 밖의 필드를 보내면 400 `INVALID_INPUT`):
`request_id`(필수), `job_id`, `run_id`, `lot_id`, `model_contract_version`, `source`, `process_parameters`(필수: `body_dose`, `epi_doping`, `oxide_thickness`만), `requested_outputs`, `predicted_outputs`, `options`.
→ Unity 패키지의 `candidate_after`, `inspection`, `diagnosis`, `tcad_setup` 같은 필드를 그대로 보내면 거절된다. Gateway가 위 필드로 변환해서 보내야 한다.

결과(`succeeded`): `result_payload` {`vth` V, `gm` µS/µm, `id_on` µA/µm, `bv` V}, `metadata`(소요 시간, 재시도, 경고), `prediction_error`(예측 − TCAD, `predicted_outputs`를 보냈을 때). **규격 판정은 Gateway가 한다** (Vth 1.7~2.6 V, BV 40 V 이상, gm·id_on은 판정 안 함). 실패: `error_code`(`OUT_OF_RANGE`는 접수 때 422, 계산 중 실패는 `TCAD_NO_CONVERGENCE`, `TCAD_TIMEOUT`, `TCAD_LICENSE_UNAVAILABLE`).

---

## 5. Gateway가 호출하는 것 (순서)

```
① Worker → 모델 서비스   POST /api/v1/predict 또는 /api/v1/diagnose
② 응답의 result_payload.compensation.route 로 분기 (임계값을 Gateway가 다시 비교하지 않는다)
     apply        → TCAD 호출 없음. compensation.target_process_parameters 를 관리자 승인 후 적용
     tcad_verify  → ③
     no_action    → 결과만 저장
     manual       → 관리자 검토 대기
③ Gateway → TCAD 서비스  POST /api/v1/tcad/verify   (tcad_proposal.candidates[i] 로 요청 생성)
④ Gateway → TCAD 서비스  GET  /api/v1/tcad/jobs/{request_id}   (30초~1분 간격 폴링)
⑤ succeeded 면 Gateway가 vth·bv 로 규격 판정 + prediction_error 저장 → 관리자 승인 → Unity
```
Gateway가 직접 부르는 것은 ③④(TCAD 서비스)와 필요하면 취소 `POST …/cancel`이다. ①은 Worker가 부른다.

---

## 6. 현재 Gateway 설계 구조 확인

```
Unity ─WebSocket─▶ Gateway ─ROS 2─▶ Jetson Worker ─HTTP─▶ 모델 서비스 (Jetson)
                      │
                      └─HTTP─▶ TCAD 서비스 (워크스테이션 PC)
```
**이 구조로 잡으면 된다.** 다음을 확인하고 정하면 된다.

| 확인·결정 사항 | 현재 상태 |
|---|---|
| 모델 서비스는 Worker만 접속 | 맞음. `127.0.0.1`이라 Gateway가 직접 부를 수 없다 |
| Worker가 진단 경로를 호출하는가 | Worker는 `/api/v1/predict`(서로게이트)까지 구현됐다고 했다. **진단(`task_type: diagnosis`) 호출과 `route`/`tcad_proposal` 전달을 Worker와 ROS 메시지에 추가해야 한다** |
| Gateway → TCAD 서비스 네트워크 | PC 주소, 포트 8400 방화벽 허용, 토큰이 필요하다. 지금 서비스가 꺼져 있다 |
| `apply` 처리 | 모델은 임계값 5개를 모두 통과하면 `apply`(TCAD 건너뜀)를 준다. **팀의 이전 합의(모든 보정은 TCAD 검증)와 충돌**하므로 Gateway가 `apply`에서 TCAD를 건너뛰는지 확정해야 한다. 모든 보정에 TCAD를 쓰려면 `변환기.py`의 `SKIP_TCAD_WHEN_HIGH_CONFIDENCE`를 False로 한다 |
| 관리자 승인 | 모델 응답의 `requires_human_approval`은 항상 true. `apply`도 승인은 필요하다 |
| 후보가 2개일 때 | `tcad_proposal.candidates`가 보통 2개. 둘 다 검증(시간 2배)할지, 첫 번째만 할지 정해야 한다 (요청 id는 후보마다 따로) |
| TCAD 결과가 규격 밖일 때 | 재진단을 요청할지, 관리자에게만 알릴지 정해야 한다 |
| 제한 시간 | TCAD 작업당 90분 이상, 폴링 30초~1분. 실측 약 20분 |
| 재시도 안전 | 두 서비스 모두 같은 `request_id`면 새로 계산하지 않고 이전 결과를 돌려준다. 새 요청은 새 `request_id` |
| 단일 장애점 | TCAD 서비스는 이 PC가 켜져 있고 서비스가 떠 있어야 한다. 누가 켜고 감시할지 정해야 한다 |

### 보안 주의
- TCAD 서비스는 외부에 열리므로 토큰을 반드시 쓰고 사내망으로 제한한다. 토큰을 `--token` 인자로 주면 프로세스 목록에 보이니 환경변수(`TCAD_SERVICE_TOKEN`)를 쓴다.
- 이미 프로세스 목록에 노출된 토큰은 바꾸는 편이 좋다.

---

## 7. 점검 체크리스트

| # | 확인 | 명령 |
|---|---|---|
| 1 | Jetson 모델 서비스 | `curl -s http://127.0.0.1:8300/health/ready` → ready |
| 2 | 서로게이트 | 기준값 요청 → vth 2.26, bv 41.1 |
| 3 | 진단 | 측정값 요청 → `route` 확인 (예: 산화막 +25 %는 `tcad_verify`) |
| 4 | TCAD 서비스 (PC) | `curl -H "X-Fab-Token: …" http://<PC>:8400/health/ready` → `calc_mode: real` |
| 5 | Gateway → TCAD 연결 | 다른 장치에서 4번이 되는지 (방화벽) |
| 6 | TCAD 흐름 | 기준값 요청 → `queued` → `running` → `succeeded`, vth 2.2583, bv 41.117 (실측 약 20분) |
| 7 | Worker → 진단 | Worker가 `/api/v1/diagnose`로 호출해 `route`를 ROS 응답으로 전달 |
| 8 | 끝에서 끝 | Unity 요청 → 진단 → (`tcad_verify`면) TCAD → 결과가 Unity에 표시 |
