"""Three test clients; this isn't the Unity application or the real Jetson."""
import argparse
import asyncio
from contextlib import AsyncExitStack
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).parent / ".deps"))
from websockets.asyncio.client import connect


async def run(url):
    tokens = json.loads(Path(__file__).with_name("server.local.json").read_text())["tokens"]
    async with AsyncExitStack() as stack:
        clients = {}
        for role in ("unity", "jetson", "tcad"):
            client = await stack.enter_async_context(connect(url, proxy=None, max_size=4_000_000))
            await client.send(json.dumps({"type": "hello", "role": role, "token": tokens[role]}))
            welcome = json.loads(await asyncio.wait_for(client.recv(), 3))
            assert welcome["type"] == "welcome", welcome
            clients[role] = client
        examples = [
            ("jetson", "unity", "inspection_result", {"result_id": "DEMO-RESULT-013", "product_id": "DEMO-MOSFET-013", "frame_id": "DEMO-FRAME-013", "label": "scratch", "confidence": .968, "captured_at_ms": int(time.time()*1000)}),
            ("tcad", "unity", "tcad_result", {"run_id": "DEMO-RUN-001", "status": "completed", "representation": "physical", "units": {"vth": "V"}, "metrics": {"vth": 2.258}, "data_source": "demo"}),
            ("unity", "tcad", "command", {"action": "RUN_TCAD", "run_id": "DEMO-RUN-002"})]
        for source, target, kind, payload in examples:
            message = {"version": 1, "message_id": str(uuid.uuid4()), "type": kind, "payload": payload, "target": target}
            await clients[source].send(json.dumps(message))
            received = json.loads(await asyncio.wait_for(clients[target].recv(), 3))
            ack = json.loads(await asyncio.wait_for(clients[source].recv(), 3))
            assert received["message_id"] == message["message_id"] and received["source"] == source
            assert ack.get("status") == "forwarded", ack
            print(f"PASS {source} -> {target}: {kind}")
    print("FAB_SOCKET_DEMO_OK (test clients only; real Unity/Jetson/TCAD not connected)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="ws://127.0.0.1:8765/fab")
    asyncio.run(run(parser.parse_args().url))
