"""One-frame Unity-compatible client for the Jetson camera Preview socket."""

import argparse
import json
from pathlib import Path

from websockets.sync.client import connect


def receive_preview(url: str, token: str, camera_id: str, timeout: float = 10,
                    connector=connect) -> tuple[dict, bytes]:
    with connector(url, open_timeout=3, max_size=8 * 1024 * 1024) as websocket:
        websocket.send(json.dumps({
            "type": "camera.preview.subscribe", "schema_version": 1,
            "camera_id": camera_id, "api_token": token,
            "preferred_width": 1280, "preferred_height": 720, "preferred_fps": 5,
        }))
        subscribed = json.loads(websocket.recv(timeout=timeout))
        if subscribed.get("type") != "camera.preview.subscribed":
            raise RuntimeError("camera Preview subscription was rejected")
        metadata = json.loads(websocket.recv(timeout=timeout))
        if metadata.get("type") != "camera.preview.frame":
            raise RuntimeError("camera Preview metadata is missing")
        image = websocket.recv(timeout=timeout)
        if not isinstance(image, bytes) or len(image) != int(metadata["byte_length"]):
            raise RuntimeError("camera Preview binary length mismatch")
        return metadata, image


def main() -> None:
    parser = argparse.ArgumentParser(description="Jetson 카메라 Preview 1프레임 확인")
    parser.add_argument("--url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--camera-id", default="aoi-camera-1")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args()
    metadata, image = receive_preview(args.url, args.token, args.camera_id, args.timeout)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(image)
    print(json.dumps({
        "status": "received", "camera_id": metadata["camera_id"],
        "frame_id": metadata["frame_id"], "width": metadata["width"],
        "height": metadata["height"], "output": str(args.output or ""),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
