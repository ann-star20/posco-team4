"""Console-only Unity contract client; writes cursor after processing."""

import json
import os
from pathlib import Path
import time
from urllib.parse import urlencode
from uuid import UUID

from websockets.sync.client import connect


class MockUnity:
    def __init__(self, run_id: UUID, cursor_path: Path):
        self.run_id = run_id
        self.cursor_path = cursor_path

    def cursor(self) -> int:
        if not self.cursor_path.exists():
            return 0
        return int(self.cursor_path.read_text(encoding="utf-8"))

    def handle(self, event: dict) -> None:
        if UUID(event["run_id"]) != self.run_id:
            raise ValueError("wrong run_id")
        sequence = int(event["sequence"])
        if sequence <= self.cursor():
            return
        print(json.dumps(event, ensure_ascii=False))
        self.cursor_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cursor_path.with_suffix(".tmp")
        temporary.write_text(str(sequence), encoding="utf-8")
        temporary.replace(self.cursor_path)

    def connect(self, base_url: str) -> None:
        while True:
            query = urlencode({"run_id": str(self.run_id),
                               "after_sequence": self.cursor()})
            try:
                with connect(f"{base_url}?{query}") as socket:
                    for raw in socket:
                        self.handle(json.loads(raw))
            except (OSError, TimeoutError):
                time.sleep(1)


def main() -> None:
    run_id = UUID(os.environ["FAB_RUN_ID"])
    base_url = os.environ.get("UNITY_GATEWAY_WS_URL",
                              "ws://127.0.0.1:8000/api/v1/stream")
    MockUnity(run_id, Path("data/mock-unity-cursor.txt")).connect(base_url)


if __name__ == "__main__":
    main()
