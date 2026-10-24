# Jetson Camera Preview and Ring Buffer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jetson이 인증된 IP 카메라 스트림을 한 번만 수신해 제한된 RAM Ring Buffer와 Unity Preview를 제공하고, Unity가 지정한 프레임을 영속 AOI 큐에서 추론·저장하도록 구현한다.

**Architecture:** `fab_aoi_unity_server` 프로세스가 장시간 실행되는 camera service, Preview WebSocket, bounded AOI dispatcher를 조립한다. Preview와 AOI 제어 연결은 분리하고, AOI는 선택 프레임을 디스크·SQLite에 고정한 뒤 `accepted`를 반환하며 기존 ROS outbox와 Aiven 저장 경로를 유지한다.

**Tech Stack:** Python 3.10, ROS 2 Humble/rclpy, OpenCV, NumPy, `websockets.sync`, SQLite, `concurrent.futures.ThreadPoolExecutor`, pytest

**Spec:** `docs/superpowers/specs/2026-10-20-jetson-camera-preview-ring-buffer-design.md`

## Global Constraints

- IP 카메라에는 Jetson의 camera source 하나만 연결한다.
- `CAMERA_MODE=mock|prod`를 지원하고 prod 실패를 mock 성공으로 대체하지 않는다.
- 운영 기본 입력은 HTTPS이며 HTTP는 `CAMERA_ALLOW_HTTP=true`일 때만 허용한다.
- 카메라 URL·계정·비밀번호는 로그, ROS 2, WebSocket 결과, DB에 기록하지 않는다.
- Ring Buffer 기본 상한은 2초와 128MiB이며 두 조건 중 먼저 도달한 조건으로 퇴출한다.
- Preview 기본값은 1280x720, 5FPS, JPEG quality 75, 최대 클라이언트 2개다.
- Preview는 `:8500/camera/preview`, AOI 요청·결과는 기존 `:8400/aoi`를 사용한다.
- Unity가 지정한 `frame_id`가 없으면 `stale_frame`이며 최신 프레임으로 대체하지 않는다.
- AOI executor 기본 worker는 1이고 부품·결함 모델은 한 작업 안에서 순차 실행한다.
- AOI와 별도 Surrogate Worker는 병렬 실행한다.
- Preview 전체 영상은 디스크나 Aiven에 저장하지 않고 요청에 고정된 원본·결과만 저장한다.
- Jetson 전력·클럭·팬·네트워크 시스템 설정을 변경하지 않는다.

## Review Focus

- 인증정보를 포함한 카메라 연결 오류가 발생해도 로그와 예외 문자열에는 비밀번호가 없어야 한다. Task 2의 redaction 시험으로 고정한다.
- 느린 Unity Preview 클라이언트가 capture thread를 막거나 메모리를 증가시키지 않아야 한다. Task 3의 latest-only queue 시험으로 고정한다.
- `accepted` 직후 Jetson 프로세스가 종료돼도 선택 프레임과 queued 작업이 복구돼야 한다. Task 4의 재시작 시험으로 고정한다.
- Ring Buffer에서 퇴출된 `frame_id` 요청은 최신 프레임을 추론하지 않고 `stale_frame`을 반환해야 한다. Task 5의 계약 시험으로 고정한다.
- AOI 실행 중 Surrogate 요청과 ROS ACK가 처리되고, 같은 GPU AOI 작업 두 건은 동시에 실행되지 않아야 한다. Task 6의 동시성 시험으로 고정한다.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/camera_buffer.py` | 불변 `CameraFrame`, 시간·바이트 제한 Ring Buffer |
| `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/camera_source.py` | mock/prod 설정, 인증된 MJPEG HTTP(S) source, 비밀값 redaction |
| `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/camera_service.py` | capture thread, frame ID, reconnect, subscriber-independent frame lifecycle |
| `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/camera_preview.py` | Preview 계약, JPEG 변환, 클라이언트별 latest-only 송신 |
| `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_dispatcher.py` | 선택 프레임 영속화, SQLite job 상태, bounded executor, 완료 callback |
| `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_unity.py` | 기존 AOI 계약을 dispatcher와 camera service에 연결하는 조립부 |
| `jetson_ws/src/fab_virtual_lot/setup.py` | 패키지 모듈·실행 의존성 확인 |
| `jetson_ws/src/fab_virtual_lot/test/test_camera_*.py` | buffer/source/service/preview 독립 시험 |
| `jetson_ws/src/fab_virtual_lot/test/test_aoi_dispatcher.py` | 영속 큐·재시작·포화·순차 실행 시험 |
| `jetson_ws/src/fab_virtual_lot/test/test_aoi_unity_direct.py` | Unity 요청·비동기 완료·ROS outbox 회귀 시험 |
| `docs/examples/process-inspection.env.example` | 비밀값 없는 환경변수 기준 |
| `docs/api/asyncapi.yaml` | Preview와 비동기 AOI 메시지 명세 |
| `docs/runbooks/jetson-camera-preview-aoi.md` | Jetson 배포·실행·Unity 전달·검증·복구 절차 |

### Task 1: 불변 프레임과 제한 Ring Buffer

**Files:**
- Create: `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/camera_buffer.py`
- Create: `jetson_ws/src/fab_virtual_lot/test/test_camera_buffer.py`

**Interfaces:**
- Produces: `CameraFrame`, `FrameBounds`, `FrameBufferStats`, `FrameRingBuffer.put()`, `get_copy()`, `bounds()`, `stats()`
- Consumes: NumPy BGR frame and injected monotonic clock

- [ ] **Step 1: Write failing buffer tests**

Add tests named `test_ring_buffer_evicts_by_age`, `test_ring_buffer_evicts_by_byte_limit`, `test_get_copy_is_not_mutated_by_capture_reuse`, and `test_missing_frame_reports_available_bounds`. Assert a 2-second/128MiB-equivalent configured buffer evicts the oldest entry first and returns copies.

- [ ] **Step 2: Run the tests and confirm RED**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_camera_buffer.py -v`

Expected: collection fails because `camera_buffer` does not exist.

- [ ] **Step 3: Implement the buffer API**

Implement immutable metadata around a read-only/copy-owned NumPy image. `put(frame: CameraFrame) -> None` accounts for `image.nbytes`; `get_copy(frame_id: int) -> CameraFrame | None` returns an isolated image; eviction applies age then bytes under a lock.

- [ ] **Step 4: Run GREEN and regression tests**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_camera_buffer.py jetson_ws/src/fab_virtual_lot/test/test_aoi_pipeline.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jetson_ws/src/fab_virtual_lot/fab_virtual_lot/camera_buffer.py jetson_ws/src/fab_virtual_lot/test/test_camera_buffer.py
git commit -m "feat: add bounded camera frame ring buffer"
```

### Task 2: 인증 IP 카메라 Source와 설정

**Files:**
- Create: `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/camera_source.py`
- Create: `jetson_ws/src/fab_virtual_lot/test/test_camera_source.py`
- Modify: `jetson_ws/src/fab_virtual_lot/setup.py`

**Interfaces:**
- Consumes: `CAMERA_MODE`, source URL, basic-auth credentials, TLS/HTTP policy, fixture path
- Produces: `CameraSettings.from_env(env)`, `CameraSource.read() -> numpy.ndarray`, `CameraSource.close()`, `make_camera_source(settings)`

- [ ] **Step 1: Write failing configuration and source tests**

Cover `mock` fixture loading, HTTPS acceptance, HTTP rejection unless explicitly enabled, unsupported scheme rejection, empty credentials, MJPEG JPEG-boundary decoding from a fake byte stream, timeout propagation, and safe close.

- [ ] **Step 2: Add the password redaction regression test**

Use a sentinel password and force connection/decode failure. Assert the password is absent from `str(exc)`, `repr(exc)`, and captured logs.

- [ ] **Step 3: Run tests and confirm RED**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_camera_source.py -v`

Expected: FAIL because the source API is missing.

- [ ] **Step 4: Implement settings and source adapters**

Use a standard-library authenticated HTTP(S) stream reader plus `cv2.imdecode` for JPEG frames so username/password and TLS verification remain separate from the logged URL. Support a test-injected opener/stream. Never include the credential-bearing request object in raised application errors.

- [ ] **Step 5: Run GREEN and dependency discovery tests**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_camera_source.py jetson_ws/src/fab_virtual_lot/test/test_package_discovery.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add jetson_ws/src/fab_virtual_lot/fab_virtual_lot/camera_source.py jetson_ws/src/fab_virtual_lot/test/test_camera_source.py jetson_ws/src/fab_virtual_lot/setup.py
git commit -m "feat: add authenticated IP camera source"
```

### Task 3: 장시간 Capture Service와 Preview Broadcaster

**Files:**
- Create: `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/camera_service.py`
- Create: `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/camera_preview.py`
- Create: `jetson_ws/src/fab_virtual_lot/test/test_camera_service.py`
- Create: `jetson_ws/src/fab_virtual_lot/test/test_camera_preview.py`

**Interfaces:**
- Consumes: Task 1 `FrameRingBuffer`, Task 2 `CameraSource`
- Produces: `CameraCaptureService.start()`, `stop()`, `latest_status()`, `PreviewSubscription`, `CameraPreviewService.handle(websocket)`

- [ ] **Step 1: Write failing capture lifecycle tests**

Test monotonic frame IDs, configured FPS throttling with injected clock, reconnect after read failure, stop/close idempotence, and no unbounded pending frames.

- [ ] **Step 2: Write failing Preview tests**

Test first-message token authentication, `subscribed` negotiation, JSON-then-binary ordering, JPEG dimensions, max-client rejection, no encoding without subscribers, and client disconnect cleanup.

- [ ] **Step 3: Pin the slow-client behavior**

Block a fake client sender while publishing multiple frames. Assert its pending queue remains size 1 and the eventual payload is the newest frame ID.

- [ ] **Step 4: Run tests and confirm RED**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_camera_service.py jetson_ws/src/fab_virtual_lot/test/test_camera_preview.py -v`

Expected: FAIL because the services are missing.

- [ ] **Step 5: Implement capture and Preview services**

Keep capture, encoding, and each client sender isolated. Preview resizing and JPEG encoding run only while at least one authenticated subscriber exists. Expose status and counters without credentials.

- [ ] **Step 6: Run GREEN and leak-focused repeat test**

Run the following command three times without adding a test plugin:

`python -m pytest jetson_ws/src/fab_virtual_lot/test/test_camera_service.py jetson_ws/src/fab_virtual_lot/test/test_camera_preview.py -v`

- [ ] **Step 7: Commit**

```bash
git add jetson_ws/src/fab_virtual_lot/fab_virtual_lot/camera_service.py jetson_ws/src/fab_virtual_lot/fab_virtual_lot/camera_preview.py jetson_ws/src/fab_virtual_lot/test/test_camera_service.py jetson_ws/src/fab_virtual_lot/test/test_camera_preview.py
git commit -m "feat: stream bounded camera preview to Unity"
```

### Task 4: 선택 프레임 영속 AOI Dispatcher

**Files:**
- Create: `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_dispatcher.py`
- Create: `jetson_ws/src/fab_virtual_lot/test/test_aoi_dispatcher.py`
- Modify: `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_pipeline.py`

**Interfaces:**
- Consumes: `CameraFrame`, existing `inspect_image` pipeline and models
- Produces: `AoiDispatcher.submit(request, frame) -> AoiAccepted`, `subscribe(job_id, callback)`, `recover()`, `close()` and persisted states `queued|running|succeeded|failed`

- [ ] **Step 1: Write failing persistence tests**

Test atomic selected-frame file creation, SQLite request snapshot, duplicate same-body idempotency, duplicate different-body conflict, queue capacity, and original file hash metadata.

- [ ] **Step 2: Write the restart recovery test**

Submit and receive `accepted`, close before execution, create a new dispatcher over the same DB/spool, call `recover()`, and assert it runs the same pinned image and reaches `succeeded`.

- [ ] **Step 3: Write the executor serialization test**

Block the first AOI infer call, submit a second, and assert active AOI calls never exceed one while both eventually complete in order.

- [ ] **Step 4: Run tests and confirm RED**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_aoi_dispatcher.py -v`

Expected: FAIL because the dispatcher is missing.

- [ ] **Step 5: Implement bounded durable dispatch**

Persist a lossless or configured original image and request record before returning `accepted`. Use `ThreadPoolExecutor(max_workers=AOI_EXECUTOR_WORKERS)` but reject values other than 1 for the current GPU contract. Update states transactionally and deliver completion callbacks outside the DB lock.

- [ ] **Step 6: Run GREEN and AOI pipeline regression**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_aoi_dispatcher.py jetson_ws/src/fab_virtual_lot/test/test_aoi_pipeline.py jetson_ws/src/fab_virtual_lot/test/test_aoi_runtime.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_dispatcher.py jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_pipeline.py jetson_ws/src/fab_virtual_lot/test/test_aoi_dispatcher.py
git commit -m "feat: add durable asynchronous AOI dispatcher"
```

### Task 5: Unity AOI WebSocket 비동기 계약 통합

**Files:**
- Modify: `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_unity.py`
- Modify: `jetson_ws/src/fab_virtual_lot/test/test_aoi_unity_direct.py`
- Create: `jetson_ws/src/fab_virtual_lot/test/test_camera_aoi_contract.py`

**Interfaces:**
- Consumes: camera service/buffer, Preview service, AOI dispatcher, existing result builder/outbox
- Produces: immediate `aoi.inspection.accepted|rejected`, asynchronous `aoi.inspection.completed|failed`, annotated binary frame

- [ ] **Step 1: Write failing contract tests**

Test valid displayed frame acceptance, exact frame passed to inference, completion JSON followed by annotated JPEG, `stale_frame` bounds, `queue_full`, invalid camera ID, invalid token, and connection-close-safe completion persistence.

- [ ] **Step 2: Pin stale-frame non-substitution**

Place only frame 11 in the buffer and request frame 10. Assert inference is never called and response is `stale_frame` rather than processing frame 11.

- [ ] **Step 3: Run tests and confirm RED**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_camera_aoi_contract.py jetson_ws/src/fab_virtual_lot/test/test_aoi_unity_direct.py -v`

Expected: FAIL against the current synchronous fixture-only server.

- [ ] **Step 4: Refactor `AoiUnityService` around dispatcher**

Keep a single sender path per WebSocket connection. The receive path validates and submits; a bounded outgoing queue serializes accepted/completed metadata and binary frames. A disconnected Unity session must not cancel a persisted AOI job.

- [ ] **Step 5: Compose both WebSocket servers in one process**

Start camera capture once, serve Preview on 8500 and AOI control on 8400, preserve ROS bridge/outbox, and shut down servers, dispatcher, camera, ROS node in reverse dependency order.

- [ ] **Step 6: Run GREEN and all Jetson unit tests**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test -v`

Expected: PASS without an actual camera, ROS daemon, or Unity application.

- [ ] **Step 7: Commit**

```bash
git add jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_unity.py jetson_ws/src/fab_virtual_lot/test/test_aoi_unity_direct.py jetson_ws/src/fab_virtual_lot/test/test_camera_aoi_contract.py
git commit -m "feat: queue frame-specific Unity AOI requests"
```

### Task 6: AOI·Surrogate·ROS 병렬성 통합 검증

**Files:**
- Create: `jetson_ws/src/fab_virtual_lot/test/test_parallel_workers.py`
- Modify: `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/surrogate_worker.py`
- Modify: `jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_unity.py`

**Interfaces:**
- Consumes: existing separate AOI and Surrogate process contracts
- Produces: observable non-blocking callbacks and bounded execution metrics

- [ ] **Step 1: Write the failing concurrency test**

Block AOI inference, complete a fake Surrogate CPU/HTTP inference, deliver an AOI ROS ACK, and assert both finish before releasing AOI. Submit two AOI jobs and assert only one AOI inference is active.

- [ ] **Step 2: Run test and confirm RED or expose blocking**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_parallel_workers.py -v`

Expected: FAIL until blocking callbacks are separated.

- [ ] **Step 3: Make only the minimal callback/executor changes**

Keep AOI and Surrogate as separate processes. Do not introduce a shared global pool or CUDA process pool. Ensure ROS spin/ACK and WebSocket receive remain responsive while worker futures execute.

- [ ] **Step 4: Run GREEN and worker regression tests**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_parallel_workers.py jetson_ws/src/fab_virtual_lot/test/test_surrogate_runtime.py jetson_ws/src/fab_virtual_lot/test/test_aoi_runtime.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jetson_ws/src/fab_virtual_lot/fab_virtual_lot/surrogate_worker.py jetson_ws/src/fab_virtual_lot/fab_virtual_lot/aoi_unity.py jetson_ws/src/fab_virtual_lot/test/test_parallel_workers.py
git commit -m "perf: isolate AOI and surrogate worker execution"
```

### Task 7: 환경변수·AsyncAPI·Jetson 적용 문서

**Files:**
- Modify: `.env.example`
- Modify: `docs/examples/process-inspection.env.example`
- Modify: `docs/api/asyncapi.yaml`
- Modify: `docs/api/README.md`
- Modify: `docs/architecture/current-system-architecture.md`
- Create: `docs/runbooks/jetson-camera-preview-aoi.md`
- Create: `tools/mock_unity/camera_preview_client.py`
- Create: `tools/mock_unity/aoi_frame_client.py`
- Create: `jetson_ws/src/fab_virtual_lot/test/test_camera_runbook.py`

**Interfaces:**
- Consumes: Tasks 1-6 runtime and contracts
- Produces: secret-free deployment configuration, mock Unity clients, copy/build/run/verify/rollback procedure

- [ ] **Step 1: Write failing documentation and launcher contract tests**

Assert required env keys and endpoints appear, no real username/password appears, commands use `/home/jetson/project/smart_factory`, and mock clients construct `frame_id` requests from displayed Preview metadata.

- [ ] **Step 2: Run contract tests and confirm RED**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_camera_runbook.py -v`

Expected: FAIL until artifacts exist.

- [ ] **Step 3: Update env and API contracts**

Add all camera/Preview/AOI queue keys with placeholders. Document JSON and binary ordering, stale/queue errors, and keep real camera credentials out of tracked files.

- [ ] **Step 4: Implement mock Unity clients**

The Preview client authenticates, receives one metadata+JPEG pair, optionally saves it, and prints only non-secret IDs. The AOI frame client submits that `frame_id`, observes accepted then completed, verifies the image hash, and supports mock camera mode.

- [ ] **Step 5: Write the Jetson runbook**

Include backup scope explanation, source copy or Git pull, venv/package check, `colcon build --packages-select fab_virtual_lot --symlink-install`, local `.env.camera-prod` creation with placeholders, four required terminals/processes, port checks, mock-first test, prod switch, `tegrastats`/`free -h`, result/ROS/Aiven verification, and rollback that restores only project files.

- [ ] **Step 6: Run GREEN and documentation checks**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test/test_camera_runbook.py -v`

Run: `git diff --check`

Expected: PASS and no whitespace errors.

- [ ] **Step 7: Commit**

```bash
git add .env.example docs/examples/process-inspection.env.example docs/api/asyncapi.yaml docs/api/README.md docs/architecture/current-system-architecture.md docs/runbooks/jetson-camera-preview-aoi.md tools/mock_unity/camera_preview_client.py tools/mock_unity/aoi_frame_client.py jetson_ws/src/fab_virtual_lot/test/test_camera_runbook.py
git commit -m "docs: add Jetson camera deployment and Unity test flow"
```

### Task 8: 전체 회귀와 Jetson 적용 전 패키지 검증

**Files:**
- Modify only files required by failures attributable to Tasks 1-7.

**Interfaces:**
- Consumes: complete implementation
- Produces: test evidence and a clean, reproducible Jetson deployment handoff

- [ ] **Step 1: Run all Jetson package tests**

Run: `python -m pytest jetson_ws/src/fab_virtual_lot/test -v`

Expected: PASS.

- [ ] **Step 2: Run Gateway unit and camera-related integration regressions**

Run: `python -m pytest services/event_gateway/tests/unit services/event_gateway/tests/integration/test_aoi_event_storage.py services/event_gateway/tests/integration/test_ros_bridge_storage.py -v`

Expected: PASS, with DB-dependent tests skipped only when their documented test DB is unavailable.

- [ ] **Step 3: Build the ROS package in WSL/Jetson-compatible environment**

Run:

```bash
source /opt/ros/humble/setup.bash
cd /mnt/c/posco_project/jetson_ws
colcon build --packages-select fab_virtual_lot --symlink-install
source install/setup.bash
ros2 pkg executables fab_virtual_lot
```

Expected: build succeeds and `fab_aoi_unity_server`, `fab_aoi_worker`, `fab_surrogate_worker` remain discoverable.

- [ ] **Step 4: Run mock camera-to-Unity-to-Aiven E2E**

Start Gateway, AOI/Preview server, Surrogate mock/worker, and Python Unity clients according to the new runbook. Verify Preview frame ID, AOI accepted/completed, annotated JPEG, ROS event ACK, and Aiven row using identifiers rather than secrets.

- [ ] **Step 5: Capture final resource verification instructions**

Confirm the runbook records how to compare idle, capture, Preview, AOI, and AOI+Surrogate with `tegrastats` and `free -h`; do not claim 24-hour stability without an actual soak test.

- [ ] **Step 6: Run final diff checks and commit fixes**

Run: `git diff --check`

Commit only implementation-related fixes with the matching `fix:`, `test:`, or `docs:` prefix.
