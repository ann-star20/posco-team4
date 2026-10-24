import asyncio
import json
import secrets
import time
import unittest
from contextlib import AsyncExitStack

from server import Relay, serve, ROLES
from websockets.asyncio.client import connect


class SocketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tokens = {role: secrets.token_urlsafe(32) for role in ROLES}
        self.relay = Relay(self.tokens)
        self.server = await serve(self.relay.handler, "127.0.0.1", 0, origins=[None], max_size=4_000_000, compression=None)
        self.url = f"ws://127.0.0.1:{self.server.sockets[0].getsockname()[1]}/fab"
        self.stack = AsyncExitStack()

    async def asyncTearDown(self):
        await self.stack.aclose()
        self.server.close()
        await self.server.wait_closed()

    async def login(self, role):
        client = await self.stack.enter_async_context(connect(self.url, proxy=None))
        await client.send(json.dumps({"type": "hello", "role": role, "token": self.tokens[role]}))
        self.assertEqual((await self.recv(client))["type"], "welcome")
        return client

    async def recv(self, client):
        return json.loads(await asyncio.wait_for(client.recv(), 2))

    def result(self, label="scratch", mid="test-1"):
        return {"version": 1, "message_id": mid, "type": "inspection_result", "source": "forged",
                "payload": {"result_id": mid, "product_id": "PRODUCT-001", "frame_id": "FRAME-001", "label": label,
                            "confidence": .96, "captured_at_ms": int(time.time()*1000)}}

    async def test_aoi_delivery_dedup_and_identity(self):
        unity, jetson = await self.login("unity"), await self.login("jetson")
        packet = self.result()
        await jetson.send(json.dumps(packet))
        event = await self.recv(unity)
        self.assertEqual(event["source"], "jetson")
        self.assertEqual(event["payload"]["label"], "scratch")
        self.assertEqual((await self.recv(jetson))["status"], "forwarded")
        await jetson.send(json.dumps(packet))
        self.assertEqual((await self.recv(jetson))["status"], "duplicate")
        packet["payload"]["label"] = "normal"
        await jetson.send(json.dumps(packet))
        self.assertEqual((await self.recv(jetson))["code"], "INVALID_MESSAGE")
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(unity.recv(), .08)

    async def test_tcad_and_command(self):
        unity, tcad = await self.login("unity"), await self.login("tcad")
        packet = {"version": 1, "message_id": "run-1", "type": "tcad_result", "payload": {"run_id": "RUN-1", "status": "completed", "representation": "normalized_ratio", "baseline_version": "demo-v1", "metrics": {"vth": 1.02}}}
        await tcad.send(json.dumps(packet))
        self.assertEqual((await self.recv(unity))["payload"]["metrics"]["vth"], 1.02)
        await self.recv(tcad)
        packet = {"version": 1, "message_id": "cmd-1", "type": "command", "target": "tcad", "payload": {"action": "RUN_TCAD", "run_id": "RUN-2"}}
        await unity.send(json.dumps(packet))
        self.assertEqual((await self.recv(tcad))["payload"]["action"], "RUN_TCAD")
        self.assertEqual((await self.recv(unity))["status"], "forwarded")

    async def test_invalid_inputs_and_permissions(self):
        unity, jetson = await self.login("unity"), await self.login("jetson")
        for raw in ("{", "[]", b"binary", '{"version":1,"payload":{"n":1e999}}'):
            await jetson.send(raw)
            self.assertEqual((await self.recv(jetson))["code"], "INVALID_MESSAGE")
        for label, confidence, stamp in (("unknown", .9, int(time.time()*1000)), ("normal", 1.5, int(time.time()*1000)), ("normal", .9, 1)):
            packet = self.result()
            packet["payload"].update(label=label, confidence=confidence, captured_at_ms=stamp)
            await jetson.send(json.dumps(packet))
            self.assertEqual((await self.recv(jetson))["code"], "INVALID_MESSAGE")
        await unity.send(json.dumps(self.result()))
        self.assertEqual((await self.recv(unity))["code"], "INVALID_MESSAGE")

    async def test_auth_and_offline(self):
        client = await self.stack.enter_async_context(connect(self.url, proxy=None))
        await client.send(json.dumps({"type": "hello", "role": "unity", "token": "wrong"}))
        self.assertEqual((await self.recv(client))["code"], "AUTH_FAILED")
        jetson = await self.login("jetson")
        packet = self.result()
        await jetson.send(json.dumps(packet))
        self.assertEqual((await self.recv(jetson))["code"], "TARGET_OFFLINE")
        unity = await self.login("unity")
        await jetson.send(json.dumps(packet))
        self.assertEqual((await self.recv(unity))["message_id"], "test-1")
        self.assertEqual((await self.recv(jetson))["status"], "forwarded")


if __name__ == "__main__":
    unittest.main(verbosity=2)
