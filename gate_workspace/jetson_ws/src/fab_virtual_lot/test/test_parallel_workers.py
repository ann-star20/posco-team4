from datetime import datetime, timezone
from threading import Event, Lock
import time
from uuid import uuid4

import numpy as np

from fab_virtual_lot.aoi_dispatcher import AoiDispatcher
from fab_virtual_lot.camera_buffer import CameraFrame
from fab_virtual_lot.surrogate_worker import SingleFlightExecutor, SurrogateRuntime


def wait_until(predicate, timeout=2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("condition was not reached")


def request():
    return {
        "request_id": str(uuid4()), "job_id": str(uuid4()), "run_id": str(uuid4()),
        "attempt": 1, "camera_id": "camera-1", "frame_id": 1,
    }


def frame():
    return CameraFrame(1, "camera-1", datetime.now(timezone.utc), time.monotonic_ns(),
                       np.zeros((8, 8, 3), dtype=np.uint8))


def test_surrogate_completes_while_aoi_gpu_job_is_blocked(tmp_path):
    aoi_started = Event()
    release_aoi = Event()
    surrogate_completed = Event()

    def slow_aoi(_request, _image):
        aoi_started.set()
        release_aoi.wait(2)
        return {"verdict": "pass"}

    dispatcher = AoiDispatcher(tmp_path / "aoi.sqlite", tmp_path / "spool", slow_aoi)
    body = request()
    dispatcher.submit(body, frame())
    assert aoi_started.wait(1)

    runner = SingleFlightExecutor("surrogate-cpu")
    assert runner.submit(lambda: surrogate_completed.set()) is True
    assert surrogate_completed.wait(1)
    assert dispatcher.get(body["job_id"]).status == "running"

    release_aoi.set()
    wait_until(lambda: dispatcher.get(body["job_id"]).status == "succeeded")
    runner.close()
    dispatcher.close()


def test_single_flight_rejects_overlap_without_blocking_caller():
    started = Event()
    release = Event()
    errors = []
    runner = SingleFlightExecutor("surrogate-cpu", on_error=errors.append)

    def blocking():
        started.set()
        release.wait(1)

    before = time.perf_counter()
    assert runner.submit(blocking) is True
    assert time.perf_counter() - before < .1
    assert started.wait(1)
    assert runner.submit(lambda: None) is False
    release.set()
    wait_until(lambda: runner.busy is False)
    assert runner.submit(lambda: (_ for _ in ()).throw(ValueError("bad"))) is True
    wait_until(lambda: len(errors) == 1)
    runner.close()

    assert isinstance(errors[0], ValueError)


def test_surrogate_runtime_accepts_next_request_while_inference_is_blocked(tmp_path):
    runtime = SurrogateRuntime(tmp_path / "surrogate.sqlite")
    first = {**request(), "task_type": "surrogate"}
    second = {**request(), "task_type": "surrogate"}
    started = Event()
    release = Event()
    errors = []

    def infer(body):
        started.set()
        release.wait(1)
        return {"status": "succeeded", "job_id": body["job_id"]}

    runtime.accept(first)
    runner = SingleFlightExecutor("surrogate-cpu", on_error=errors.append)
    assert runner.submit(lambda: runtime.process_next(infer))
    assert started.wait(1)

    before = time.perf_counter()
    runtime.accept(second)
    assert time.perf_counter() - before < .1
    release.set()
    wait_until(lambda: runtime.db.execute(
        "SELECT status FROM ml_inbox WHERE job_id=?", (first["job_id"],)
    ).fetchone()[0] == "completed")
    runner.close()
    runtime.close()

    assert errors == []
