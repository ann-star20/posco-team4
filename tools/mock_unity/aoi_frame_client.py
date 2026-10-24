"""Unity-compatible frame-specific AOI request client."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from websockets.sync.client import connect


def inspect_frame(url: str, token: str, camera_id: str, frame_id: int,
                  timeout: float = 60, connector=connect) -> tuple[dict, dict, bytes]:
    request = {
        "type": "aoi.inspection.requested", "schema_version": 1,
        "request_id": str(uuid4()), "job_id": str(uuid4()), "run_id": str(uuid4()),
        "lot_id": "UNITY-CAMERA-TEST", "unit_id": "MOSFET-TEST-1", "attempt": 1,
        "camera_id": camera_id, "frame_id": frame_id, "api_token": token,
    }
    with connector(url, open_timeout=3, max_size=8 * 1024 * 1024) as websocket:
        websocket.send(json.dumps(request))
        accepted = json.loads(websocket.recv(timeout=timeout))
        if accepted.get("type") != "aoi.inspection.accepted":
            raise RuntimeError("AOI request rejected: " + str(accepted.get("error_code")))
        completed = json.loads(websocket.recv(timeout=timeout))
        if completed.get("type") != "aoi.inspection.completed":
            raise RuntimeError("AOI inference failed: " + str(completed.get("error_code")))
        image = websocket.recv(timeout=timeout)
        if not isinstance(image, bytes) or len(image) != int(completed["image"]["byte_length"]):
            raise RuntimeError("AOI annotated image length mismatch")
        expected_hash = completed["image"].get("sha256")
        if expected_hash and sha256(image).hexdigest() != expected_hash:
            raise RuntimeError("AOI annotated image checksum mismatch")
        return accepted, completed, image


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview frame_id 기반 AOI 검사")
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--camera-id", default="aoi-camera-1")
    parser.add_argument("--frame-id", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    accepted, completed, image = inspect_frame(
        args.url, args.token, args.camera_id, args.frame_id, args.timeout
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    image_path = args.output_dir / f"aoi_{completed['job_id']}.jpg"
    json_path = args.output_dir / f"aoi_{completed['job_id']}.json"
    image_path.write_bytes(image)
    json_path.write_text(json.dumps(completed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": "completed", "job_id": completed["job_id"],
        "frame_id": accepted["frame_id"], "verdict": completed["verdict"],
        "annotated_image": str(image_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
