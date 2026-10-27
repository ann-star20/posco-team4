"""One real direct-Jetson diagnosis and a Gateway request carrying the full result.

Run while Unity Play is off (the relay permits one Unity client). Never re-submit
an uncertain job; active.json keeps the exact request IDs for read-only tracing.
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools/FabSocket/.deps"))
sys.path.insert(0, str(ROOT / "Tools/FabSocket"))
from websockets.asyncio.client import connect
from process_analysis import validate_analysis, validate_request

OUT = ROOT / "Tools/Gateway/IonDirectIntegration"


def save(name, data):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_json(url, token=None):
    req = urllib.request.Request(url, headers={"X-Unity-Token": token} if token else {})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


async def run():
    if (OUT / "active.json").exists():
        raise RuntimeError("A run already exists; inspect its IDs instead of sending again")
    gateway_token = os.environ.get("UNITY_GATEWAY_TEST_TOKEN")
    if not gateway_token:
        raise RuntimeError("Gateway token missing from process environment")
    dataset = get_json("http://127.0.0.1:8601/api/v1/test-samples")
    if dataset.get("data_source") != "jetson_csv_test":
        raise RuntimeError("Expected Jetson CSV service")
    row = next(row for row in dataset["rows"] if row["id"] == "B122" and row["has_tcad"])
    measurement = row["tcad"]
    request_id = "REQ-" + uuid.uuid4().hex
    req = dict(request_id=request_id, lot_id="LOT-UNITY-ION-DIRECT-TEST",
               baseline_version=json.loads((ROOT / "Assets/MOSFETInspection/Resources/ProcessAnalysisSamples.json").read_text(encoding="utf-8-sig"))["baseline_version"],
               data_source="synthetic", n_wafers=1, sent_at_ms=int(time.time()*1000),
               units=dict(vth="V", gm="A/V/um", id4v="A/um", bv="V"), measurement=measurement)
    validate_request(req)
    credentials = json.loads((ROOT / "Tools/FabSocket/server.local.json").read_text(encoding="utf-8-sig"))
    async with connect("ws://127.0.0.1:8765/fab", proxy=None, max_size=4_000_000) as relay:
        await relay.send(json.dumps(dict(type="hello", role="unity", token=credentials["tokens"]["unity"])))
        welcome = json.loads(await asyncio.wait_for(relay.recv(), 8))
        if welcome.get("type") != "welcome":
            raise RuntimeError("Relay login unavailable: " + str(welcome.get("code")))
        save("active.json", dict(direct_request_id=request_id, sample_id=row["id"], state="before_direct_send", simulation_only=True))
        save("direct.request.json", req)
        await relay.send(json.dumps(dict(version=1, type="process_request", message_id=request_id, payload=req)))
        print("DIRECT_REQUEST_SENT " + request_id, flush=True)
        async with asyncio.timeout(200):
            while True:
                packet = json.loads(await relay.recv())
                if packet.get("type") == "error" and packet.get("message_id") == request_id:
                    raise RuntimeError("Direct request failed: " + str(packet.get("code")))
                result = packet.get("payload", {})
                if packet.get("type") != "process_analysis" or result.get("request_id") != request_id:
                    continue
                validate_analysis(result)
                if packet.get("source") != "process_ai" or result.get("delivery") != "computed" or result.get("input") != req:
                    raise RuntimeError("Unrelated or replayed diagnosis")
                save("direct.result.json", packet)
                print("DIRECT_DIAGNOSIS_RECEIVED " + result["top_cause"] + " " + result["mode"], flush=True)
                break
    gateway_request_id, run_id = str(uuid.uuid4()), str(uuid.uuid4())
    archive = dict(type="diagnosis.requested", schema_version=1, request_id=gateway_request_id,
                   run_id=run_id, lot_id=req["lot_id"], unit_id="SIM-IMP01-INTEGRATION", stage_id="ion_diagnosis",
                   stage_attempt=1, model_contract_version="fab-ml-v1", input_payload=dict(
                       measurements=dict(vth=measurement["vth"], gm=measurement["gm"]*1e6,
                                         id_on=measurement["id4v"]*1e6, bv=measurement["bv"]),
                       n_wafers=1, refine=False, provenance=dict(
                           data_source="jetson_csv_test", equipment_id="IMP-01", electrical_source="tcad_csv_not_measurement",
                           inspection_id="DIRECT-INTEGRATION-"+uuid.uuid4().hex, sample_id=row["id"], csv_sha256=dataset["dataset_sha256"],
                           vth_unit="V", gm_unit="uS/um", id_on_unit="uA/um", bv_unit="V",
                           archive_purpose="preserve_jetson_direct_result_in_committed_request; gateway_rediagnosis_is_separate",
                           direct_diagnosis=result)))
    save("gateway.request.json", archive)
    save("active.json", dict(direct_request_id=request_id, gateway_request_id=gateway_request_id, run_id=run_id,
                             sample_id=row["id"], state="before_gateway_send", simulation_only=True))
    async with connect("ws://192.168.212.10:8000/api/v1/control", proxy=None,
                       additional_headers={"X-Unity-Token": gateway_token}) as control:
        await control.send(json.dumps(archive))
        ack = json.loads(await asyncio.wait_for(control.recv(), 15))
        if ack.get("type") != "request.accepted" or ack.get("request_id") != gateway_request_id or ack.get("status") != "queued":
            raise RuntimeError("Gateway did not acknowledge the archive request")
        uuid.UUID(ack["job_id"])
        save("gateway.accepted.json", ack)
    status = get_json("http://192.168.212.10:8000/api/v1/jobs/"+ack["job_id"], gateway_token)
    if status.get("request_id") != gateway_request_id or status.get("run_id") != run_id:
        raise RuntimeError("Gateway job identity mismatch")
    save("gateway.status.json", status)
    save("summary.json", dict(direct_diagnosis_completed=True, direct_request_id=request_id,
        cause=result["top_cause"], probability=result["top_probability"], mode=result["mode"],
        dose_factor=result["dose_factor"], oxide_factor=result["oxide_factor"],
        gateway_request_id=gateway_request_id, gateway_job_id=ack["job_id"], run_id=run_id,
        gateway_request_commit_confirmed=True, gateway_job_status=status["status"],
        note="Full direct result stored inside accepted request provenance; this is not a Gateway diagnosis.completed event",
        simulation_only=True, unity_runtime_cycle_tested=False))
    save("active.json", dict(direct_request_id=request_id, gateway_request_id=gateway_request_id,
                             gateway_job_id=ack["job_id"], run_id=run_id, sample_id=row["id"],
                             state="direct_completed_gateway_request_committed", simulation_only=True))
    print("DIRECT_RESULT_GATEWAY_REQUEST_COMMITTED " + ack["job_id"], flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as error:
        save("failure.json", dict(error=type(error).__name__, detail=str(error)))
        print("DIRECT_INTEGRATION_FAILED " + type(error).__name__ + ": " + str(error), flush=True)
        raise SystemExit(1)
