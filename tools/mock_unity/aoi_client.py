"""One-shot mock Unity client for the direct Jetson AOI WebSocket."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import time
from uuid import uuid4

from websockets.sync.client import connect


def receive_once(url: str, token: str, fixture: str, output_dir: Path,
                 timeout: float = 30, max_image_bytes: int = 8 * 1024 * 1024) -> tuple[dict, Path]:
    request = {
        "type": "aoi.inspection.requested",
        "schema_version": 1,
        "request_id": str(uuid4()),
        "job_id": str(uuid4()),
        "run_id": str(uuid4()),
        "lot_id": "UNITY-DIRECT-TEST",
        "unit_id": "MOSFET-TEST-1",
        "attempt": 1,
        "fixture_name": fixture,
        "api_token": token,
    }
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            with connect(url, open_timeout=3, max_size=max_image_bytes) as websocket:
                websocket.send(json.dumps(request))
                metadata = json.loads(websocket.recv(timeout=timeout))
                if metadata.get("type") != "aoi.inspection.completed":
                    raise RuntimeError("AOI server rejected the request")
                image = websocket.recv(timeout=timeout)
                if not isinstance(image, bytes):
                    raise RuntimeError("annotated image binary frame is missing")
                if len(image) != metadata["image"]["byte_length"]:
                    raise RuntimeError("annotated image length mismatch")
                if sha256(image).hexdigest() != metadata["image"]["sha256"]:
                    raise RuntimeError("annotated image checksum mismatch")
                output_dir.mkdir(parents=True, exist_ok=True)
                path = output_dir / f"unity_{metadata['job_id']}.jpg"
                path.write_bytes(image)
                (output_dir / f"unity_{metadata['job_id']}.json").write_text(
                    json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
                return metadata, path
        except OSError as exc:
            last_error = exc
            time.sleep(.25)
    raise TimeoutError("AOI Unity WebSocket connection timeout") from last_error


def main() -> None:
    parser = argparse.ArgumentParser(description="Unity 역할 AOI WebSocket 수신 시험")
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", default="")
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--max-image-bytes", type=int, default=8 * 1024 * 1024)
    args = parser.parse_args()
    metadata, path = receive_once(args.url, args.token, args.fixture,
                                  args.output_dir, args.timeout, args.max_image_bytes)
    print(json.dumps({"status": "passed", "verdict": metadata["verdict"],
                      "parts": len(metadata["parts"]),
                      "defects": len(metadata["defects"]),
                      "annotated_image": str(path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
