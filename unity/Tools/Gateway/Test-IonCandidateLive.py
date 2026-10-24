"""Submit one Unity-built ion correction candidate and verify its committed event.

Uses the saved real Jetson diagnosis, not a new diagnosis or a fabricated result.
The request JSON is produced by GatewayTcadProtocol.BuildIon in Unity checks.
"""
import asyncio
import json
import math
import os
from pathlib import Path
import sys
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Tools/FabSocket/.deps"))
from websockets.asyncio.client import connect

OUT = ROOT / "Tools/Gateway/IonCandidateIntegration"
ORIGIN = "http://192.168.212.10:8000"


def save(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def get(path, token):
    req = urllib.request.Request(ORIGIN+path, headers={"X-Unity-Token": token})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


async def run():
    if (OUT / "active.json").exists():
        raise RuntimeError("Existing candidate run found; query its IDs instead of resubmitting")
    token = os.environ.get("UNITY_GATEWAY_TEST_TOKEN")
    if not token:
        raise RuntimeError("Gateway token missing from environment")
    request = json.loads((ROOT / "Temp/IonGateway/ion-candidate-live.request.json").read_text(encoding="utf-8-sig"))
    if request["type"] != "surrogate.requested" or request["stage_id"] != "tcad_candidate_prediction":
        raise RuntimeError("Not the film-compatible candidate request")
    uuid.UUID(request["request_id"])
    uuid.UUID(request["run_id"])
    params = request["input_payload"]["process_parameters"]
    provenance = request["input_payload"]["provenance"]
    context = provenance["tcad"]
    if context["purpose"] != "tcad_candidate_prediction_for_gateway_forwarding" or context["approved"] or context["applied"]:
        raise RuntimeError("Candidate purpose or approval boundaries invalid")
    before = context["estimated_before"]
    expected = dict(body_dose=before["body_dose"]*context["dose_factor"], epi_doping=before["epi_doping"],
                    oxide_thickness=before["oxide_thickness"]*context["oxide_factor"])
    if not all(math.isclose(params[key], value, rel_tol=1e-12) for key, value in expected.items()):
        raise RuntimeError("Candidate did not use posterior state and correction factors")
    actual = json.loads((ROOT / "Tools/Gateway/IonDirectIntegration/direct.result.json").read_text(encoding="utf-8-sig"))["payload"]
    if context["diagnosis_request_id"] != actual["request_id"] or context["direct_diagnosis"]["top_cause"] != actual["top_cause"]:
        raise RuntimeError("Real Jetson diagnosis association missing")
    run = request["run_id"]
    async with connect("ws://192.168.212.10:8000/api/v1/stream?run_id="+run+"&after_sequence=0", proxy=None, max_size=4_000_000) as stream:
        save("active.json", dict(request_id=request["request_id"], run_id=run, state="before_send", simulation_only=True))
        save("candidate.request.json", request)
        async with connect("ws://192.168.212.10:8000/api/v1/control", proxy=None,
                           additional_headers={"X-Unity-Token": token}) as control:
            await control.send(json.dumps(request))
            ack = json.loads(await asyncio.wait_for(control.recv(), 15))
            if ack.get("type") != "request.accepted" or ack.get("request_id") != request["request_id"] or ack.get("status") != "queued":
                raise RuntimeError("Candidate not accepted; do not automatically resubmit")
            save("candidate.accepted.json", ack)
            print("ION_CANDIDATE_ACCEPTED " + ack["job_id"], flush=True)
        async with asyncio.timeout(100):
            while True:
                event = json.loads(await stream.recv())
                payload = event.get("payload", {})
                if event.get("run_id") != run or payload.get("request_id") != request["request_id"]:
                    continue
                save("candidate.event.json", event)
                if event.get("event_type") != "surrogate.completed" or payload.get("job_id") != ack["job_id"]:
                    raise RuntimeError("Candidate failed or response identity mismatch")
                response = payload.get("response", {})
                if response.get("status") != "succeeded" or response.get("result_origin") != "prod":
                    raise RuntimeError("No successful real-model candidate prediction")
                units = response.get("metadata", {}).get("units", {})
                if units != dict(vth="V", gm="uS/um", id_on="uA/um", bv="V"):
                    raise RuntimeError("Candidate prediction units invalid")
                print("ION_CANDIDATE_PREDICTED " + event["event_id"], flush=True)
                break
    events = get("/api/v1/events?run_id="+run+"&after_sequence=0", token)["events"]
    replay = next(item for item in events if item["event_id"] == event["event_id"])
    saved_input = replay["payload"]["input_payload"]
    saved_context = saved_input["provenance"]["tcad"]
    if saved_input["process_parameters"] != params or saved_context["diagnosis_request_id"] != actual["request_id"]:
        raise RuntimeError("DB event changed candidate parameters or diagnosis identity")
    if saved_context["direct_diagnosis"]["top_cause"] != actual["top_cause"] or saved_context["dose_factor"] != context["dose_factor"]:
        raise RuntimeError("DB event lost direct cause or correction")
    save("candidate.db-replayed.json", replay)
    job = get("/api/v1/jobs/"+ack["job_id"], token)
    save("candidate.job.json", job)
    save("summary.json", dict(request_id=request["request_id"], run_id=run, job_id=ack["job_id"],
        event_id=event["event_id"], sequence=event["sequence"], process_parameters=params,
        predicted_outputs=response["result_payload"], cause=saved_context["legacy_top_cause_ko"],
        dose_factor=context["dose_factor"], oxide_factor=context["oxide_factor"],
        candidate_and_diagnosis_db_event_replayed=True, gateway_job_status=job["status"],
        simulation_only=True, unity_runtime_network_tested=False, tcad_executed=False, approved=False))
    save("active.json", dict(request_id=request["request_id"], run_id=run, job_id=ack["job_id"],
                             state="candidate_and_diagnosis_db_event_replayed", simulation_only=True))
    print("ION_CANDIDATE_CAUSE_AND_PARAMETERS_DB_REPLAY_OK", flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except Exception as error:
        save("failure.json", dict(error=type(error).__name__, detail=str(error)))
        print("ION_CANDIDATE_FAILED " + type(error).__name__ + ": " + str(error), flush=True)
        raise SystemExit(1)
