import json
from hashlib import sha256
from pathlib import Path
from threading import Thread
from uuid import uuid4

import cv2
import numpy as np
from websockets.sync.client import connect
from websockets.sync.server import serve

from fab_virtual_lot.aoi_pipeline import AoiConfig, MockModel
from fab_virtual_lot.aoi_unity import (
    AoiUnityOutbox,
    AoiUnityService,
    build_unity_result,
    websocket_max_bytes,
)


class FakeSocket:
    def __init__(self, request):
        self.request = request
        self.sent = []

    def __iter__(self):
        yield json.dumps(self.request)

    def send(self, value):
        self.sent.append(value)


def request_message(image_name="fixture.jpg"):
    return {
        "type": "aoi.inspection.requested",
        "schema_version": 1,
        "request_id": str(uuid4()),
        "job_id": str(uuid4()),
        "run_id": str(uuid4()),
        "lot_id": "LOT-UNITY-1",
        "unit_id": "MOSFET-1",
        "attempt": 1,
        "fixture_name": image_name,
    }


def test_websocket_image_limit_is_bounded_and_configurable():
    assert websocket_max_bytes({}) == 8 * 1024 * 1024
    assert websocket_max_bytes({"AOI_UNITY_MAX_IMAGE_BYTES": "2097152"}) == 2 * 1024 * 1024
    try:
        websocket_max_bytes({"AOI_UNITY_MAX_IMAGE_BYTES": "999999"})
    except ValueError:
        pass
    else:
        raise AssertionError("limits below 1 MiB must be rejected")


def test_unity_message_separates_part_defect_and_pairs_annotated_jpeg(tmp_path):
    image = np.full((120, 160, 3), 180, dtype=np.uint8)
    config = AoiConfig(tmp_path, .35, .20, .45, .35, "mock", "wsl-jetson")
    request = request_message()
    persisted = []
    service = AoiUnityService(
        config,
        lambda _: image,
        MockModel(2, .97, (20, 30, 100, 90)),
        MockModel(0, .92, (40, 50, 130, 105)),
        event_sink=persisted.append,
    )

    result, jpeg = service.inspect(request)

    assert result["type"] == "aoi.inspection.completed"
    assert result["verdict"] == "fail"
    assert result["parts"] == [{
        "class_id": 2, "class_name": "tab", "confidence": .97,
        "bbox_xyxy": [20.0, 30.0, 100.0, 90.0],
    }]
    assert result["defects"] == [{
        "class_id": 0, "class_name": "crash", "confidence": .92,
        "bbox_xyxy": [40.0, 50.0, 130.0, 105.0],
    }]
    assert result["image"]["frame_role"] == "annotated"
    assert result["image"]["mime_type"] == "image/jpeg"
    assert result["image"]["binary_frame_follows"] is True
    assert result["image"]["byte_length"] == len(jpeg)
    assert result["image"]["sha256"] == sha256(jpeg).hexdigest()
    assert result["persistence_status"] == "queued"
    assert len(persisted) == 1
    assert persisted[0]["event_id"] == result["message_id"]
    assert persisted[0]["event_type"] == "aoi.inspection.completed"
    assert persisted[0]["source"] == "jetson.aoi"
    assert persisted[0]["run_id"] == request["run_id"]
    assert persisted[0]["correlation_id"] == request["request_id"]
    assert persisted[0]["payload"]["images"]["annotated"]["sha256"] == result["image"]["sha256"]
    decoded = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
    assert decoded.shape[:2] == (120, 160)
    # part rectangle is blue/orange-ish in BGR; defect rectangle is red.
    assert int(decoded[30, 20, 0]) > int(decoded[30, 20, 2])
    assert int(decoded[50, 40, 2]) > int(decoded[50, 40, 0])


def test_direct_aoi_outbox_waits_for_gateway_commit_ack(tmp_path):
    store = AoiUnityOutbox(tmp_path / "direct-aoi.sqlite")
    event_id, run_id = uuid4(), uuid4()
    event = {
        "schema_version": 1,
        "event_id": str(event_id),
        "run_id": str(run_id),
        "event_type": "aoi.inspection.completed",
        "source": "jetson.aoi",
        "severity": "warning",
        "payload": {"job_id": str(uuid4())},
        "occurred_at": "2026-10-19T00:00:00+00:00",
    }

    store.enqueue(event)

    assert [json.loads(body) for body in store.pending_bodies()] == [event]
    assert store.receive_ack(json.dumps({
        "event_id": str(event_id), "run_id": str(run_id),
        "sequence": 17, "status": "committed",
    })) is True
    assert store.pending_bodies() == []


def test_websocket_sends_json_then_annotated_binary(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    cv2.imwrite(str(images / "fixture.jpg"), np.full((80, 100, 3), 150, dtype=np.uint8))
    config = AoiConfig(tmp_path / "result", .35, .20, .45, .35, "mock", "wsl-jetson")
    service = AoiUnityService(
        config,
        lambda req: cv2.imread(str(images / req["fixture_name"])),
        MockModel(0, .97, (5, 10, 70, 60)),
        MockModel(1, .92, (15, 20, 80, 70)),
    )
    socket = FakeSocket(request_message())

    service.handle(socket)

    assert len(socket.sent) == 2
    metadata = json.loads(socket.sent[0])
    assert metadata["image"]["file_name"] == "annotated.jpg"
    assert isinstance(socket.sent[1], bytes)
    assert sha256(socket.sent[1]).hexdigest() == metadata["image"]["sha256"]


def test_build_result_rejects_missing_or_modified_annotated_file(tmp_path):
    event = {"event_id": str(uuid4()), "run_id": str(uuid4()), "payload": {
        "job_id": str(uuid4()), "request_id": str(uuid4()), "lot_id": "L", "verdict": "pass",
        "device_id": "j", "result_origin": "mock", "thresholds": {}, "detections": [],
        "images": {"annotated": {"local_directory": str(tmp_path), "file_name": "missing.jpg",
                                   "sha256": "0" * 64, "byte_size": 0, "width": 10, "height": 10}},
    }}
    try:
        build_unity_result(event)
    except ValueError as exc:
        assert "annotated" in str(exc)
    else:
        raise AssertionError("missing annotated image must fail closed")


def test_real_websocket_round_trip_returns_metadata_and_jpeg(tmp_path):
    image = np.full((72, 96, 3), 160, dtype=np.uint8)
    config = AoiConfig(tmp_path / "result", .35, .20, .45, .35, "mock", "wsl-jetson")
    service = AoiUnityService(config, lambda _: image,
                              MockModel(1, .95, (4, 8, 50, 60)),
                              MockModel(1, .91, (12, 18, 70, 68)), token="test-token")
    with serve(service.handle, "127.0.0.1", 0) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.socket.getsockname()[1]
        request = request_message()
        request["api_token"] = "test-token"
        with connect(f"ws://127.0.0.1:{port}/aoi", open_timeout=3) as websocket:
            websocket.send(json.dumps(request))
            metadata = json.loads(websocket.recv(timeout=3))
            jpeg = websocket.recv(timeout=3)
        server.shutdown()
        thread.join(timeout=3)
    assert metadata["type"] == "aoi.inspection.completed"
    assert metadata["parts"][0]["class_name"] == "lead"
    assert metadata["defects"][0]["class_name"] == "bend"
    assert isinstance(jpeg, bytes)
    assert sha256(jpeg).hexdigest() == metadata["image"]["sha256"]
