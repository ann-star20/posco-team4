import copy
import json
from pathlib import Path

from process_analysis import from_result
from test_server import SocketTests


class AnalysisTests(SocketTests):
    def packet(self):
        folder = Path(__file__).parents[1] / "JetsonML"
        hp = json.loads((folder / "agent-high-precision-jetson-result.json").read_text(encoding="utf-8-sig"))
        basic = json.loads((folder / "agent_reference.json").read_text(encoding="utf-8"))
        import time
        case = next(item for item in hp["results"] if item["name"] == "oxide_plus15")
        base = next(item for item in basic["results"] if item["name"] == case["name"])
        payload = from_result(case, base, "TEST-RUN", "TEST-BASE", "TEST-MODEL", int(time.time() * 1000))
        return dict(version=1, message_id="analysis-1", type="process_analysis", payload=payload)

    async def test_analysis_delivery_and_permissions(self):
        unity, ai, aoi = await self.login("unity"), await self.login("process_ai"), await self.login("jetson")
        packet = self.packet()
        await ai.send(json.dumps(packet))
        event = await self.recv(unity)
        self.assertEqual(event["source"], "process_ai")
        self.assertEqual(event["payload"]["decision"], "ambiguous")
        self.assertFalse(event["payload"]["applied"])
        self.assertEqual((await self.recv(ai))["status"], "forwarded")
        await ai.send(json.dumps(packet))
        self.assertEqual((await self.recv(ai))["status"], "duplicate")
        await aoi.send(json.dumps(packet))
        self.assertEqual((await self.recv(aoi))["code"], "INVALID_MESSAGE")
        # AOI still operates simultaneously on its own role.
        await aoi.send(json.dumps(self.result()))
        self.assertEqual((await self.recv(unity))["type"], "inspection_result")
        await self.recv(aoi)

    async def test_analysis_rejects_unsafe_claims(self):
        unity, ai = await self.login("unity"), await self.login("process_ai")
        for change in (dict(applied=True), dict(tcad_status="passed"), dict(dose_factor=2),
                       dict(top_probability=float("nan")), dict(decided=True), dict(data_source="real"),
                       dict(basic_candidates=[]), dict(sent_at_ms=1)):
            packet = copy.deepcopy(self.packet())
            packet["payload"].update(change)
            await ai.send(json.dumps(packet))
            self.assertEqual((await self.recv(ai))["code"], "INVALID_MESSAGE")


if __name__ == "__main__":
    import unittest
    unittest.main(verbosity=2)
