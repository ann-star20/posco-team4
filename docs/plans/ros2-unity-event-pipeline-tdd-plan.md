# Durable ROS 2-to-Unity Event Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a loss-resistant vertical slice that accepts Jetson ROS 2 events, commits them once to PostgreSQL, and delivers or replays them to Unity.

**Architecture:** A Jetson ROS 2 bridge first records each event in a local SQLite outbox and then posts it to a FastAPI gateway. The gateway commits the event idempotently to PostgreSQL before notifying Unity through WebSocket; Unity recovers missed notifications through a sequence-based HTTP API.

**Tech Stack:** Python 3.10, ROS 2 Humble (`rclpy`), FastAPI, Pydantic 2, psycopg 3, SQLite, pytest, PostgreSQL 16, Docker Compose, Unity 2022.3 LTS, C#, NUnit

**Spec:** `docs/architecture/ros2-unity-event-pipeline.md`

## Global Constraints

- PostgreSQL is the only permanent system of record.
- ROS 2 is used only inside the Jetson boundary.
- MQTT and a separate message broker are excluded.
- An HTTP success response means the event transaction has committed to PostgreSQL.
- Every retry preserves the original `event_id`.
- PostgreSQL stores timestamps in UTC; Unity displays them in Asia/Seoul.
- Unity and Jetson never receive PostgreSQL credentials or direct database access.
- Tests must run without TCAD, external networks, or physical fab equipment.

## Review Focus

- A valid duplicate `event_id` with different content must return `409 Conflict`, not silently retain ambiguous data; covered in Task 2.
- A client-supplied or malformed `sequence` must be ignored because the server owns sequence allocation; covered in Task 2.
- A commit that succeeds while the HTTP response is lost must be safe to retry; covered in Task 3.
- Unity must close the replay/live race without losing an event committed during catch-up; covered in Task 5.
- A malformed ROS 2 JSON message must be rejected without crashing the subscriber or entering the outbox; covered in Task 4.

---

## Planned File Structure

```text
database/
  migrations/001_create_events.sql       # Durable event table and indexes
services/event_gateway/
  pyproject.toml                          # Gateway package and test dependencies
  src/event_gateway/config.py             # Environment configuration
  src/event_gateway/contracts.py          # Shared HTTP event models
  src/event_gateway/repository.py         # PostgreSQL event operations
  src/event_gateway/app.py                # FastAPI routes and application lifecycle
  src/event_gateway/stream.py             # WebSocket connection and ordered broadcast
  tests/                                  # Gateway unit and integration tests
jetson_ws/src/fab_event_bridge/
  package.xml, setup.py, setup.cfg         # ROS 2 Python package metadata
  fab_event_bridge/contracts.py           # Jetson-side event validation
  fab_event_bridge/outbox.py               # SQLite transactional outbox
  fab_event_bridge/sender.py               # HTTP retry worker
  fab_event_bridge/node.py                 # rclpy topic adapter
  test/                                    # ROS-independent unit tests
unity/Assets/FabEvents/
  Runtime/EventEnvelope.cs                 # JSON contract
  Runtime/EventCursor.cs                   # Last applied sequence state
  Runtime/EventApiClient.cs                # HTTP replay and WebSocket transport
  Runtime/EventStreamCoordinator.cs        # Replay/live ordering
  Tests/EditMode/                          # NUnit contract and ordering tests
tests/e2e/                                 # Docker-based failure recovery tests
docker-compose.yml                         # PostgreSQL and gateway development stack
```

### Task 1: Event Contract and PostgreSQL Migration

**Files:**
- Create: `services/event_gateway/pyproject.toml`
- Create: `services/event_gateway/src/event_gateway/__init__.py`
- Create: `services/event_gateway/src/event_gateway/contracts.py`
- Create: `services/event_gateway/tests/unit/test_contracts.py`
- Create: `database/migrations/001_create_events.sql`
- Create: `services/event_gateway/tests/integration/test_events_migration.py`
- Create: `docker-compose.yml`

**Interfaces:**
- Produces: `EventCreate`, `StoredEvent`, `Severity` in `event_gateway.contracts`
- Produces: PostgreSQL `events(sequence, event_id, schema_version, event_type, source, severity, correlation_id, causation_id, payload, occurred_at, received_at)`

- [ ] **Step 1: Write failing contract tests**

Add tests named `test_event_create_accepts_version_one`, `test_event_create_rejects_unknown_severity`, `test_event_create_requires_timezone`, and `test_event_create_does_not_accept_sequence`. Assert exact field normalization, the five allowed severity values, and timezone-aware `occurred_at`.

- [ ] **Step 2: Run contract tests and confirm failure**

Run: `python -m pytest services/event_gateway/tests/unit/test_contracts.py -v`  
Expected: FAIL because `event_gateway.contracts` does not exist.

- [ ] **Step 3: Implement the contract types**

Define `Severity = Literal["debug", "info", "warning", "error", "critical"]`, `EventCreate(BaseModel)`, and `StoredEvent(EventCreate)` with server-owned `sequence: int` and `received_at: datetime`. Reject naive datetimes and extra fields.

- [ ] **Step 4: Run contract tests and confirm pass**

Run: `python -m pytest services/event_gateway/tests/unit/test_contracts.py -v`  
Expected: PASS.

- [ ] **Step 5: Write failing migration test**

Add `test_events_migration_enforces_unique_event_id_and_server_sequence`. Apply the migration to the test PostgreSQL database, insert two distinct events, assert increasing sequence values, then assert duplicate `event_id` violates the unique constraint.

- [ ] **Step 6: Run migration test and confirm failure**

Run: `python -m pytest services/event_gateway/tests/integration/test_events_migration.py -v`  
Expected: FAIL because the migration is absent.

- [ ] **Step 7: Implement the SQL migration and development Compose service**

Create the table and three indexes exactly as specified in the design. Configure PostgreSQL 16 with a health check and a named volume; obtain credentials only from environment variables.

- [ ] **Step 8: Run Task 1 tests**

Run: `python -m pytest services/event_gateway/tests/unit/test_contracts.py services/event_gateway/tests/integration/test_events_migration.py -v`  
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add database docker-compose.yml services/event_gateway
git commit -m "feat: define durable fab event contract"
```

### Task 2: Idempotent Event Ingestion API

**Files:**
- Create: `services/event_gateway/src/event_gateway/config.py`
- Create: `services/event_gateway/src/event_gateway/repository.py`
- Create: `services/event_gateway/src/event_gateway/app.py`
- Create: `services/event_gateway/tests/unit/test_repository.py`
- Create: `services/event_gateway/tests/integration/test_event_api.py`

**Interfaces:**
- Consumes: `EventCreate`, `StoredEvent`, PostgreSQL `events` from Task 1
- Produces: `EventRepository.insert(event: EventCreate) -> tuple[StoredEvent, bool]`
- Produces: `EventRepository.list_after(sequence: int, limit: int) -> list[StoredEvent]`
- Produces: `EventRepository.high_water_sequence() -> int`
- Produces: `POST /api/v1/events` and `GET /api/v1/events?after_sequence=&limit=`

- [ ] **Step 1: Write failing repository tests**

Add `test_insert_returns_created_true`, `test_identical_duplicate_returns_original_with_created_false`, and `test_conflicting_duplicate_raises_event_conflict`. Compare all producer-owned fields when deciding whether a duplicate is identical.

- [ ] **Step 2: Run repository tests and confirm failure**

Run: `python -m pytest services/event_gateway/tests/unit/test_repository.py -v`  
Expected: FAIL because `EventRepository` is missing.

- [ ] **Step 3: Implement repository operations**

Implement `insert`, `get_by_event_id`, and `list_after`. Use `INSERT ... ON CONFLICT (event_id) DO NOTHING`, fetch the existing row on conflict, and raise `EventConflictError` if its producer-owned fields differ.

- [ ] **Step 4: Run repository tests and confirm pass**

Run: `python -m pytest services/event_gateway/tests/unit/test_repository.py -v`  
Expected: PASS.

- [ ] **Step 5: Write failing API tests**

Add `test_post_commits_and_returns_201`, `test_identical_retry_returns_200_and_same_sequence`, `test_conflicting_retry_returns_409`, `test_post_rejects_client_sequence`, and `test_list_after_returns_strictly_later_sequences`.

- [ ] **Step 6: Run API tests and confirm failure**

Run: `python -m pytest services/event_gateway/tests/integration/test_event_api.py -v`  
Expected: FAIL because routes are missing.

- [ ] **Step 7: Implement FastAPI application and routes**

Create `create_app(settings: Settings) -> FastAPI`. Return `201` for a new event, `200` for an identical retry, `409` for conflicting content, and `422` for invalid contracts. Bound replay `limit` to `1..1000`, default `200`.

- [ ] **Step 8: Run Task 2 tests**

Run: `python -m pytest services/event_gateway/tests -v`  
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add services/event_gateway
git commit -m "feat: add idempotent event ingestion API"
```

### Task 3: Jetson SQLite Outbox and HTTP Sender

**Files:**
- Create: `jetson_ws/src/fab_event_bridge/package.xml`
- Create: `jetson_ws/src/fab_event_bridge/setup.py`
- Create: `jetson_ws/src/fab_event_bridge/setup.cfg`
- Create: `jetson_ws/src/fab_event_bridge/fab_event_bridge/__init__.py`
- Create: `jetson_ws/src/fab_event_bridge/fab_event_bridge/contracts.py`
- Create: `jetson_ws/src/fab_event_bridge/fab_event_bridge/outbox.py`
- Create: `jetson_ws/src/fab_event_bridge/fab_event_bridge/sender.py`
- Create: `jetson_ws/src/fab_event_bridge/test/test_outbox.py`
- Create: `jetson_ws/src/fab_event_bridge/test/test_sender.py`

**Interfaces:**
- Consumes: `POST /api/v1/events` from Task 2
- Produces: `Outbox.enqueue(event: EventEnvelope) -> None`
- Produces: `Outbox.pending(limit: int) -> list[PendingEvent]`
- Produces: `Outbox.mark_delivered(event_id: UUID, sequence: int) -> None`
- Produces: `EventSender.run_once(limit: int = 100) -> SendSummary`

- [ ] **Step 1: Write failing outbox tests**

Add `test_enqueue_is_durable_across_reopen`, `test_enqueue_same_event_is_idempotent`, `test_pending_is_oldest_first`, and `test_mark_delivered_removes_event_from_pending`. Use a temporary on-disk SQLite file rather than `:memory:` for restart coverage.

- [ ] **Step 2: Run outbox tests and confirm failure**

Run: `python -m pytest jetson_ws/src/fab_event_bridge/test/test_outbox.py -v`  
Expected: FAIL because `Outbox` is missing.

- [ ] **Step 3: Implement the SQLite outbox**

Use WAL mode and explicit transactions. Store the immutable serialized event, enqueue time, attempt count, next-attempt time, delivered sequence, and last error. Do not delete the row until the gateway response is validated.

- [ ] **Step 4: Run outbox tests and confirm pass**

Run: `python -m pytest jetson_ws/src/fab_event_bridge/test/test_outbox.py -v`  
Expected: PASS.

- [ ] **Step 5: Write failing sender tests**

Add `test_2xx_marks_event_delivered`, `test_timeout_leaves_event_pending`, `test_5xx_schedules_exponential_retry`, `test_4xx_schema_error_is_quarantined`, and `test_commit_then_response_loss_retry_is_accepted`. Stub the HTTP transport; do not require a live server.

- [ ] **Step 6: Run sender tests and confirm failure**

Run: `python -m pytest jetson_ws/src/fab_event_bridge/test/test_sender.py -v`  
Expected: FAIL because `EventSender` is missing.

- [ ] **Step 7: Implement the HTTP sender**

Inject an `EventTransport` protocol with `post_event(event) -> GatewayReceipt`. Apply capped exponential backoff with jitter to transport errors and `5xx`; quarantine non-retryable `4xx` responses while retaining their record for inspection.

- [ ] **Step 8: Run Task 3 tests**

Run: `python -m pytest jetson_ws/src/fab_event_bridge/test -v`  
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add jetson_ws/src/fab_event_bridge
git commit -m "feat: add durable Jetson event outbox"
```

### Task 4: ROS 2 Topic Adapter

**Files:**
- Create: `jetson_ws/src/fab_event_bridge/fab_event_bridge/node.py`
- Create: `jetson_ws/src/fab_event_bridge/test/test_node_adapter.py`
- Modify: `jetson_ws/src/fab_event_bridge/setup.py`

**Interfaces:**
- Consumes: `/fab/events` messages of type `std_msgs/msg/String`
- Consumes: `Outbox.enqueue(event: EventEnvelope) -> None` from Task 3
- Produces: `parse_ros_event(raw: str, now: Callable[[], datetime]) -> EventEnvelope`
- Produces: console entry point `fab_event_bridge = fab_event_bridge.node:main`

- [ ] **Step 1: Write failing adapter tests**

Add `test_valid_ros_json_is_enqueued`, `test_missing_event_id_is_generated_once_before_enqueue`, `test_malformed_json_is_rejected_without_enqueue`, and `test_invalid_schema_does_not_stop_next_message`. Test the pure callback adapter without starting a ROS graph.

- [ ] **Step 2: Run adapter tests and confirm failure**

Run: `python -m pytest jetson_ws/src/fab_event_bridge/test/test_node_adapter.py -v`  
Expected: FAIL because the adapter is missing.

- [ ] **Step 3: Implement parser and ROS 2 node**

Keep `rclpy` imports at the adapter boundary. The callback validates one message, logs rejection without payload secrets, enqueues valid data synchronously, and lets the sender worker perform network I/O outside the callback.

- [ ] **Step 4: Run ROS-independent tests**

Run: `python -m pytest jetson_ws/src/fab_event_bridge/test -v`  
Expected: PASS on a machine without ROS 2 installed.

- [ ] **Step 5: Run ROS 2 package tests on Jetson**

Run: `cd jetson_ws && colcon test --packages-select fab_event_bridge && colcon test-result --verbose`  
Expected: package tests pass with zero failures.

- [ ] **Step 6: Commit**

```bash
git add jetson_ws/src/fab_event_bridge
git commit -m "feat: bridge ROS 2 events to durable outbox"
```

### Task 5: WebSocket Stream and Race-Free Replay

**Files:**
- Create: `services/event_gateway/src/event_gateway/stream.py`
- Modify: `services/event_gateway/src/event_gateway/app.py`
- Create: `services/event_gateway/tests/unit/test_stream.py`
- Create: `services/event_gateway/tests/integration/test_websocket_replay.py`

**Interfaces:**
- Consumes: `StoredEvent`, `EventRepository.list_after` from Tasks 1 and 2
- Produces: `EventHub.publish(event: StoredEvent) -> None`
- Produces: `WS /api/v1/stream?after_sequence={n}`

- [ ] **Step 1: Write failing stream tests**

Add `test_publish_sends_events_in_sequence_order`, `test_slow_client_does_not_block_other_clients`, and `test_disconnect_removes_client`. Give each client a bounded queue and terminate a client whose queue overflows.

- [ ] **Step 2: Run stream tests and confirm failure**

Run: `python -m pytest services/event_gateway/tests/unit/test_stream.py -v`  
Expected: FAIL because `EventHub` is missing.

- [ ] **Step 3: Implement the in-process event hub**

Implement register, unregister, and publish operations with one bounded `asyncio.Queue[StoredEvent]` per connection. Publish only after repository insertion returns from its committed transaction.

- [ ] **Step 4: Write failing replay race test**

Add `test_event_committed_during_replay_is_delivered_once`. Connect with `after_sequence=N`, commit another event while historical rows are being replayed, and assert the client sees every sequence greater than `N` exactly once in order.

- [ ] **Step 5: Run replay test and confirm failure**

Run: `python -m pytest services/event_gateway/tests/integration/test_websocket_replay.py -v`  
Expected: FAIL because the stream handshake is incomplete.

- [ ] **Step 6: Implement the replay/live handshake**

Register the client before reading the replay high-water mark, replay `(after_sequence, high_water]`, then drain queued live events while discarding sequences at or below the high-water mark. Continue live delivery afterward.

- [ ] **Step 7: Run Task 5 tests**

Run: `python -m pytest services/event_gateway/tests -v`  
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add services/event_gateway
git commit -m "feat: stream committed events to Unity"
```

### Task 6: Unity Event Client and Cursor

**Files:**
- Create: `unity/Assets/FabEvents/Runtime/EventEnvelope.cs`
- Create: `unity/Assets/FabEvents/Runtime/EventCursor.cs`
- Create: `unity/Assets/FabEvents/Runtime/IEventTransport.cs`
- Create: `unity/Assets/FabEvents/Runtime/EventStreamCoordinator.cs`
- Create: `unity/Assets/FabEvents/Runtime/EventApiClient.cs`
- Create: `unity/Assets/FabEvents/Tests/EditMode/EventEnvelopeTests.cs`
- Create: `unity/Assets/FabEvents/Tests/EditMode/EventStreamCoordinatorTests.cs`
- Create: `unity/Assets/FabEvents/FabEvents.asmdef`
- Create: `unity/Assets/FabEvents/Tests/EditMode/FabEvents.Tests.asmdef`

**Interfaces:**
- Consumes: `GET /api/v1/events` and `WS /api/v1/stream` from Tasks 2 and 5
- Produces: `EventStreamCoordinator.StartAsync(CancellationToken) -> Task`
- Produces: `event Action<EventEnvelope> EventApplied`
- Produces: persisted `EventCursor.LastSequence`

- [ ] **Step 1: Write failing Unity contract tests**

Add `DeserializeStoredEvent_UsesServerSequence`, `RejectsUnknownSchemaVersion`, and `FormatsOccurredAtInKoreanTime`. Use a fixed UTC fixture and assert the Asia/Seoul conversion.

- [ ] **Step 2: Run EditMode tests and confirm failure**

Run Unity in batch mode with `-runTests -testPlatform EditMode -projectPath unity`.  
Expected: FAIL because runtime types are missing.

- [ ] **Step 3: Implement event contract and durable cursor**

Define serializable event DTOs and `IEventCursorStore`. Provide a `PlayerPrefsEventCursorStore` implementation under a versioned key; persist only after the event has been applied successfully.

- [ ] **Step 4: Write failing ordering tests**

Add `ReplayThenLive_AppliesEverySequenceOnce`, `DuplicateSequence_IsIgnored`, `Gap_TriggersReplayFromLastSequence`, and `HandlerFailure_DoesNotAdvanceCursor`. Use an in-memory fake transport.

- [ ] **Step 5: Run ordering tests and confirm failure**

Run the Unity EditMode test command.  
Expected: FAIL because the coordinator is missing.

- [ ] **Step 6: Implement transport boundary and coordinator**

Keep UnityWebRequest and WebSocket library calls inside `EventApiClient`. The coordinator owns replay, ordered application, duplicate suppression, gap recovery, cancellation, and reconnect backoff.

- [ ] **Step 7: Run Task 6 tests**

Run the Unity EditMode test command.  
Expected: all FabEvents EditMode tests PASS.

- [ ] **Step 8: Commit**

```bash
git add unity/Assets/FabEvents
git commit -m "feat: add replayable Unity event client"
```

### Task 7: Unity Anomaly Injection Command

**Files:**
- Create: `database/migrations/002_create_injection_commands.sql`
- Create: `services/event_gateway/src/event_gateway/commands.py`
- Modify: `services/event_gateway/src/event_gateway/app.py`
- Create: `services/event_gateway/tests/integration/test_injection_api.py`
- Create: `unity/Assets/FabEvents/Runtime/AnomalyInjectionClient.cs`
- Create: `unity/Assets/FabEvents/Tests/EditMode/AnomalyInjectionClientTests.cs`

**Interfaces:**
- Produces: `POST /api/v1/lots/injections`
- Produces: `AnomalyInjectionClient.InjectAsync(AnomalyInjection command, CancellationToken) -> Task<CommandReceipt>`
- Produces: committed `lot.injection.requested` event correlated by lot identifier

- [ ] **Step 1: Write failing gateway command tests**

Add `test_injection_creates_command_and_audit_event_atomically`, `test_invalid_knob_returns_422`, `test_duplicate_command_id_is_idempotent`, and `test_database_failure_creates_neither_record`.

- [ ] **Step 2: Run gateway command tests and confirm failure**

Run: `python -m pytest services/event_gateway/tests/integration/test_injection_api.py -v`  
Expected: FAIL because the endpoint is missing.

- [ ] **Step 3: Implement command transaction**

Accept only `oxide_thickness`, `body_dose`, `diffusion_time`, and `epi_doping`. Create the injection command table in migration `002`, then store the command and its audit event in one transaction and return their identifiers after commit.

- [ ] **Step 4: Write failing Unity command tests**

Add `InjectAsync_SerializesCommandIdAndKnob`, `InjectAsync_RetryPreservesCommandId`, and `InjectAsync_ServerErrorDoesNotReportSuccess` using a fake HTTP transport.

- [ ] **Step 5: Run Unity command tests and confirm failure**

Run the Unity EditMode test command.  
Expected: FAIL because `AnomalyInjectionClient` is missing.

- [ ] **Step 6: Implement the Unity injection client**

Generate one command UUID per user action and preserve it across retry attempts. Surface committed, validation-error, and retryable-failure states separately to the UI layer.

- [ ] **Step 7: Run Task 7 tests**

Run the gateway integration test and Unity EditMode tests.  
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add database/migrations/002_create_injection_commands.sql services/event_gateway unity/Assets/FabEvents
git commit -m "feat: persist Unity anomaly injection commands"
```

### Task 8: End-to-End Failure Recovery Harness

**Files:**
- Modify: `docker-compose.yml`
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_event_recovery.py`
- Create: `scripts/run-e2e.ps1`
- Create: `scripts/run-e2e.sh`
- Create: `docs/runbooks/event-pipeline-local.md`

**Interfaces:**
- Consumes: all prior task interfaces
- Produces: repeatable local acceptance test and operator runbook

- [ ] **Step 1: Write failing end-to-end tests**

Add `test_ros_event_reaches_postgres_and_stream`, `test_gateway_outage_replays_all_outbox_events`, `test_response_loss_does_not_duplicate_postgres_row`, `test_jetson_restart_recovers_pending_events`, and `test_unity_reconnect_replays_all_missing_sequences`.

- [ ] **Step 2: Run end-to-end tests and confirm initial failure**

Run: `docker compose up -d --build postgres gateway && python -m pytest tests/e2e -v`  
Expected: at least one recovery test FAIL until lifecycle controls and fixtures are complete.

- [ ] **Step 3: Complete deterministic fault controls**

Add test-only Compose profiles or fixtures that stop the gateway, sever the sender response after commit, restart the bridge process, and disconnect the WebSocket client. Do not put fault-control endpoints in the production application.

- [ ] **Step 4: Run the full acceptance suite**

Run: `./scripts/run-e2e.ps1` on Windows and `./scripts/run-e2e.sh` on Linux/Jetson.  
Expected: all five recovery tests PASS; duplicate query returns zero grouped duplicates.

- [ ] **Step 5: Write and verify the runbook**

Document environment variables, database migration, Gateway startup, ROS 2 topic test publisher, Unity endpoint configuration, recovery behavior, and clean shutdown. Execute every command once from a clean Compose volume.

- [ ] **Step 6: Run all automated tests**

Run Python unit/integration suites, ROS 2 package tests on Jetson, Unity EditMode tests, and the E2E script.  
Expected: every suite exits `0` with no skipped recovery tests.

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml tests/e2e scripts docs/runbooks
git commit -m "test: verify event pipeline failure recovery"
```

## Final Verification

- [ ] Publish ten ROS 2 events while the Gateway is available; confirm ten PostgreSQL rows and ten Unity applications.
- [ ] Stop the Gateway, publish ten more events, restart it, and confirm all twenty unique `event_id` values in PostgreSQL.
- [ ] Disconnect Unity, publish five events, reconnect it, and confirm its cursor advances without a sequence gap.
- [ ] Retry a committed event with the same body and confirm the same sequence is returned.
- [ ] Retry the same `event_id` with changed payload and confirm `409 Conflict`.
- [ ] Confirm neither Jetson nor Unity configuration contains PostgreSQL credentials.
- [ ] Confirm no MQTT dependency or broker exists in Compose or package manifests.
