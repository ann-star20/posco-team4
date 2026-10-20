"""Receive a Preview frame and immediately request AOI for that exact frame."""

import argparse
import json
from pathlib import Path

from tools.mock_unity.aoi_frame_client import inspect_frame
from tools.mock_unity.camera_preview_client import receive_preview


def inspect_latest_preview(
    preview_url: str,
    preview_token: str,
    aoi_url: str,
    aoi_token: str,
    camera_id: str,
    timeout: float = 180,
    preview_receiver=receive_preview,
    frame_inspector=inspect_frame,
):
    preview, preview_image = preview_receiver(
        preview_url, preview_token, camera_id, timeout=min(timeout, 30)
    )
    frame_id = int(preview["frame_id"])
    accepted, completed, annotated = frame_inspector(
        aoi_url, aoi_token, camera_id, frame_id, timeout=timeout
    )
    return preview, accepted, completed, preview_image, annotated


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview 최신 frame을 즉시 AOI 검사하는 통합 시험"
    )
    parser.add_argument("--preview-url", required=True)
    parser.add_argument("--preview-token", required=True)
    parser.add_argument("--aoi-url", required=True)
    parser.add_argument("--aoi-token", required=True)
    parser.add_argument("--camera-id", default="aoi-camera-1")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()

    preview, accepted, completed, preview_image, annotated = inspect_latest_preview(
        args.preview_url, args.preview_token, args.aoi_url, args.aoi_token,
        args.camera_id, args.timeout,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame_id = preview["frame_id"]
    preview_path = args.output_dir / f"preview_{frame_id}.jpg"
    result_path = args.output_dir / f"aoi_{completed['job_id']}.jpg"
    metadata_path = args.output_dir / f"aoi_{completed['job_id']}.json"
    preview_path.write_bytes(preview_image)
    result_path.write_bytes(annotated)
    metadata_path.write_text(
        json.dumps(completed, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({
        "status": "completed", "frame_id": accepted["frame_id"],
        "job_id": completed["job_id"], "verdict": completed["verdict"],
        "preview_image": str(preview_path), "annotated_image": str(result_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
