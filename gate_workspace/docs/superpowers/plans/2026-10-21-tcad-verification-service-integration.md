# TCAD Verification Service Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every valid diagnosis correction candidate, submit candidates to the external TCAD HTTP service with bounded concurrency, durably poll results, and replay progress to Unity.

**Architecture:** Diagnosis ingestion atomically creates one proposal group and deterministic candidate rows in Aiven PostgreSQL. A DB-backed worker claims candidates with leases, limits externally active jobs, calls the versioned TCAD HTTP contract, and emits events only on meaningful state changes. The existing legacy `verification_jobs` path remains available while the new diagnosis path uses dedicated tables.

**Tech Stack:** Python 3.10, FastAPI, Pydantic 2, httpx, psycopg 3, PostgreSQL 16, pytest, ROS 2 event ingestion, OpenAPI/AsyncAPI

**Spec:** `docs/superpowers/specs/2026-10-21-tcad-verification-service-integration-design.md`

## Global Constraints

- Persist all valid `tcad_proposal.candidates`; do not select only the first candidate.
- Default `TCAD_MAX_CONCURRENT_JOBS=1`; external `queued` and `running` both consume capacity.
- Generate `tcad_request_id` as UUIDv5 from `proposal_id` and `candidate_index`.
- Use `POST /api/v1/tcad/verify` and `GET /api/v1/tcad/jobs/{tcad_request_id}`.
- Send `X-Fab-Token` on POST and GET; never persist or log the token.
- Require `TCAD_API_TOKEN` in prod mode and allow it to be empty only in mock mode.
- Keep the Unity request, Gateway ML job, proposal group, and candidate TCAD identifiers distinct.
- Emit a committed ROS ACK only after diagnosis result and all candidate rows commit atomically.
- Require TCAD verification and human approval before correction; `high_confidence` never bypasses TCAD.
- Preserve legacy `verification_jobs` behavior while the diagnosis path migrates to candidate jobs.
- Do not invent `x_current`; this plan ends new candidate processing at `review_required` until the correction-command input contract supplies the current process values.

## Review Focus

- Replayed diagnosis result: same source event creates no duplicate group or candidates and returns the prior receipt.
- Duplicate external submit: HTTP 409 for the same `tcad_request_id` switches to polling without creating a second local job.
- Worker restart after HTTP 202 but before DB update: deterministic ID allows safe resubmission and recovery.
- Long-running candidate: HTTP transaction timeouts stay short while the job deadline is enforced independently.
- Invalid or missing process parameter: the entire diagnosis transaction is rejected before committed ACK, rather than queuing a partial batch.

---

## File Structure

### New files

- `database/migrations/010_create_tcad_candidate_queue.sql`: proposal-group and candidate queue schema.
- `services/event_gateway/src/event_gateway/tcad_contracts.py`: Pydantic request, acceptance, progress, terminal-result contracts.
- `services/event_gateway/src/event_gateway/tcad_queue.py`: deterministic IDs, diagnosis admission, DB claim and state transitions.
- `services/event_gateway/tests/unit/test_tcad_contracts.py`: contract and UUID tests.
- `services/event_gateway/tests/unit/test_tcad_candidate_migration_contract.py`: static migration invariants.
- `services/event_gateway/tests/integration/test_tcad_candidate_queue.py`: atomic admission, deduplication, claim and concurrency tests.
- `services/event_gateway/tests/integration/test_tcad_candidate_worker.py`: worker state-machine and recovery tests.
- `docs/runbooks/tcad-verification-service-e2e.md`: mock/prod startup, curl, DB and Unity verification procedure.

### Modified files

- `services/event_gateway/src/event_gateway/ml_contracts.py`: require candidate process parameters and non-empty candidate list.
- `services/event_gateway/src/event_gateway/config.py`: token, concurrency, transaction timeout, deadline and routing settings.
- `.env.example`: non-secret TCAD configuration examples.
- `services/event_gateway/src/event_gateway/diagnosis.py`: atomically admit all candidates after validated diagnosis.
- `services/event_gateway/src/event_gateway/tcad_client.py`: new authenticated request-id based contract while preserving the legacy adapter.
- `services/event_gateway/src/event_gateway/verification_worker.py`: process candidate queue first, then legacy queue.
- `services/event_gateway/src/mock_tcad/app.py`: implement the production-shaped async endpoints and keep legacy routes.
- `services/event_gateway/src/event_gateway/stream.py`: format candidate and batch events without exposing endpoint/token.
- `docs/api/openapi.yaml`: external TCAD contract and Gateway review-state schemas.
- `docs/api/asyncapi.yaml`: candidate and batch event payloads.
- `docs/database/integration-schema.md`: tables, states, indexes and ownership.
- `services/event_gateway/tests/unit/test_config.py`: prod token and numeric-bound validation.
- `services/event_gateway/tests/unit/test_tcad_client.py`: headers, paths and response validation.
- `services/event_gateway/tests/unit/test_mock_tcad.py`: new mock state progression and idempotency.
- `services/event_gateway/tests/integration/test_diagnosis_flow.py`: diagnosis-to-candidate atomic flow.
- `services/event_gateway/tests/integration/test_stream.py`: disconnection and cursor replay.

## Task 1: Lock the TCAD Candidate Contract and Configuration

**Files:**
- Create: `services/event_gateway/src/event_gateway/tcad_contracts.py`
- Create: `services/event_gateway/tests/unit/test_tcad_contracts.py`
- Modify: `services/event_gateway/src/event_gateway/ml_contracts.py`
- Modify: `services/event_gateway/src/event_gateway/config.py`
- Modify: `services/event_gateway/tests/unit/test_ml_contracts.py`
- Modify: `services/event_gateway/tests/unit/test_config.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `ProcessParameters`, `TcadVerificationRequest`, `TcadAcceptance`, `TcadJobStatus`, `make_tcad_request_id(proposal_id: UUID, candidate_index: int) -> UUID`.
- Produces settings: `tcad_api_token`, `tcad_auto_submit_enabled`, `tcad_max_concurrent_jobs`, `tcad_connect_timeout_seconds`, `tcad_request_timeout_seconds`, `tcad_job_deadline_seconds`, `tcad_policy_version`.

- [ ] **Step 1: Write failing contract tests**

Add tests proving exact units-bearing fields are finite and positive, requested outputs only allow `vth|gm|id_on|bv`, candidate lists are non-empty, missing `process_parameters` is rejected, UUIDv5 is stable, and acceptance/status only permit the five external states.

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `python -m pytest services/event_gateway/tests/unit/test_tcad_contracts.py services/event_gateway/tests/unit/test_ml_contracts.py -q`

Expected: FAIL because `tcad_contracts` and strict process-parameter validation do not exist.

- [ ] **Step 3: Implement the minimum contracts**

Use Pydantic `extra="allow"` for response metadata, but require all three process parameters and all four predicted outputs. Define terminal states as `succeeded|failed|cancelled`; local-only `pending|submitting|expired` remain outside the external response model.

- [ ] **Step 4: Write and run failing configuration tests**

Assert prod without `TCAD_API_TOKEN` fails, mock permits an empty token, booleans parse explicit true/false values, and concurrency/timeouts/deadline reject zero or negative values.

Run: `python -m pytest services/event_gateway/tests/unit/test_config.py -q`

Expected: FAIL on missing settings fields and validation.

- [ ] **Step 5: Implement settings and update `.env.example`**

Keep token fields `repr=False`. Do not place a real URL or token in `.env.example`.

- [ ] **Step 6: Verify GREEN**

Run: `python -m pytest services/event_gateway/tests/unit/test_tcad_contracts.py services/event_gateway/tests/unit/test_ml_contracts.py services/event_gateway/tests/unit/test_config.py -q`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add .env.example services/event_gateway/src/event_gateway/tcad_contracts.py services/event_gateway/src/event_gateway/ml_contracts.py services/event_gateway/src/event_gateway/config.py services/event_gateway/tests/unit/test_tcad_contracts.py services/event_gateway/tests/unit/test_ml_contracts.py services/event_gateway/tests/unit/test_config.py
git commit -m "feat: define TCAD candidate contracts"
```

## Task 2: Add the Durable Candidate Queue Schema

**Files:**
- Create: `database/migrations/010_create_tcad_candidate_queue.sql`
- Create: `services/event_gateway/tests/unit/test_tcad_candidate_migration_contract.py`
- Modify: `docs/database/integration-schema.md`

**Interfaces:**
- Produces tables: `tcad_proposal_groups`, `tcad_verification_candidates`.
- Produces uniqueness: `source_event_id`, (`proposal_id`, `candidate_index`), `tcad_request_id`.
- Produces due index covering `pending|submitting|queued|running` and `next_attempt_at`.

- [ ] **Step 1: Write the failing static migration test**

Assert both tables, all spec statuses, JSON object/array checks, lease-pair check, three unique keys, foreign keys, timestamps and partial due index are present.

- [ ] **Step 2: Run the test and confirm RED**

Run: `python -m pytest services/event_gateway/tests/unit/test_tcad_candidate_migration_contract.py -q`

Expected: FAIL because migration 010 is absent.

- [ ] **Step 3: Write migration 010**

Add group columns for routing snapshot, counts, status and selected candidate. Add candidate columns from the spec, with `deadline_at` required and token/credentials absent.

- [ ] **Step 4: Run migration tests and PostgreSQL integration bootstrap**

Run: `python -m pytest services/event_gateway/tests/unit/test_tcad_candidate_migration_contract.py services/event_gateway/tests/integration/test_events_migration.py -q`

Expected: PASS with `TEST_DATABASE_URL` configured.

- [ ] **Step 5: Document the schema ownership**

State that `diagnosis_results` owns the model response, the proposal group owns routing/batch state, and candidate rows own external TCAD lifecycle.

- [ ] **Step 6: Commit**

```bash
git add database/migrations/010_create_tcad_candidate_queue.sql services/event_gateway/tests/unit/test_tcad_candidate_migration_contract.py docs/database/integration-schema.md
git commit -m "feat: add durable TCAD candidate queue"
```

## Task 3: Atomically Admit Every Diagnosis Candidate

**Files:**
- Create: `services/event_gateway/src/event_gateway/tcad_queue.py`
- Create: `services/event_gateway/tests/integration/test_tcad_candidate_queue.py`
- Modify: `services/event_gateway/src/event_gateway/diagnosis.py`
- Modify: `services/event_gateway/tests/integration/test_diagnosis_flow.py`

**Interfaces:**
- Consumes: `make_tcad_request_id`, validated `DiagnosisModelResponse`, Task 2 tables.
- Produces: `admit_tcad_candidates(db, *, event, run_id, job_id, request_id, response, settings) -> UUID | None`.
- Produces: one `proposal_id` and one row per candidate in the same transaction as `diagnosis_results`.

- [ ] **Step 1: Write failing routing and atomicity tests**

Cover: two candidates create two rows; no-action/manual/failed/disabled create none; duplicate event creates none; invalid second candidate rolls back diagnosis and first candidate; proposal IDs and candidate IDs remain stable across retry.

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest services/event_gateway/tests/integration/test_tcad_candidate_queue.py services/event_gateway/tests/integration/test_diagnosis_flow.py -q`

Expected: FAIL because candidate admission is absent.

- [ ] **Step 3: Implement admission**

Derive `proposal_id` deterministically from the source event, preserve the routing evidence JSON, set candidate `deadline_at=now()+TCAD_JOB_DEADLINE_SECONDS`, and update `diagnosis_results.routing_status='verification_queued'` plus `proposal_id` only after all inserts succeed.

- [ ] **Step 4: Verify GREEN and legacy route behavior**

Run: `python -m pytest services/event_gateway/tests/integration/test_tcad_candidate_queue.py services/event_gateway/tests/integration/test_diagnosis_flow.py services/event_gateway/tests/integration/test_surrogate_flow.py -q`

Expected: PASS; legacy surrogate still uses `verification_jobs`.

- [ ] **Step 5: Commit**

```bash
git add services/event_gateway/src/event_gateway/tcad_queue.py services/event_gateway/src/event_gateway/diagnosis.py services/event_gateway/tests/integration/test_tcad_candidate_queue.py services/event_gateway/tests/integration/test_diagnosis_flow.py
git commit -m "feat: queue all diagnosis TCAD candidates"
```

## Task 4: Implement the Authenticated TCAD HTTP Client

**Files:**
- Modify: `services/event_gateway/src/event_gateway/tcad_client.py`
- Modify: `services/event_gateway/tests/unit/test_tcad_client.py`

**Interfaces:**
- Consumes: Task 1 request and response models.
- Produces: `TcadCandidateClient.submit(request: TcadVerificationRequest) -> TcadAcceptance`.
- Produces: `TcadCandidateClient.poll(tcad_request_id: UUID) -> TcadJobStatus`.
- Preserves: existing `TcadClient` legacy API.

- [ ] **Step 1: Write failing HTTP tests**

Assert exact POST/GET paths, `X-Fab-Token` on both calls, 202 requirement, matching request ID, five statuses, malformed terminal result rejection, metadata passthrough, and no token in `repr(client)` or raised validation messages.

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest services/event_gateway/tests/unit/test_tcad_client.py -q`

Expected: FAIL because the new client does not exist.

- [ ] **Step 3: Implement `TcadCandidateClient`**

Inject a configured `httpx.Client` and secret token. Treat HTTP status separately from TCAD job status. Return typed models; do not retry inside the client.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest services/event_gateway/tests/unit/test_tcad_client.py -q`

Expected: PASS, including existing legacy tests.

- [ ] **Step 5: Commit**

```bash
git add services/event_gateway/src/event_gateway/tcad_client.py services/event_gateway/tests/unit/test_tcad_client.py
git commit -m "feat: add authenticated TCAD verification client"
```

## Task 5: Make the Mock Service Production-Shaped

**Files:**
- Modify: `services/event_gateway/src/mock_tcad/app.py`
- Modify: `services/event_gateway/tests/unit/test_mock_tcad.py`
- Modify: `services/event_gateway/tests/integration/test_mock_http.py`

**Interfaces:**
- Consumes: Task 1 request contract.
- Produces: `POST /api/v1/tcad/verify`, `GET /api/v1/tcad/jobs/{request_id}`.
- Preserves: old `/api/v1/verifications` routes for legacy tests.

- [ ] **Step 1: Write failing mock contract tests**

Test token enforcement when configured, idempotent same-body POST, 409 changed-body POST, request-id keyed GET, queued→running→succeeded progression, and scenarios for failed/cancelled/malformed/timeout.

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest services/event_gateway/tests/unit/test_mock_tcad.py services/event_gateway/tests/integration/test_mock_http.py -q`

Expected: FAIL on missing new routes.

- [ ] **Step 3: Implement durable mock jobs**

Extend the SQLite fixture schema without deleting existing jobs. Store canonical body hash, poll count and full result. Generate deterministic result values from `predicted_outputs` and include units/timing metadata.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest services/event_gateway/tests/unit/test_mock_tcad.py services/event_gateway/tests/integration/test_mock_http.py -q`

Expected: PASS for new and legacy routes.

- [ ] **Step 5: Commit**

```bash
git add services/event_gateway/src/mock_tcad/app.py services/event_gateway/tests/unit/test_mock_tcad.py services/event_gateway/tests/integration/test_mock_http.py
git commit -m "feat: align mock TCAD with async contract"
```

## Task 6: Build the Recoverable Bounded-Concurrency Worker

**Files:**
- Modify: `services/event_gateway/src/event_gateway/tcad_queue.py`
- Modify: `services/event_gateway/src/event_gateway/verification_worker.py`
- Create: `services/event_gateway/tests/integration/test_tcad_candidate_worker.py`
- Modify: `services/event_gateway/tests/integration/test_verification_worker.py`

**Interfaces:**
- Consumes: Task 2 candidate rows, Task 4 client, settings from Task 1.
- Produces: `TcadCandidateWorker.run_once() -> int`.
- Produces queue operations: `claim_next_candidate`, `record_acceptance`, `record_progress`, `record_terminal`, `schedule_retry`, `expire_due_jobs`.

- [ ] **Step 1: Write failing worker state-machine tests**

Cover one active job blocking the next pending candidate, poll-before-submit priority, 202 recovery after restart, 409-to-poll recovery, 5xx/network retry, 4xx terminal failure, external failed/cancelled, local deadline expiry, lease contention and batch terminal aggregation.

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest services/event_gateway/tests/integration/test_tcad_candidate_worker.py -q`

Expected: FAIL because the worker and transitions are absent.

- [ ] **Step 3: Implement DB state transitions**

Use `FOR UPDATE SKIP LOCKED`, paired lease fields and state-checked updates. Count active external states in the same claim transaction. Poll `queued|running` before claiming a `pending` submit.

- [ ] **Step 4: Implement HTTP execution and retry policy**

Use separate connect/request timeouts. Retry network and 5xx with capped exponential backoff; make 400/401/403/422 and contract violations terminal. Do not create a new request ID after terminal failure.

- [ ] **Step 5: Emit state-change-only audit events**

Insert candidate events only when status/stage changes and one batch event when all candidates become terminal. Include correlation IDs and omit endpoint/token.

- [ ] **Step 6: Verify new and legacy workers**

Run: `python -m pytest services/event_gateway/tests/integration/test_tcad_candidate_worker.py services/event_gateway/tests/integration/test_verification_worker.py services/event_gateway/tests/integration/test_full_flow.py -q`

Expected: PASS; `VerificationWorker.run_once()` checks the new queue and falls back to legacy work.

- [ ] **Step 7: Commit**

```bash
git add services/event_gateway/src/event_gateway/tcad_queue.py services/event_gateway/src/event_gateway/verification_worker.py services/event_gateway/tests/integration/test_tcad_candidate_worker.py services/event_gateway/tests/integration/test_verification_worker.py
git commit -m "feat: process TCAD candidates with bounded concurrency"
```

## Task 7: Replay Candidate Progress Safely to Unity

**Files:**
- Modify: `services/event_gateway/src/event_gateway/stream.py`
- Modify: `services/event_gateway/tests/integration/test_stream.py`
- Modify: `docs/api/asyncapi.yaml`

**Interfaces:**
- Consumes: state-change events from Task 6 and existing run/sequence cursor.
- Produces: Unity payloads for candidate queued/running/terminal, batch completed and review required.

- [ ] **Step 1: Write failing stream tests**

Assert all correlation IDs and candidate index are present; terminal payload contains result or error; token and endpoint are absent; disconnect followed by `after_sequence` replays every missed transition once.

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest services/event_gateway/tests/integration/test_stream.py -q`

Expected: FAIL because candidate event formatting is unspecified.

- [ ] **Step 3: Implement formatters and AsyncAPI schemas**

Reuse the existing DB cursor stream. Do not create a direct TCAD-to-Unity socket and do not hold the original control request open.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest services/event_gateway/tests/integration/test_stream.py services/event_gateway/tests/unit/test_stream_contract.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add services/event_gateway/src/event_gateway/stream.py services/event_gateway/tests/integration/test_stream.py docs/api/asyncapi.yaml
git commit -m "feat: stream TCAD candidate progress to Unity"
```

## Task 8: Publish the Contract and End-to-End Runbook

**Files:**
- Modify: `docs/api/openapi.yaml`
- Create: `docs/runbooks/tcad-verification-service-e2e.md`
- Modify: `docs/architecture/jetson-ros2-tcad-unity-integration.md`
- Modify: `services/event_gateway/tests/unit/test_app_routes.py`

**Interfaces:**
- Produces: exact mock/prod environment setup, service order, health/submit/poll examples, ROS observations, DB queries and Unity cursor verification.

- [ ] **Step 1: Add failing documentation-contract assertions**

Assert OpenAPI contains the new external paths, `X-Fab-Token`, five states and candidate correlation fields. Assert the runbook contains mock and prod commands without real secrets.

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest services/event_gateway/tests/unit/test_app_routes.py -q`

Expected: FAIL until the contract docs are updated.

- [ ] **Step 3: Update OpenAPI, architecture and Korean runbook**

The runbook must show: migrations, mock TCAD start, Gateway/worker start, synthetic diagnosis request with two candidates, DB progress queries, stream replay, prod readiness, and failure diagnosis. State explicitly that the new flow stops at `review_required` until the command contract receives `x_current`.

- [ ] **Step 4: Run the focused and full Gateway suites**

Run: `python -m pytest services/event_gateway/tests/unit -q`

Run: `python -m pytest services/event_gateway/tests/integration -q`

Expected: PASS with `TEST_DATABASE_URL` configured; no existing AOI, surrogate, approval or legacy verification regression.

- [ ] **Step 5: Run repository hygiene checks**

Run: `git diff --check`

Run: `python -m compileall -q services/event_gateway/src`

Expected: exit code 0 for both.

- [ ] **Step 6: Commit**

```bash
git add docs/api/openapi.yaml docs/runbooks/tcad-verification-service-e2e.md docs/architecture/jetson-ros2-tcad-unity-integration.md services/event_gateway/tests/unit/test_app_routes.py
git commit -m "docs: add TCAD verification E2E guide"
```

## Final Acceptance

- [ ] Apply migration 010 to a disposable PostgreSQL schema and confirm all constraints/indexes.
- [ ] Start mock TCAD with token and submit a two-candidate diagnosis result.
- [ ] Confirm both candidates exist immediately while no more than one is externally `queued|running`.
- [ ] Restart the worker mid-job and confirm it resumes polling by the same `tcad_request_id`.
- [ ] Confirm candidate terminal results and one batch completion event in Aiven.
- [ ] Disconnect/reconnect the mock Unity client and confirm sequence-based replay.
- [ ] Confirm no token appears in PostgreSQL JSON, application logs or Unity payloads.
- [ ] Run the full Gateway test suite and capture pass count in the implementation handoff.
- [ ] Do not apply migration 010 to Aiven production until disposable-DB verification and user approval.
