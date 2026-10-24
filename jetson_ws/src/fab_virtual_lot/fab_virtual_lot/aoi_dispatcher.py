"""Durable, bounded, single-GPU AOI job dispatch."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
from threading import RLock
from typing import Callable
from uuid import UUID, uuid4

import cv2
import numpy as np

from .camera_buffer import CameraFrame


class AoiQueueFull(RuntimeError):
    pass


@dataclass(frozen=True)
class AoiAccepted:
    job_id: str
    request_id: str
    frame_id: int
    status: str
    frame_path: Path
    frame_sha256: str


@dataclass(frozen=True)
class AoiCompletion:
    job_id: str
    status: str
    result: dict | None
    error_code: str | None


@dataclass(frozen=True)
class AoiJobRecord:
    job_id: str
    request: dict
    frame_id: int
    frame_path: Path
    frame_sha256: str
    status: str
    result: dict | None
    error_code: str | None


class AoiDispatcher:
    def __init__(
        self,
        database_path: Path,
        spool_dir: Path,
        infer: Callable[[dict, np.ndarray], dict],
        queue_size: int = 10,
        workers: int = 1,
        autostart: bool = True,
    ) -> None:
        if queue_size < 1:
            raise ValueError("AOI queue_size must be positive")
        if workers != 1:
            raise ValueError("AOI executor workers must be 1")
        database_path = Path(database_path)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.spool_dir = Path(spool_dir)
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        self.infer = infer
        self.queue_size = queue_size
        self._lock = RLock()
        self._db = sqlite3.connect(database_path, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS camera_aoi_jobs(
                job_id TEXT PRIMARY KEY,
                request_json TEXT NOT NULL,
                frame_id INTEGER NOT NULL,
                frame_path TEXT NOT NULL,
                frame_sha256 TEXT NOT NULL,
                status TEXT NOT NULL,
                result_json TEXT,
                error_code TEXT
            )
        """)
        self._db.commit()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aoi-gpu")
        self._callbacks: dict[str, list[Callable[[AoiCompletion], None]]] = {}
        self._scheduled: set[str] = set()
        self._autostart = autostart
        self._closed = False

    def submit(self, request: dict, frame: CameraFrame) -> AoiAccepted:
        job_id = str(request["job_id"])
        request_id = str(request["request_id"])
        UUID(job_id)
        UUID(request_id)
        body = json.dumps(request, sort_keys=True, separators=(",", ":"))
        with self._lock:
            self._ensure_open()
            existing = self._db.execute(
                "SELECT request_json FROM camera_aoi_jobs WHERE job_id=?", (job_id,)
            ).fetchone()
            if existing:
                if existing[0] != body:
                    raise ValueError("AOI job content conflict")
                return self._accepted(self._get_locked(job_id))
            count = self._db.execute(
                "SELECT COUNT(*) FROM camera_aoi_jobs WHERE status IN ('queued','running')"
            ).fetchone()[0]
            if count >= self.queue_size:
                raise AoiQueueFull("AOI queue is full")

            path, digest = self._pin_frame(job_id, frame.image)
            try:
                with self._db:
                    self._db.execute(
                        "INSERT INTO camera_aoi_jobs"
                        "(job_id,request_json,frame_id,frame_path,frame_sha256,status) "
                        "VALUES (?,?,?,?,?,'queued')",
                        (job_id, body, frame.frame_id, str(path), digest),
                    )
            except Exception:
                path.unlink(missing_ok=True)
                raise
            record = self._get_locked(job_id)
            if self._autostart:
                self._schedule_locked(job_id)
            return self._accepted(record)

    def subscribe(self, job_id: str, callback: Callable[[AoiCompletion], None]) -> None:
        immediate = None
        with self._lock:
            record = self._get_locked(job_id)
            if record.status in {"succeeded", "failed"}:
                immediate = self._completion(record)
            else:
                self._callbacks.setdefault(job_id, []).append(callback)
        if immediate is not None:
            callback(immediate)

    def recover(self) -> None:
        with self._lock:
            self._ensure_open()
            with self._db:
                self._db.execute("UPDATE camera_aoi_jobs SET status='queued' WHERE status='running'")
            rows = self._db.execute(
                "SELECT job_id FROM camera_aoi_jobs WHERE status='queued' ORDER BY rowid"
            ).fetchall()
            self._autostart = True
            for (job_id,) in rows:
                self._schedule_locked(job_id)

    def get(self, job_id: str) -> AoiJobRecord:
        with self._lock:
            return self._get_locked(job_id)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._executor.shutdown(wait=True, cancel_futures=False)
        with self._lock:
            self._db.close()

    def _schedule_locked(self, job_id: str) -> None:
        if job_id in self._scheduled:
            return
        self._scheduled.add(job_id)
        self._executor.submit(self._run_job, job_id)

    def _run_job(self, job_id: str) -> None:
        callbacks = []
        try:
            with self._lock:
                if self._closed:
                    return
                record = self._get_locked(job_id)
                with self._db:
                    self._db.execute(
                        "UPDATE camera_aoi_jobs SET status='running', error_code=NULL WHERE job_id=?",
                        (job_id,),
                    )
            image = cv2.imread(str(record.frame_path), cv2.IMREAD_COLOR)
            if image is None:
                raise OSError("pinned AOI frame cannot be read")
            result = self.infer(record.request, image)
            result_json = json.dumps(result, sort_keys=True, separators=(",", ":"))
            with self._lock:
                with self._db:
                    self._db.execute(
                        "UPDATE camera_aoi_jobs SET status='succeeded',result_json=?,error_code=NULL "
                        "WHERE job_id=?", (result_json, job_id)
                    )
                completed = self._get_locked(job_id)
                callbacks = self._callbacks.pop(job_id, [])
        except Exception:
            with self._lock:
                if not self._closed:
                    with self._db:
                        self._db.execute(
                            "UPDATE camera_aoi_jobs SET status='failed',error_code='inference_failed' "
                            "WHERE job_id=?", (job_id,)
                        )
                    completed = self._get_locked(job_id)
                    callbacks = self._callbacks.pop(job_id, [])
                else:
                    return
        finally:
            with self._lock:
                self._scheduled.discard(job_id)
        completion = self._completion(completed)
        for callback in callbacks:
            try:
                callback(completion)
            except Exception:
                continue

    def _pin_frame(self, job_id: str, image: np.ndarray) -> tuple[Path, str]:
        okay, encoded = cv2.imencode(".png", image)
        if not okay:
            raise OSError("AOI frame encoding failed")
        data = encoded.tobytes()
        path = self.spool_dir / f"{job_id}.png"
        temp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        try:
            with temp.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
        return path, sha256(data).hexdigest()

    def _get_locked(self, job_id: str) -> AoiJobRecord:
        row = self._db.execute(
            "SELECT job_id,request_json,frame_id,frame_path,frame_sha256,status,result_json,error_code "
            "FROM camera_aoi_jobs WHERE job_id=?", (job_id,)
        ).fetchone()
        if row is None:
            raise KeyError(job_id)
        return AoiJobRecord(
            job_id=row[0], request=json.loads(row[1]), frame_id=int(row[2]),
            frame_path=Path(row[3]), frame_sha256=row[4], status=row[5],
            result=json.loads(row[6]) if row[6] else None, error_code=row[7],
        )

    @staticmethod
    def _accepted(record: AoiJobRecord) -> AoiAccepted:
        return AoiAccepted(record.job_id, record.request["request_id"], record.frame_id,
                           record.status, record.frame_path, record.frame_sha256)

    @staticmethod
    def _completion(record: AoiJobRecord) -> AoiCompletion:
        return AoiCompletion(record.job_id, record.status, record.result, record.error_code)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("AOI dispatcher is closed")
