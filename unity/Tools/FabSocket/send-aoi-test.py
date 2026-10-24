"""Publish one marked test result to an already-connected real Unity client."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent / ".deps"))
from websockets.asyncio.client import connect


async def main(args):
    config = json.loads(Path(__file__).with_name("server.local.json").read_text())
    async with connect(args.url, proxy=None) as socket:
        await socket.send(json.dumps({"type": "hello", "role": "jetson", "token": config["tokens"]["jetson"]}))
        welcome = json.loads(await asyncio.wait_for(socket.recv(), 3))
        if welcome.get("type") != "welcome":
            raise RuntimeError("Jetson test client could not authenticate; check active role connections")
        message_id = str(uuid.uuid4())
        packet = {"version": 1, "type": "inspection_result", "message_id": message_id,
                  "payload": {"result_id": message_id, "product_id": "WS-TEST-013", "frame_id": "WS-TEST-FRAME",
                              "label": args.label, "confidence": .968, "captured_at_ms": int(time.time()*1000), "data_source": "demo"}}
        await socket.send(json.dumps(packet))
        response = json.loads(await asyncio.wait_for(socket.recv(), 3))
        if response.get("status") != "forwarded":
            raise RuntimeError("Result not forwarded; ensure Unity is connected first")
        print("AOI_TEST_FORWARDED " + args.label + " (delivery to Unity socket; check Unity display separately)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8765/fab")
    parser.add_argument("--label", choices=["normal", "crash", "band", "scratch"], default="scratch")
    asyncio.run(main(parser.parse_args()))
