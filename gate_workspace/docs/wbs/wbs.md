# WBS (Work Breakdown Structure)

- 기준일: 2026-10-23
- 출처: `git log --reverse`(전체 49 커밋, 2026-10-14~10-22) + 현재 작업트리의 미커밋 변경분(`git status`). 추정 일정이 아니라 **실제로 수행되고 커밋된 작업**을 역산해 단계로 재구성한 것이다. 향후 계획은 §4(미완료 항목)에 한정해 기술한다.

---

## 1. 전체 구조

```
0. Virtual Fab 통합 시스템
├── 1. 이벤트 파이프라인 기반 구축          (2026-10-14)
├── 2. 아키텍처 경계 정리                   (2026-10-16)
├── 3. Jetson 카메라/AOI 직접 검사 통합      (2026-10-20)
├── 4. Surrogate/Diagnosis ML + TCAD 후보 큐 (2026-10-21)
├── 5. TCAD 검증 안정화 및 서비스 연동       (2026-10-22)
└── 6. TCAD 승인 API + 산출물 문서화 (진행 중, 미커밋)  (2026-10-23)
```

---

## 2. WBS 상세

### 1. 이벤트 파이프라인 기반 구축 — 2026-10-14 (12 커밋)

| WP | 작업 | 근거 커밋 |
|---|---|---|
| 1.1 | ROS 2 이벤트 계약 정의(스키마 버전, event_id 멱등키) | `acdac68 feat: define durable fab event contract` |
| 1.2 | 가상 팹 ROS2-TCAD-Unity 모의 흐름 구현 | `f8eb946 feat(integration)` |
| 1.3 | Aiven 기반 ROS 이벤트 저장 검증 | `f21fdfc feat(integration)` |
| 1.4 | WSL ROS 브리지 정상 종료 처리 | `1337407 fix(ros)` |
| 1.5 | Gateway 패키지 editable 설치 경로 정리 | `ea81f33 build(gateway)` |
| 1.6 | 설계 문서화: Jetson TCAD 통합 흐름, mock/prod 통합 설계, Git 커밋 컨벤션, TDD 계획 | `636ea93`, `4f7af9d`, `1beaddb`, `e8eadd1`, `1bd87bb`, `13cad7c` (문서 6건) |

**완료 기준**: `events` 테이블 append-only 로그, ROS↔Aiven 왕복 검증됨. (→ `database/migrations/001_create_events.sql`, `002_create_integration_workflow.sql`에 대응)

### 2. 아키텍처 경계 정리 — 2026-10-16 (2 커밋)

| WP | 작업 | 근거 커밋 |
|---|---|---|
| 2.1 | TCAD/Unity 통합 경계 정의 문서화 | `cbe3c6f docs(architecture)` |
| 2.2 | mock 데이터와 실 전송 구분 명시 | `299f0b4 docs(architecture)` |

### 3. Jetson 카메라/AOI 직접 검사 통합 — 2026-10-20 (14 커밋)

| WP | 작업 | 근거 커밋 |
|---|---|---|
| 3.1 | 인증된 IP 카메라 소스 추가 | `6d61090 feat` |
| 3.2 | 유한 크기 프레임 링버퍼 추가 | `4dc08ed feat` |
| 3.3 | Unity에 카메라 미리보기 스트리밍(제한된 프레임레이트) | `afed64e feat`, `95819ea perf` |
| 3.4 | 프레임별 Unity AOI 요청 큐잉 + 비동기 디스패처 | `f939b6c feat`, `6c1bf95 feat` |
| 3.5 | 직접 카메라 AOI 클라이언트 실행 지원 + 최신 프레임 정확 조회 | `3c386e5 fix`, `07e7ea1 fix` |
| 3.6 | AOI/Surrogate 워커 실행 분리(성능) | `ddb1aa2 perf` |
| 3.7 | 통합 런타임 완성 | `14011e9 feat: complete virtual fab integration runtime` |
| 3.8 | 문서화: 카메라 프리뷰/링버퍼 설계, TDD 계획, 런북, WS 런타임 의존성 | `679ae1e`, `9112aba`, `b6f8e3d`, `ef45bf9` (문서 4건) |
| 3.9 | 코드 스타일 정리(파일 개행 정규화) | `54dc364 style` |

**완료 기준**: `/camera/preview`, `/aoi` WebSocket 채널 동작(→ `interface-definition.md` §3.1~3.2). `aoi_image_artifacts`, `aoi_inference_metrics` 테이블 도입(→ `004`, `007` 마이그레이션).

### 4. Surrogate/Diagnosis ML + TCAD 후보 큐 — 2026-10-21 (16 커밋)

| WP | 작업 | 근거 커밋 |
|---|---|---|
| 4.1 | Surrogate 진단 서비스 통합 + 계획/설계 문서 | `0786817 feat`, `4ead993 docs`, `2b783f4 docs` |
| 4.2 | ML v1 응답 계약 강제, 진단 접수/디스패치 테스트 | `cf29248 fix`, `97db3ee test` |
| 4.3 | AOI 추론 관측성(메트릭) 영속화 | `e5ead1c feat` |
| 4.4 | ROS 스택 기동 자동화 | `2d39cc2 chore` |
| 4.5 | 큐잉형 TCAD 검증 통합 설계/계획 문서 | `a9d417f docs`, `1da5f03 docs` |
| 4.6 | TCAD 후보 계약 정의 + request-id keyed 내구성 큐 추가 | `05d7b13 feat`, `68804a0 feat` |
| 4.7 | 진단의 모든 TCAD 후보 큐잉 | `a2a2fa2 feat` |
| 4.8 | 인증된 TCAD 검증 클라이언트(`X-Fab-Token`) 추가 | `11fa9c8 feat` |
| 4.9 | mock TCAD를 비동기 계약에 맞춰 정렬 | `2a4ab8d feat` |
| 4.10 | 유한 동시성으로 TCAD 후보 처리(워커 claim 로직) | `9b275ae feat` |
| 4.11 | TCAD 후보 진행상황을 Unity에 스트리밍 | `d16ddbe feat` |
| 4.12 | 통합 아키텍처/ML 가이드 갱신 | `3385364 docs` |

**완료 기준**: `tcad_proposal_groups`/`tcad_verification_candidates` 테이블 도입(→ `010` 마이그레이션), `verification-worker` 프로세스로 폴링 동작.

### 5. TCAD 검증 안정화 및 서비스 연동 — 2026-10-22 (3 커밋)

| WP | 작업 | 근거 커밋 |
|---|---|---|
| 5.1 | TCAD 후보 처리 재시작 안전성 확보(lease 복구) | `7cac46d fix: make TCAD candidate processing restart safe` |
| 5.2 | TCAD 검증 E2E 가이드 문서화 | `46a8eb4 docs` |
| 5.3 | TCAD 서비스 실연동(`cc69060 Tcad svc 연동`) | `cc69060` |

### 6. TCAD 승인 API + 산출물 문서화 — 2026-10-23, 이번 세션 (미커밋)

| WP | 작업 | 상태 |
|---|---|---|
| 6.1 | 규격 판정 로직(`evaluate_spec`) + `spec_verdict` 컬럼 | 완료 — `tcad_candidate_worker.py`, `database/migrations/011_tcad_spec_verdict.sql` (미커밋) |
| 6.2 | Unity용 TCAD 후보 승인 API(`GET/POST /api/v1/tcad/proposals(/decision)`) | 완료 — `app.py` (미커밋) |
| 6.3 | 시스템 아키텍처 문서 갱신(신규 승인 경로 반영) | 완료 — `current-system-architecture.md`, `.dot` (미커밋) |
| 6.4 | 요구사항 정의서 신규 작성 | 완료 — `docs/requirements/requirements-definition.md` (미커밋, 신규 디렉터리) |
| 6.5 | 인터페이스 정의서 신규 작성 | 완료 — `docs/architecture/interface-definition.md` (미커밋) |
| 6.6 | ERD 신규 작성 | 완료 — `docs/architecture/erd.md` (미커밋) |
| 6.7 | WBS 작성(본 문서) | 완료 — `docs/wbs/wbs.md` |
| 6.8 | TCAD 운영 조치: 특정 `tcad_request_id` 2건만 진행, 나머지 취소 | 완료 — DB 상태 변경(코드 변경 없음) |
| 6.9 | `verification-worker` 크래시 버그 발견/수정/재기동 | 완료 — `PredictedOutputs.get()` → attribute 접근 수정 |

---

## 3. 테스트/품질 보증 작업 (커밋 전반에 걸쳐 분산, 별도 집계)

| 유형 | 비고 |
|---|---|
| `test: cover diagnosis admission and dispatch` (97db3ee) | 명시적으로 `test:` 태그가 붙은 유일한 커밋 — 나머지 테스트는 `feat`/`fix` 커밋에 동반 포함된 것으로 추정(개별 집계 안 됨) |
| `services/event_gateway/tests/integration/*` | `test_tcad_candidate_worker.py`, `test_verification_worker.py`, `test_full_flow.py` 등 존재 — 이번 세션에서 직접 실행/검증하지 않음 (별도 과제, §4) |

---

## 4. 미완료/후속 과제

| 항목 | 내용 | 비고 |
|---|---|---|
| 두 보정 경로 통합 여부 결정 | `correction_proposals` 경로와 `tcad_proposal_groups` 경로를 하나로 합칠지, 공존시킬지 — 제품 결정 필요 | `erd.md` §3, `requirements-definition.md` §8에서도 플래그 |
| OpenAPI/AsyncAPI 갱신 | `/api/v1/diagnosis-jobs`, `GET/POST /api/v1/tcad/proposals(/decision)`를 계약 문서에 반영 | `interface-definition.md` §5 |
| `rejected` 결정 경로 E2E 검증 | TCAD 후보 거부 시나리오가 아직 테스트로 검증 안 됨 | `requirements-definition.md` §8 |
| orphaned `tcad_proposal_groups` 5건 정리 | 후보는 전부 `cancelled`인데 그룹 `status`가 `queued`에 멈춰있는 과거 데이터 5건 | 이번 세션에서 발견, 의도적으로 보류 |
| 6단계(본 세션) 변경분 커밋 | §2.6의 모든 WP가 작업트리에 미커밋 상태 | 사용자 확인 후 커밋 필요 |
| `.pytest-*` 임시 디렉터리 정리 | 세션 중 생성된 pytest 스크래치 디렉터리 16개가 작업트리에 잔존 | 실제 변경사항 아님, 커밋 전 정리 필요 |

---

## 5. 관련 문서

- `docs/requirements/requirements-definition.md`
- `docs/architecture/current-system-architecture.md`
- `docs/architecture/interface-definition.md`
- `docs/architecture/erd.md`
