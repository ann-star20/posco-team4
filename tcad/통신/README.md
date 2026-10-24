# 모델 서비스 (Jetson Worker 연동, 계약 fab-ml-v1)

Jetson Worker 가 `POST http://127.0.0.1:8300/api/v1/predict` 로 요청하면 서로게이트(`../최종ML`)와 진단 에이전트(`../진단에이전트`)가 답한다. 표준 라이브러리만 쓴다 (NumPy 는 서로게이트가 필요로 함).

| 파일 | 역할 |
|---|---|
| `모델서비스.py` | HTTP 서버 (`POST /api/v1/predict`, `GET /health`), 재요청 캐시, 오류 처리, 선택 토큰 |
| `변환기.py` | 계약 JSON ↔ 서로게이트·에이전트 입출력. **단위, id 조건, 스펙 상수는 이 파일 맨 위에서만 정한다** |
| `시험.py` | 서버를 임시 포트로 띄워 39개 항목 확인 (`python 시험.py`) |
| `계약_보완.md` | 계약 문서와 실제 값이 다른 곳, 근거, 추가한 것, 소요 시간 |
| `예시/` | 실제 서비스가 돌려준 요청·응답 예 4개 (기준값, 영역 밖, 진단: 임계값 통과(apply), 진단: 임계값 못 채움(tcad_verify)) |
| `도구/` | Jetson 번들에 들어가는 시작·점검·Worker 대역·systemd 등록 스크립트 (설명은 `도구/README.md`) |
| `번들만들기.py` | **개발 PC 에서만**: Jetson 에 옮길 번들 `../Jetson배포/fabrx/` 와 `fabrx_jetson.tar.gz` 를 만든다 (모델이나 코드를 고친 뒤 다시 실행) |

폴더 배치: `최종ML/`, `진단에이전트/`, `통신/` 세 폴더가 같은 상위 폴더 아래 나란히 있어야 한다.
실행: `python 모델서비스.py` (127.0.0.1:8300 에서만 접속 가능). 토큰: `python 모델서비스.py --token 영문토큰` 또는 환경변수 `FAB_SERVICE_TOKEN`, 요청 헤더 `X-Fab-Token`. 진단 없이 surrogate 만: `--no-agent`.

## 작업 종류
- **surrogate**: 공정 변수(물리 단위) → vth, gm, id_on, bv 와 σ. 학습 영역 밖이면 `OUT_OF_DOMAIN`
- **diagnose**: 측정값(vth V, gm μS/μm, id_on μA/μm, bv V 또는 null) + `n_wafers` → 원인 확률, 구분 불가 판정, 다음 측정 권고, 보정안(변화량), `tcad_proposal`(TCAD 확인 후보, 물리 단위, 사람 승인 필요). `refine: true` 면 고정밀 확인까지(쓸 수 있을 때)

## 확인된 값과 근거 (TCAD 실행 기록과 deck 에서 직접 확인)
| 항목 | 값 | 근거 |
|---|---|---|
| id_on 조건 | Vgs 4.0 V, **Vds 0.1 V**, **26.85 °C (300 K)** | deck `solve vdrain=0.1`, `vfinal=4.0`, Atlas 로그 `Temperature = 300 K` |
| 길이 단위 | 산화막 **μm** (기준 0.06) | 로그 `Dimensions in microns`, `deposit oxide thick=0.06` |
| 전류 단위 | 폭 **1 μm 당** (gm μS/μm, id_on μA/μm) | 로그 `Jn(A/um)` |
| 기준값 | 도즈 7.7e12, 에피 1.7e16, 산화막 0.06 | `단계시험.py BASE`, 로그 `set DOSE = 7.7e+12` |

## 아직 확인이 필요한 것 (정직하게)
- **단위 확정**: 도즈 cm⁻², 에피 cm⁻³, 산화막 µm, gm µS/µm, id_on µA/µm. 근거: deck 에서 DOSE 는 `implant boron dose=`, 에피는 `init silicon c.phos=` 로 들어가고, Silvaco 자료("Process simulation - Silvaco" 13쪽 atom/cm³, 20쪽 atm/cm², 16쪽 µm)가 같은 단위를 쓴다. 이 PC 의 자료로 확인했고, 공식 매뉴얼 원문은 아니다
- **스펙(Vth 1.7~2.6 V, BV 40 V 이상)**: 기준 소자 AOI4184 데이터시트의 VGS(th) 최소·최대, BVDSS 최소와 같은 값 (응답 `spec.status: "datasheet_AOI4184"`). 데이터시트 Vth 는 ID=250 µA 정의라 TCAD 추출 방식과 같은지는 미확인
- **소자 폭**: 미정 (지금은 μm 당 값)
- **계약 문서의 예시 숫자**(1.2e13, 2.5e15, 5.2)는 기준값과 단위가 맞지 않아 영역 밖으로 거절된다 → 문서 수정 필요 (`계약_보완.md`)
- **Jetson 실측은 일부만**: 시험 중 진단 1건이 3.5 초(이 PC 2.7 초). 다른 조건과 고정밀 포함 시간은 미측정. diagnose 는 이 PC 에서 3~14 초이므로 Worker 제한 시간은 60 초 이상 권장
- **Jetson 에서 확인됨**: Python 3.10.12, NumPy 2.2.6 (aarch64, 6코어)에서 `시험.py` 39개 항목과 `worker_stub.py` 10개 항목 모두 통과. HTTP 응답은 surrogate 6 ms, 진단 3.8 초. 아직 안 해본 것: 실제 Worker 연동, systemd 등록의 완료, 고정밀 모드

## 안전 장치 (시험으로 확인)
- 127.0.0.1 에만 바인딩. Windows 에서 같은 포트에 서버 두 개가 동시에 붙는 문제를 막았다 (두 번째는 실패)
- 토큰은 바이트로 비교, 어떤 예외가 나도 연결을 끊지 않고 500 응답. NaN, 음수, 누락, 알 수 없는 필드 거부, 요청 1 MB 제한
- **POOR_FIT**: 가장 잘 맞는 후보의 χ² 가 관측 수의 4배를 넘으면 "학습하지 않은 유형의 이상일 수 있다"며 판정하지 않고 TCAD 요청도 내지 않는다. 정상 측정을 잘못 막는 비율은 교차검증으로 0.1 %(792건 중 1건), 명백히 맞지 않는 측정은 χ² 1534 로 걸러졌다
