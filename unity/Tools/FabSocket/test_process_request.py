import copy
import json
import time
from pathlib import Path
from process_analysis import UNITS, validate_request
from test_process_analysis import AnalysisTests


def sample_request(name="oxide_plus15"):
    reference=json.loads((Path(__file__).parents[1]/"JetsonML/agent_reference.json").read_text(encoding="utf-8"))
    case=next(c for c in reference["cases"] if c["name"]==name)
    return dict(request_id="REQ-test", lot_id="LOT-TEST-1", baseline_version="tcad-gp-"+reference["hashes"]["최종ML/모델/gp.npz"][:12],
                data_source="synthetic", units=UNITS, n_wafers=case["n_wafers"], measurement=case["measurement"], sent_at_ms=int(time.time()*1000))


class RequestTests(AnalysisTests):
    async def test_request_running_result_and_aoi_independent(self):
        unity, worker, aoi=await self.login("unity"),await self.login("process_ai"),await self.login("jetson")
        p=sample_request()
        request=dict(version=1,type="process_request",message_id=p["request_id"],payload=p)
        await unity.send(json.dumps(request))
        event=await self.recv(worker)
        self.assertEqual(event["payload"],p)
        self.assertEqual(event["source"],"unity")
        self.assertEqual((await self.recv(unity))["status"],"forwarded")
        await worker.send(json.dumps(dict(version=1,type="process_status",message_id="s1",payload=dict(state="running",request_id=p["request_id"],lot_id=p["lot_id"],detail="running"))))
        self.assertEqual((await self.recv(unity))["payload"]["state"],"running")
        await self.recv(worker)
        result=self.packet()
        result["payload"].update(delivery="computed",request_id=p["request_id"],lot_id=p["lot_id"],baseline_version=p["baseline_version"],input=p)
        await worker.send(json.dumps(result))
        self.assertEqual((await self.recv(unity))["payload"]["input"],p)
        await self.recv(worker)
        await aoi.send(json.dumps(self.result()))
        self.assertEqual((await self.recv(unity))["type"],"inspection_result")
        await self.recv(aoi)
        await unity.send(json.dumps(request))
        self.assertEqual((await self.recv(unity))["status"],"duplicate")
        request["payload"]["measurement"]["vth"]+=.1
        await unity.send(json.dumps(request))
        self.assertEqual((await self.recv(unity))["code"],"INVALID_MESSAGE")

    async def test_request_validation_and_offline_error_identity(self):
        unity=await self.login("unity")
        p=sample_request()
        packet=dict(version=1,type="process_request",message_id=p["request_id"],payload=p)
        await unity.send(json.dumps(packet))
        error=await self.recv(unity)
        self.assertEqual(error["code"],"TARGET_OFFLINE")
        self.assertEqual(error["message_id"],p["request_id"])
        for change in (dict(n_wafers=0),dict(data_source="real"),dict(units={}),dict(sent_at_ms=1),dict(measurement=dict(vth=2,gm=-1,id4v=1e-6,bv=None))):
            bad=copy.deepcopy(p);bad.update(change)
            with self.assertRaises(ValueError):validate_request(bad)
        worker=await self.login("process_ai")
        await worker.send(json.dumps(packet))
        self.assertEqual((await self.recv(worker))["code"],"INVALID_MESSAGE")


if __name__=="__main__":
    import unittest
    unittest.main(verbosity=2)
