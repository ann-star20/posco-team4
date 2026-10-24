# 진단 라우팅 기준과 임계값 — 단계별 정리

- 기준일: 2026-10-23
- 목적: "TCAD 검증서버로 넘어가는 기준이 뭐냐", "임계값이 왜 여러 군데 있냐"는 팀 내 혼란을 해소하기 위해, 실제 운영 중인 코드를 전부 확인해 단계별로 정리한다.
- 출처: Jetson(`192.168.10.253`) `fabrx-model.service`(`systemctl status fabrx-model`로 기동 확인, `/home/jetson/project/surrogate_ml/fabrx/run_service.py`) 내부의 `진단에이전트/진단에이전트.py`, `통신/모델서비스.py`, `통신/변환기.py`. **이 서비스는 이 git 레포 밖(Jetson 로컬)에 있으며, Gateway 레포에는 소스가 없다** — 이 문서가 그 공백을 메운다.
- 결론 선요약: **"TCAD로 보낼지"를 결정하는 임계값과 "TCAD 실측 결과가 합격인지"를 판정하는 임계값은 완전히 다른 두 개이며, 같은 숫자(1.7~2.6V, 40V)가 세 군데서 서로 다른 목적으로 재사용되는 것이 혼란의 원인이다.**

---

## 1. 전체 단계와 input/output

```
노브값(공정변수) → [Surrogate] → 전기특성 예측 → [Diagnosis Agent] → 원인/라우팅 결정
   → (route=tcad_verify일 때만) 보정 후보 → [Gateway 큐잉] → [TCAD 실측]
   → [Gateway 규격판정] → [Unity 사람 승인]
```

| # | 단계 | 실행 위치 | Input | Output |
|---|---|---|---|---|
| 1 | Surrogate 예측 | Jetson `fabrx-model.service` (`/api/v1/predict`) | `process_parameters{body_dose,epi_doping,oxide_thickness}` | `vth,gm,id_on,bv` 예측값 + `anomaly_detected`(§3) |
| 2 | Diagnosis(원인추정+라우팅) | Jetson `fabrx-model.service` (`/api/v1/diagnose`) | `measurements{vth,gm,id_on,bv}` (보통 1단계 예측값을 그대로 투입) | `decision{top_category,top_probability,decided}` + `compensation{route,...}` + (route=tcad_verify면) `tcad_proposal.candidates[]` |
| 3 | TCAD 후보 큐잉 | Gateway (`tcad_queue.py`) | 2단계의 `tcad_proposal.candidates` 전체 | `tcad_verification_candidates` N행 생성, 필터링 없음 |
| 4 | TCAD 실측 | TCAD 워크스테이션(Silvaco) | 후보별 `process_parameters` | 실측 `vth,gm,id_on,bv` |
| 5 | 규격 판정 | Gateway (`evaluate_spec()`) | 실측 `vth,bv` + 2단계가 실어온 `spec` 스냅샷 | `spec_verdict{overall: in_spec/out_of_spec/bv_unconfirmed}` |
| 6 | Unity 승인 | 사람 | `spec_verdict` 포함 후보 목록 | 승인/거부 (강제 게이트 아님) |

---

## 2. 2단계(Diagnosis) — TCAD로 넘어가는 진짜 기준

`통신/변환기.py:175-181`, `route_compensation()`:

```python
def route_compensation(decision, knobs, comp, fit):
    """프로젝트 정책(Gateway 계약): 모델은 apply 를 내지 않는다.
    보정 후보가 있으면 tcad_verify, 정상이면 no_action, 판단 불가면 manual."""
    if fit["poor_fit"]:
        return "manual", ["POOR_FIT"]
    if decision["decided"] and decision["top_category"] == "normal":
        return "no_action", []
    return "tcad_verify", confidence_blockers(decision, knobs, comp)
```

**3분기만 존재한다. `apply`(모델 자동 보정)는 설계상 존재하지 않는다** — 어떤 보정이든 사람 승인을 거쳐야 한다는 Gateway 계약을 모델 쪽에서도 지키고 있다.

| route | 조건 | 의미 |
|---|---|---|
| `manual` | `fit["poor_fit"]` | 가장 잘 맞는 후보의 χ²가 `관측개수 × POOR_FIT_FACTOR(4.0)`을 넘음 — 측정값이 학습된 어떤 상태와도 맞지 않음(학습 안 된 새 유형의 이상일 가능성) |
| `no_action` | `decided==True` AND `top_category=="normal"` | 정상으로 확정 |
| `tcad_verify` | 그 외 전부 | **이상 원인이 확정된 경우뿐 아니라, "확신이 안 서는" 경우도 포함** |

`decided`(판정됨)의 정의 (`진단에이전트.py:99`, `DiagnosisAgent._summary`):
```
decided = (가장 유력한 범주의 베이지안 사후확률 ≥ tau) AND not poor_fit
```
- `tau = 0.70` — 8가지 노브 조합(정상/도즈/에피/.../3개 복합) 중 하나가 사후확률 70% 이상이어야 "확정"
- `delta = 0.05` — 노브 하나가 기준값 대비 ±5% 이상 벗어나야 "이 노브가 벗어났다"로 분류하는 기준 (사후확률 계산용 마스크)
- 둘 다 `진단에이전트.py:74`의 `DiagnosisAgent.__init__(step=0.025, delta=0.05, tau=0.70)` 기본값

**팀이 가장 많이 헷갈리는 지점**: "구분 불가"(확신 없음, `decided=False`)도 `manual`이 아니라 `tcad_verify`로 간다. `manual`은 오직 `poor_fit`(측정값이 아예 학습 범위 밖 패턴)일 때만 나온다.

### `high_confidence`는 현재 라우팅에 영향을 주지 않는다

`변환기.py:210`:
```python
comp["high_confidence"] = comp["route"] == "tcad_verify" and not blockers
# 기존 apply 판정 조건. 지금은 TCAD 를 건너뛰는 근거로 쓰지 않는다 (우선순위·근거 데이터용)
```
`confidence_blockers()`(`변환기.py:158-172`)가 체크하는 `AUTO` 임계값 — `p_cause≥0.90`, `p_epi_deviated≤0.05`, `p_vth/bv_in_spec_after≥0.99`, `max_change≤15%`, 보정 후 비율이 `0.70~1.30`(core) 범위 — 은 **과거 "자동 적용(apply)" 게이트의 잔재**다. `route`는 이미 그 이전에 결정이 끝나 있고, `high_confidence`/`confidence_blockers`는 응답에 참고 정보로 같이 실려갈 뿐 TCAD로 보낼지 여부를 바꾸지 않는다.

---

## 3. 규격값(1.7~2.6V, BV≥40V)이 쓰이는 세 군데 — 전부 다른 목적

출처는 단 한 곳, `변환기.py:20-21`:
```python
SPEC = {"vth": (1.7, 2.6), "bv_min": 40.0}
SPEC_STATUS = "datasheet_AOI4184"
```
AOI4184 데이터시트의 `VGS(th) 1.7~2.6V`, `BVDSS 최소 40V`와 동일 (파일 상단 주석에 TCAD 로그/deck 대조 근거 명시).

| 사용처 | 코드 | 역할 | 라우팅/승인에 영향? |
|---|---|---|---|
| Surrogate `anomaly_detected` | `변환기.py:122-123 is_anomaly()` — `violates_spec(vth,bv)` | 서로게이트 예측값이 규격 밖이면 `True` | **아니오** — 1단계 응답의 참고 플래그일 뿐, 2단계 라우팅 로직은 이 값을 안 본다 |
| Diagnosis `confidence_blockers` 내부 (`p_vth/bv_in_spec_after`) | `진단에이전트.py:198 compensate()`의 `spec(i)` | 보정 후보가 사후분포 샘플 기준 규격에 들 확률 | **아니오** — §2에서 설명했듯 `high_confidence`에만 반영, route는 이미 결정됨 |
| Gateway `evaluate_spec()` | `tcad_candidate_worker.py:17-25` | **TCAD 실측 결과**가 합/불인지 최종 판정 | **예** — 이게 유일하게 "결과가 규격에 드는가"를 실제로 결정하는 지점. `gm`/`id_on`은 판정 안 함(진단용) |

→ **"같은 숫자가 왜 세 군데 있냐"**: 라우팅(TCAD로 보낼지)과 최종 합/불 판정(TCAD 실측이 규격에 드는지)은 서로 다른 질문인데, 둘 다 같은 물리적 규격(AOI4184)을 참조하다 보니 숫자가 겹쳐 보일 뿐이다. **라우팅 결정에 실제로 쓰이는 임계값은 `tau=0.70`과 `poor_fit`(χ²>4×n) 두 개뿐이고, 1.7~2.6V/40V는 라우팅과 무관하다.**

---

## 4. 참고 임계값 전체 목록 (코드 원문 기준)

| 임계값 | 값 | 위치 | 역할 |
|---|---|---|---|
| `tau` | 0.70 | `진단에이전트.py:74` | 원인 확정 기준(사후확률) |
| `delta` | 0.05 | `진단에이전트.py:74` | 노브 "벗어남" 판정 기준(±5%) |
| `POOR_FIT_FACTOR` | 4.0 | `변환기.py:27` | `manual` 라우팅 기준(χ² > 4×관측수) — 코드 주석: "임시 기준" |
| `AUTO.p_cause` | 0.90 | `변환기.py:26` | `high_confidence` 산정용(라우팅 무관) |
| `AUTO.max_p_epi` | 0.05 | 〃 | 〃 |
| `AUTO.p_spec_after` | 0.99 | 〃 | 〃 |
| `AUTO.max_change` | 0.15 | 〃 | 〃 |
| `AUTO.core` | (0.70, 1.30) | 〃 | 〃 |
| `SPEC.vth` | (1.7, 2.6) V | `변환기.py:20` | 규격(§3) — AOI4184 |
| `SPEC.bv_min` | 40.0 V | 〃 | 규격(§3) — AOI4184 |
| Gateway `evaluate_spec` 오차허용 | ±1e-6 | `tcad_candidate_worker.py:14` | 부동소수점 비교 허용오차(물리적 의미 없음) |

`AUTO` 계열과 `POOR_FIT_FACTOR`는 코드 주석에 "임시 기준"/"에이전트 평가로 조정할 것"이라고 명시돼 있다 — 확정값이 아니라 추후 조정 대상이다.

---

## 5. 열린 질문 (코드만으로 확인 불가, 담당자 확인 필요)

- `변환기.py` 파일 상단 주석: "도즈 cm^-2, 에피 cm^-3: Athena 표준 단위... 공식 매뉴얼 문구는 확인하지 못했으니 TCAD 담당(주현)이 한 번 확인할 것." — 단위 자체는 아직 모델 작성자도 미확정 상태로 코드에 남겨둔 항목.
- `AUTO`/`POOR_FIT_FACTOR` 임계값들이 "임시 기준"이라고 코드에 명시돼 있어, 실제 운영 데이터로 재조정이 필요한지는 모델 담당자 판단이 필요하다.

---

## 6. 관련 문서

- `docs/architecture/current-system-architecture.md`
- `docs/architecture/interface-definition.md`
- `docs/architecture/erd.md` (5단계 규격판정의 DB 반영: `tcad_verification_candidates.spec_verdict`)
