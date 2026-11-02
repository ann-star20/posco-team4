# 현장 운영자 주간 리포트·질의응답 골든셋 설계

## 1. 의도와 배경

AOI, surrogate/diagnosis, TCAD, 공장 운영 이벤트가 Aiven PostgreSQL에 축적되고 있다. 현재 실행 흐름과 서비스 분기는 이미 애플리케이션 규칙으로 정해져 있으므로 LLM이 다음 서비스를 선택하거나 공정 제어를 수행하게 만들 필요가 없다.

이 프로젝트의 LLM은 현장 운영자가 지난 한 주의 상태를 빠르게 이해하도록 확정된 수치와 이벤트를 설명한다. 시스템은 근거에 따라 조치를 **권고**하지만 LOT 상태 변경, 설비 정지, 공정 보정은 자동 실행하지 않는다. TCAD 결과 검토와 공정 보정 승인은 공정 엔지니어의 기존 책임으로 유지한다.

## 2. 사용자와 성공 기준

### 주 사용자

- 현장 운영자: 이상 징후, 미처리 작업, 지연, 검사 품질 문제를 확인하고 재검사·LOT 보류·카메라 점검·설비 점검 요청·엔지니어 호출 여부를 판단한다.
- 공정 엔지니어: 용어 정의를 검수하며 TCAD 결과와 공정 보정 승인만 담당한다.

### 성공 기준

- 리포트의 모든 숫자는 SQL 집계 결과와 일치한다.
- 권고는 버전 관리되는 규칙 결과와 일치한다.
- 생성된 설명은 사용한 LOT, 기간, 이벤트 또는 집계 근거를 제시한다.
- LLM이 근거에 없는 원인, 수치, 조치를 만들지 않는다.
- 운영자용 출력에 공정 보정값이나 승인 결론을 노출하지 않는다.
- 골든셋 holdout에서 구조화 필드 정확도 100%, 근거 충실성 98% 이상을 목표로 한다.

## 3. 비목표와 금지 사항

- LLM이 AOI 판정, surrogate 판정, TCAD 규격 판정 또는 공정 승인 결과를 새로 계산하지 않는다.
- LLM이 서비스 호출 순서를 결정하거나 서비스를 직접 호출하지 않는다.
- LLM이 LOT 격리, 설비 정지, 승인, 보정 적용을 자동 실행하지 않는다.
- 긴 자유형 Chain-of-Thought를 저장하거나 학습 데이터로 사용하지 않는다.
- Aiven 운영 원문을 검증 없이 정답으로 간주하지 않는다. mock, 과거 버그, 불완전 이벤트를 구분한다.
- 첫 단계에서 Qwen을 파인튜닝하지 않는다.

## 4. 선택한 접근과 대안

### 선택: SQL·규칙 엔진 + 용어사전 RAG + Qwen 설명

1. SQL이 기간별 사실과 지표를 계산한다.
2. 결정적 규칙 엔진이 severity와 권고 조치를 만든다.
3. 용어사전 RAG가 현장 운영자용 정의와 금지된 오해를 제공한다.
4. Qwen은 위 구조화 입력을 읽어 요약·근거·권고를 자연어로 표현한다.
5. 출력 검증기가 숫자, 코드, 허용 조치, 근거 참조를 검사한다.

이 방식은 기존 안전 규칙을 유지하면서 설명 품질만 LLM에 맡기므로 감사와 회귀 평가가 쉽다.

### 대안 1: 모든 용어를 시스템 프롬프트에 포함

초기 용어가 적을 때는 간단하지만 프롬프트가 커지고 정의 변경 이력과 출처를 관리하기 어렵다. 작은 spike에는 사용할 수 있으나 운영 구조로 채택하지 않는다.

### 대안 2: Qwen SFT

말투와 용어 사용을 고정할 수 있지만 정의가 바뀔 때 재학습이 필요하고 사실 근거를 보장하지 못한다. RAG·프롬프트 평가에서 반복 실패가 충분히 수집된 뒤 별도 단계로 검토한다.

### 대안 3: LLM 에이전트가 서비스와 조치를 선택

현재 서비스 흐름이 이미 결정적이며 안전 경계와 중복된다. 이득보다 오작동 위험이 커서 제외한다.

## 5. 데이터 흐름

```text
Aiven read-only snapshot
  -> event normalization and provenance validation
  -> weekly SQL aggregates
  -> recommendation rules
  -> terminology retrieval
  -> structured report context
  -> Qwen generation
  -> deterministic output validator
  -> operator report + evidence links
```

실행 시 운영 DB를 직접 장시간 스캔하지 않는다. 읽기 전용 계정으로 필요한 기간과 컬럼만 추출해 실행 ID가 붙은 immutable snapshot을 만들고, 리포트와 골든셋은 해당 snapshot에서 생성한다.

## 6. 데이터 신뢰도와 포함 기준

각 원천 레코드에는 다음 provenance를 붙인다.

- source table/event type, primary ID, event ID, run ID
- occurred_at, received_at, report timezone(Asia/Seoul)
- result_origin(mock/prod), model version, artifact hash
- schema/contract version
- completeness and validation status

운영 리포트 기본 집계에는 `prod`와 계약 검증 통과 데이터만 포함한다. mock·simulation은 별도 시험 구간으로 표시하거나 제외한다. 동일 event ID 재전송은 한 건으로 계산한다. 결측·순서 단절·상태 버전 충돌은 숨기지 않고 데이터 품질 경고로 집계한다.

## 7. 주간 운영 리포트

### 기간

- 기본: 직전 월요일 00:00:00부터 일요일 23:59:59까지, Asia/Seoul.
- 생성 기본값: 다음 월요일 08:00. 스케줄은 설정값으로 둔다.
- 전주와 같은 요일·시간 구간을 비교한다.

### 섹션

1. **이번 주 요약**: 검사 수, 정상/불량/review, 미처리, 주요 경고 수.
2. **AOI 품질**: LOT별 검사 수, crash/bend, fail/review 비율, 재검사, 카메라/이미지 오류.
3. **공정 모델 상태**: surrogate succeeded/failed/OOD, diagnosis 원인 분포. 세부 보정값은 제외한다.
4. **TCAD·승인 상태**: queued/running/succeeded/failed, 엔지니어 승인 대기 건수와 경과시간만 표시한다.
5. **설비·흐름 상태**: down/blocked 시간, LOT waiting/processing/transferring 및 quality_hold 구간.
6. **권고 조치**: severity 순으로 대상, 근거, 권고, 운영자 결정 필요 여부를 표시한다.
7. **데이터 품질**: 누락 이벤트, mock 혼입, 상태 버전 단절, 집계 제외 건수.

모든 리포트는 사람이 읽는 Markdown/HTML과 기계 검증용 JSON을 함께 만든다.

## 8. 권고 규칙

### 결정적 출력 계약

권고 엔진은 자유문 대신 다음 action code 중 0개 이상을 배열로 반환한다.

- `reinspect_item`: 대상 제품·웨이퍼 재검사
- `review_quality_hold`: 운영자에게 LOT quality hold 검토 요청
- `check_camera`: 카메라·조명·이미지 입력 점검
- `request_equipment_check`: 설비 점검 요청
- `check_input`: 입력값·단위 확인
- `review_training_coverage`: 공정 엔지니어에게 학습 커버리지 검토 요청
- `escalate_process_engineer`: 공정 엔지니어 호출
- `monitor_only`: 정보 표시만 하고 즉시 조치 없음

여러 신호가 동시에 발생하면 하나를 버리지 않고 대상별 권고를 병합한다. 같은 action/target은 가장 높은 severity 한 건으로 합치고 모든 근거를 보존한다. severity 우선순위는 `critical > warning > info`다. `monitor_only`는 다른 조치가 없을 때만 사용한다. 규칙 엔진은 `action_code`, `target_type`, `target_id`, `severity`, `rule_id`, `rule_version`, `evidence`, `operator_decision_required=true`를 반환한다.

### 기존 서비스가 확정한 hard signal

| 관측 | 권고 |
|---|---|
| AOI `fail` | 대상 재검사 또는 보류 검토 |
| AOI `review`, 이미지 읽기 실패 | 재촬영·카메라·조명 확인 |
| 설비 `down`/`blocked` | 설비 점검 요청 |
| diagnosis `POOR_FIT`/`manual` | 공정 엔지니어 호출 |
| TCAD failed/cancelled 또는 승인 SLA 초과 | 공정 엔지니어 호출 |
| surrogate `OUT_OF_DOMAIN` | 아래 OOD 분류 규칙 적용 |

### OUT_OF_DOMAIN 분류

1. 단위·자리수·허용 형식 오류 가능성이 높으면 운영자에게 입력 확인을 권고한다.
2. 공정상 유효한 입력임이 확인되고 학습 경계를 조금 벗어나면 `coverage_gap_candidate`로 기록한다.
3. 같은 parameter/direction의 유효 OOD가 설정 기간에 반복되면 공정 엔지니어에게 TCAD 표본 추가와 재학습 검토를 권고한다.
4. 극단값은 학습 데이터에 자동 편입하지 않고 엔지니어 검토 대상으로 둔다.

### LOT quality hold 권고

고정 불량률을 임의로 정하지 않는다. 동일 제품·공정·검사조건의 최근 검증된 정상 LOT에서 baseline을 계산한다.

- 최소 표본 수를 충족하기 전에는 정보만 표시하고 격리 권고를 내지 않는다.
- warning은 baseline 상한 또는 통계적 경고선을 넘을 때 생성한다.
- quality_hold 권고는 더 높은 관리한계와 결함 집중/연속 조건을 함께 만족할 때 생성한다.
- `review`와 카메라 오류는 제품 결함률에서 제외하고 검사 품질 지표로 따로 계산한다.
- 정확한 최소 표본, lookback, 관리한계는 Aiven 분포를 분석한 뒤 버전 관리되는 정책 파일로 확정한다.

모든 규칙 결과에는 `rule_id`, `rule_version`, 입력값, 비교 기준, 결과, 생성 시각을 남긴다.

## 9. 용어사전과 RAG

용어 레코드는 다음 필드를 가진다.

```json
{
  "term_id": "surrogate.out_of_domain",
  "term": "OUT_OF_DOMAIN",
  "audience": "field_operator",
  "canonical_definition": "...",
  "plain_korean": "...",
  "what_it_does_not_mean": ["..."],
  "operator_checks": ["..."],
  "escalation_condition": "...",
  "target_role": "process_engineer",
  "related_terms": ["training_domain", "TCAD"],
  "source_refs": ["contract/version/path"],
  "reviewed_by": "...",
  "reviewed_at": "...",
  "version": 1
}
```

공정 엔지니어가 canonical definition, 오해 금지 문구, escalation condition을 검수한다. 운영자용 표현은 원뜻을 바꾸지 않는 범위에서 편집한다. 검색은 term ID, 별칭, error code, event field를 지원하고 답변에는 term version과 source를 남긴다.

## 10. 골든셋

### 레코드 구조

```json
{
  "case_id": "...",
  "task": "weekly_summary | recommendation_explanation | terminology_qa",
  "audience": "field_operator",
  "snapshot_id": "...",
  "input": {},
  "observable_evidence": {},
  "expected_judgement": {},
  "expected_action": {},
  "required_points": [],
  "forbidden_claims": [],
  "provenance": {},
  "review": {}
}
```

### 생성 방식

- 정답 코드·수치·조치는 SQL과 규칙 엔진에서 생성한다.
- 자연어 expected answer는 템플릿 초안을 만들고 현장 표현을 다듬는다.
- 용어 QA는 승인된 용어 레코드에서 생성한다.
- 실제 이벤트 기반 사례와 합성 경계 사례를 구분한다.
- 같은 LOT/run/event가 development와 holdout에 동시에 들어가지 않도록 group split한다.
- holdout은 고정하고 프롬프트 개발 중 열람·수정하지 않는다.

### 필수 케이스

- AOI pass/fail/review, crash/bend, 낮은 신뢰도, 이미지 실패
- 정상 LOT, 불량 급증, 표본 부족, 카메라 오류 집중
- surrogate 정상, 입력 오류성 OOD, 유효 coverage gap, 극단 OOD
- diagnosis normal, apply, tcad_verify, manual/POOR_FIT
- TCAD queued/running/succeeded/failed와 승인 지연
- 서비스 지연, 중복 이벤트, 누락·순서 단절, mock 혼입
- 용어 정의, 오해 반박, 운영자 확인 순서, escalation 조건

## 11. 평가

### 결정적 자동평가

- JSON schema 유효성
- judgement/action code 정확 일치
- 숫자 및 단위 정확성 또는 정해진 허용오차
- required points 포함과 forbidden claims 부재
- 인용한 event/LOT/source가 입력 evidence에 존재
- 승인되지 않은 자동 조치 표현 금지
- 공정 보정값·민감정보 노출 금지

### 전문가 평가

공정 엔지니어는 초기 용어사전 전체와 안전 관련 QA를 검수한다. 이후 신규·변경 용어와 자동평가 실패/저신뢰 사례를 우선 검수한다. 현장 운영자는 이해 가능성, 조치 가능성, 경보 피로도를 평가한다.

LLM judge는 문장 명료성 보조 점수에만 사용하고 사실·안전 합격 판정에는 사용하지 않는다.

### 출시 gate와 승인

- 구조화 필드 정확도는 case 단위 완전 일치로 계산하며 holdout 전체에서 100%여야 한다.
- 근거 충실성은 생성 문장의 검증 가능한 주장 단위로 계산하며 98% 이상이어야 한다.
- 안전 위반, 근거 없는 자동 조치, 공정 보정값 노출은 한 건이라도 있으면 출시하지 않는다.
- holdout은 주요 필수 케이스별 최소 20건을 목표로 하되 실제 희귀 이벤트가 부족하면 합성 경계 사례임을 표시한다.
- shadow 리포트를 최소 4주 운영해 운영자 오탐·불필요 경보 피드백을 수집한다.
- 제품 책임자가 기술 gate를 확인하고, 현장 운영자가 이해 가능성과 조치 가능성, 공정 엔지니어가 용어와 escalation 안전성을 승인한 뒤 정식 출시한다.

## 12. 질의응답과 월간 확장

주간 리포트가 안정된 뒤 동일 SQL view, snapshot, 규칙 결과를 질의응답 도구로 노출한다. 질문을 임의 SQL로 변환하지 않고 허용된 query template과 기간·LOT 파라미터만 사용한다. 답변은 리포트와 같은 evidence bundle과 용어사전을 사용한다.

월간 리포트는 검증된 주간 지표를 재집계해 반복 장애, 장기 불량 추세, 모델 coverage gap, 승인 병목을 보여준다. 주간과 월간 수치 정의는 같은 metric registry를 공유한다.

## 13. 전달 채널과 파일 보존

첫 출시는 이메일과 파일 저장을 함께 사용한다. 웹페이지는 RAG의 전제조건이 아니며 초기 범위에서 제외한다.

```text
reports/YYYY-Www/
  report.json
  report.md
  report.html
  evidence.jsonl
  generation.json
```

- 이메일 제목은 기간, 전체 severity, 주요 권고 수를 포함한다.
- 이메일 본문에는 요약과 상위 권고만 넣고 `report.html`을 첨부한다.
- JSON은 자동검증과 향후 UI/API 입력, Markdown은 검수·버전 비교, HTML은 운영자 열람에 사용한다.
- evidence에는 원문 전체 대신 필요한 ID, 집계값, provenance를 저장한다.
- 이메일 주소와 수신 그룹은 코드가 아닌 설정으로 관리한다.
- 추후 웹 화면을 만들면 같은 report JSON과 evidence API를 표시하므로 RAG 인덱스나 생성 파이프라인을 변경하지 않는다.

리포트와 generation audit은 기본 1년, 원시 snapshot은 기본 90일 보존을 제안한다. 실제 보존기간은 조직 보안·품질 정책으로 설정 가능하게 하고, 가명화 매핑은 별도 제한 저장소에서 관리한다.

## 14. 모델 실행 환경

### 필수 기준 환경: 중앙 노트북 또는 운영 PC

- Aiven 읽기, snapshot 생성, RAG, Qwen 추론, 이메일 발송을 중앙 환경에서 수행한다.
- GPU가 없어도 `llama.cpp` GGUF CPU 실행이 가능해야 한다.
- Qwen3 1.7B Q4와 4B Q4를 동일 골든셋으로 비교하고 품질 gate를 만족하는 가장 작은 모델을 선택한다.
- 주간 batch이므로 실시간 응답보다 정확성·재현성과 AOI 서비스 비간섭을 우선한다.

### 선택 환경: Jetson Orin 8GB

- 동일한 GGUF, prompt, glossary, golden set으로 호환성을 검증한다.
- 첫 후보는 Qwen3 1.7B Q4이며 non-thinking mode, 짧은 context, 검색 문서 3~5개를 사용한다.
- AOI와 같은 장비에서 실행할 경우 LLM 실행 전후 AOI P95 latency, 시스템 메모리, OOM을 측정한다.
- AOI 지연 gate를 넘거나 메모리 경합이 발생하면 Jetson 배포는 중단하고 중앙 환경만 운영한다.
- Jetson은 필수 출시 gate가 아니라 선택적 edge profile이다.

Qwen 공식 `llama.cpp` 경로를 우선 사용하고 로컬 OpenAI-compatible `llama-server`를 생성 서비스가 호출한다. 모델 다운로드와 해시는 manifest에 고정한다.

- Qwen llama.cpp 가이드: https://github.com/QwenLM/Qwen3/blob/main/docs/source/run_locally/llama.cpp.md
- Qwen3 모델 계열: https://github.com/QwenLM/Qwen3
- Jetson Orin Nano 8GB 메모리 사양: https://developer.nvidia.com/downloads/assets/embedded/secure/jetson/orin_nano/docs/jetson_orin_nano_devkit_carrier_board_specification_sp.pdf

## 15. Snapshot·지연 이벤트·지표 정의

- 주간 snapshot은 생성 후 immutable이며 같은 snapshot ID 재실행은 같은 결과를 내야 한다.
- cutoff 이후 도착한 전주 이벤트는 기존 리포트를 조용히 덮어쓰지 않는다.
- 지연 이벤트는 다음 리포트의 `late_arrival_adjustment`에 집계한다. 중대한 정정이 필요한 경우 새 report revision을 발행하고 기존 revision을 보존한다.
- metric registry는 지표 ID, 정의, grain, 분모·분자, 포함·제외 조건, source-of-truth, timezone, owner, version을 가진다.
- 기존 서비스 계약과 migration이 상태 의미의 source-of-truth다. 의미가 충돌하면 리포트 구현이 임의로 정하지 않고 해당 서비스 owner에게 확인한다.
- baseline cohort는 우선 제품, 공정 단계, 모델 artifact hash, 카메라/검사 설정으로 분리한다. 실제 컬럼 가용성을 조사한 뒤 공정 엔지니어가 cohort 정의를 승인한다.
- recipe, model, camera 설정이 바뀌면 이전 baseline을 자동 승계하지 않는다.

## 16. 보안·개인정보·감사

- 운영 DB는 읽기 전용 자격증명과 제한된 쿼리를 사용한다.
- snapshot에는 DB URL, 토큰, 비밀번호를 저장하지 않는다.
- 외부 배포 데이터는 UUID, LOT ID, 사용자 식별자를 가명화한다.
- 모델 입력·출력·검색 문서·프롬프트 버전·응답·validator 결과를 audit record로 남긴다.
- 원본 이미지의 골든셋 포함은 별도 접근 권한과 보존정책을 따른다.

## 17. 단계적 출시

1. Aiven 스키마·분포 읽기 전용 조사와 데이터 품질 보고서.
2. metric registry, weekly SQL, immutable snapshot.
3. 권고 규칙과 규칙 골든셋.
4. 공정 엔지니어 검수 용어사전과 terminology QA.
5. Qwen report prompt, RAG, output validator.
6. shadow 주간 리포트와 운영자·엔지니어 검수.
7. 기준 충족 후 정식 주간 리포트.
8. 동일 기반의 제한된 질의응답.
9. 월간 리포트 확장.

## 18. 빌더에게 남기는 결정

- 현재 저장소의 Python·PostgreSQL 패턴을 따른다.
- snapshot과 생성물의 구체적 디렉터리 구조, CLI 이름, Qwen serving 방식은 구현 계획에서 정한다.
- SQL view 이름과 인덱스는 실제 Aiven 스키마·쿼리 계획을 읽은 뒤 정한다.
- baseline 최소 표본과 관리한계는 실제 분포 분석 결과로 제안하고, 운영자·공정 엔지니어 승인 전에는 정보성 지표로만 표시한다.
