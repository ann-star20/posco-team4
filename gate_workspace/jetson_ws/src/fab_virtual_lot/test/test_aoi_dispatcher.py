from datetime import datetime, timezone
from hashlib import sha256
import json
from threading import Event, Lock
import time
from uuid import uuid4

import cv2
import numpy as np
import pytest

from fab_virtual_lot.aoi_dispatcher import AoiDispatcher, AoiQueueFull
from fab_virtual_lot.camera_buffer import CameraFrame


def request(job_id=None, marker="same"):
    return {
        "type": "aoi.inspection.requested", "schema_version": 1,
        "request_id": str(uuid4()), "job_id": str(job_id or uuid4()),
        "run_id": str(uuid4()), "lot_id": "LOT-1", "unit_id": marker,
        "attempt": 1, "camera_id": "camera-1", "frame_id": 7,
    }


def frame(value=77):
    return CameraFrame(7, "camera-1", datetime.now(timezone.utc), 1,
                       np.full((12, 16, 3), value, dtype=np.uint8))


def wait_until(predicate, timeout=2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(.005)
    raise AssertionError("condition was not reached")


def test_submit_atomically_pins_frame_and_request_before_accept(tmp_path):
    dispatcher = AoiDispatcher(tmp_path / "jobs.sqlite", tmp_path / "spool",
                               lambda req, image: {"verdict": "pass"}, autostart=False)
    body = request()
    accepted = dispatcher.submit(body, frame())
    record = dispatcher.get(body["job_id"])
    dispatcher.close()

    pinned = tmp_path / "spool" / f"{body['job_id']}.png"
    assert accepted.status == "queued"
    assert accepted.frame_id == 7
    assert pinned.is_file()
    assert record.request == body
    assert record.frame_path == pinned
    assert record.frame_sha256 == sha256(pinned.read_bytes()).hexdigest()
    assert cv2.imread(str(pinned)).shape == (12, 16, 3)


def test_duplicate_same_body_is_idempotent_and_conflict_is_rejected(tmp_path):
    dispatcher = AoiDispatcher(tmp_path / "jobs.sqlite", tmp_path / "spool",
                               lambda req, image: {"verdict": "pass"}, autostart=False)
    body = request()
    first = dispatcher.submit(body, frame())
    second = dispatcher.submit(dict(body), frame())
    changed = dict(body, unit_id="DIFFERENT")

    assert second == first
    with pytest.raises(ValueError, match="content conflict"):
        dispatcher.submit(changed, frame())
    dispatcher.close()


def test_queue_capacity_rejects_without_writing_second_frame(tmp_path):
    dispatcher = AoiDispatcher(tmp_path / "jobs.sqlite", tmp_path / "spool",
                               lambda req, image: {"verdict": "pass"},
                               queue_size=1, autostart=False)
    first = request()
    second = request()
    dispatcher.submit(first, frame())
    with pytest.raises(AoiQueueFull):
        dispatcher.submit(second, frame(88))
    assert not (tmp_path / "spool" / f"{second['job_id']}.png").exists()
    dispatcher.close()


def test_recover_runs_same_pinned_frame_after_restart(tmp_path):
    db = tmp_path / "jobs.sqlite"
    spool = tmp_path / "spool"
    body = request()
    first = AoiDispatcher(db, spool, lambda req, image: {}, autostart=False)
    first.submit(body, frame(61))
    first.close()

    observed = []
    second = AoiDispatcher(db, spool,
                           lambda req, image: observed.append(int(image[0, 0, 0])) or
                           {"verdict": "pass"}, autostart=False)
    completed = []
    second.subscribe(body["job_id"], completed.append)
    second.recover()
    wait_until(lambda: second.get(body["job_id"]).status == "succeeded")
    second.close()

    assert observed == [61]
    assert completed[0].result == {"verdict": "pass"}


def test_executor_runs_aoi_jobs_one_at_a_time(tmp_path):
    active = 0
    maximum = 0
    lock = Lock()
    first_started = Event()
    release_first = Event()

    def infer(req, image):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        if not first_started.is_set():
            first_started.set()
            release_first.wait(1)
        with lock:
            active -= 1
        return {"job_id": req["job_id"], "value": int(image[0, 0, 0])}

    dispatcher = AoiDispatcher(tmp_path / "jobs.sqlite", tmp_path / "spool", infer,
                               workers=1, queue_size=2)
    one, two = request(), request()
    dispatcher.submit(one, frame(1))
    assert first_started.wait(1)
    dispatcher.submit(two, frame(2))
    release_first.set()
    wait_until(lambda: dispatcher.get(two["job_id"]).status == "succeeded")
    dispatcher.close()

    assert maximum == 1
    assert json.loads(dispatcher_result(tmp_path / "jobs.sqlite", two["job_id"]))["value"] == 2


def dispatcher_result(path, job_id):
    import sqlite3
    with sqlite3.connect(path) as db:
        return db.execute("SELECT result_json FROM camera_aoi_jobs WHERE job_id=?",
                          (job_id,)).fetchone()[0]
