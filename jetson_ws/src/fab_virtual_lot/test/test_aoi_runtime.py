import json
from uuid import uuid4

import numpy as np

from fab_virtual_lot.aoi_pipeline import AoiConfig, MockModel
from fab_virtual_lot.aoi_runtime import AoiRuntime


def test_request_is_durable_and_result_replays_once(tmp_path):
    run_id, job_id, request_id = uuid4(), uuid4(), uuid4()
    request = {"schema_version": 1, "request_id": str(request_id),
               "run_id": str(run_id), "job_id": str(job_id), "attempt": 1,
               "lot_id": "LOT-1", "task_type": "aoi"}
    db = tmp_path / "aoi.sqlite"
    config = AoiConfig(tmp_path / "result", .35, .20, .45, .35, "mock", "wsl-jetson")
    frame = np.full((32, 32, 3), 128, dtype=np.uint8)
    with AoiRuntime(db, config) as runtime:
        assert runtime.accept(request)
        assert runtime.accept(request)
        assert not runtime.accept(dict(request, job_id=str(uuid4())))
    with AoiRuntime(db, config) as runtime:
        assert runtime.process_next(lambda _request: frame, MockModel(0, .97, (2, 2, 20, 20)),
                                    MockModel(1, .92, (4, 4, 16, 16)))
        assert runtime.process_next(lambda _request: frame, None, None) is None
        pending = runtime.pending_events()
        assert len(pending) == 1
        event = json.loads(pending[0][2])
        assert event["event_type"] == "aoi.inspection.completed"
        assert event["payload"]["verdict"] == "fail"
        assert event["payload"]["images"]["annotated"]["file_name"] == "annotated.jpg"
        assert runtime.ack(event["event_id"], event["run_id"], 7)
        assert not runtime.pending_events()


def test_capture_receives_persisted_fixture_name(tmp_path):
    run_id, job_id, request_id = uuid4(), uuid4(), uuid4()
    request = {"schema_version": 1, "request_id": str(request_id),
               "run_id": str(run_id), "job_id": str(job_id), "attempt": 1,
               "lot_id": "LOT-1", "task_type": "aoi", "fixture_name": "sample.png"}
    config = AoiConfig(tmp_path / "result", .35, .20, .45, .35, "mock", "wsl-jetson")
    seen = []
    with AoiRuntime(tmp_path / "aoi.sqlite", config) as runtime:
        runtime.accept(request)
        runtime.process_next(lambda saved: seen.append(saved["fixture_name"]) or
                             np.full((32, 32, 3), 128, dtype=np.uint8),
                             MockModel(0, .97, (2, 2, 20, 20)),
                             MockModel(1, 0, (4, 4, 16, 16)))
    assert seen == ["sample.png"]


def test_unreadable_fixture_becomes_durable_failed_event_and_does_not_block_queue(tmp_path):
    config = AoiConfig(tmp_path / "result", .35, .20, .45, .35, "mock", "wsl-jetson")
    requests = [{"schema_version": 1, "request_id": str(uuid4()), "run_id": str(uuid4()),
                 "job_id": str(uuid4()), "attempt": 1, "lot_id": "L1", "task_type": "aoi",
                 "fixture_name": name} for name in ("missing.png", "good.png")]
    with AoiRuntime(tmp_path / "aoi.sqlite", config) as runtime:
        for request in requests:
            runtime.accept(request)
        def capture(request):
            if request["fixture_name"] == "missing.png":
                raise ValueError("AOI fixture image cannot be read")
            return np.full((32, 32, 3), 128, dtype=np.uint8)
        failed = runtime.process_next(capture, MockModel(0, .97, (2, 2, 20, 20)),
                                      MockModel(1, 0, (4, 4, 16, 16)))
        assert failed["event_type"] == "aoi.inspection.failed"
        assert failed["payload"]["error_code"] == "image_unreadable"
        assert runtime.process_next(capture, MockModel(0, .97, (2, 2, 20, 20)),
                                    MockModel(1, 0, (4, 4, 16, 16)))["event_type"] == "aoi.inspection.completed"
        assert len(runtime.pending_events()) == 2
