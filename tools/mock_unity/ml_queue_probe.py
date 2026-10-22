"""Standalone control/stream WS probe: queue several ML requests and watch
results trickle in asynchronously. No Unity client required.

Usage example (WSL, gateway already running):

    python tools/mock_unity/ml_queue_probe.py \
        --gateway ws://127.0.0.1:8000 --token "$UNITY_API_TOKEN" \
        --request-type diagnosis.requested --scenarios anomaly anomaly normal \
        --timeout 180
"""

import argparse
import json
import time
from uuid import uuid4

from websockets.sync.client import connect


def build_requests(request_type: str, scenarios: list[str], run_id: str) -> list[dict]:
    stage_id = "diagnosis" if request_type == "diagnosis.requested" else "electrical"
    return [
        {
            "type": request_type,
            "schema_version": 1,
            "request_id": str(uuid4()),
            "run_id": run_id,
            "lot_id": "QUEUE-PROBE",
            "unit_id": f"UNIT-{index + 1}",
            "stage_id": stage_id,
            "stage_attempt": 1,
            "model_contract_version": "fab-ml-v1",
            "input_payload": {"scenario": scenario},
        }
        for index, scenario in enumerate(scenarios)
    ]


def submit_all(control_url: str, token: str, requests: list[dict]) -> dict:
    """Send every request on one control-WS connection and record the
    *immediate* accepted/rejected reply for each. This is the synchronous
    half of the contract -- it never waits for ML/TCAD to finish."""
    accepted = {}
    with connect(control_url, additional_headers={"x-unity-token": token}, open_timeout=5) as ws:
        for request in requests:
            sent_at = time.monotonic()
            ws.send(json.dumps(request))
            response = json.loads(ws.recv(timeout=10))
            print(json.dumps({"sent_unit_id": request["unit_id"], "response": response},
                             ensure_ascii=False))
            if response.get("type") != "request.accepted":
                raise RuntimeError(f"{request['unit_id']} was rejected: {response}")
            accepted[response["request_id"]] = {
                "unit_id": request["unit_id"],
                "job_id": response["job_id"],
                "accepted_at": sent_at,
            }
    return accepted


def wait_for_results(stream_url: str, accepted: dict, timeout: float) -> list[dict]:
    """Open the stream WS separately and watch results arrive one at a time.
    This is the asynchronous half -- it must NOT run on the control
    connection, and completion order is not guaranteed to match submit order."""
    pending = set(accepted)
    results = []
    deadline = time.monotonic() + timeout
    with connect(stream_url, open_timeout=5) as ws:
        while pending and time.monotonic() < deadline:
            try:
                event = json.loads(ws.recv(timeout=1))
            except TimeoutError:
                continue
            payload = event.get("payload", {})
            request_id = payload.get("request_id")
            elapsed = (time.monotonic() - accepted[request_id]["accepted_at"]
                       if request_id in accepted else None)
            print(json.dumps({
                "event_type": event["event_type"],
                "sequence": event["sequence"],
                "unit_id": accepted.get(request_id, {}).get("unit_id"),
                "elapsed_since_accept_s": round(elapsed, 2) if elapsed is not None else None,
            }, ensure_ascii=False))
            if request_id in pending and event["event_type"] in (
                "surrogate.completed", "diagnosis.completed"
            ):
                pending.discard(request_id)
                results.append({
                    "unit_id": accepted[request_id]["unit_id"],
                    "request_id": request_id,
                    "elapsed_s": round(elapsed, 2),
                })
    if pending:
        missing = [accepted[r]["unit_id"] for r in pending]
        raise TimeoutError(f"timed out waiting for results for: {missing}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unity 없이 제어/스트림 WS로 ML 요청 큐 적재·비동기 결과 수신을 직접 시험")
    parser.add_argument("--gateway", default="ws://127.0.0.1:8000",
                        help="scheme+host+port only, e.g. ws://192.168.10.234:8000")
    parser.add_argument("--token", required=True, help="Gateway .env의 UNITY_API_TOKEN")
    parser.add_argument("--run-id", default=str(uuid4()))
    parser.add_argument("--request-type", choices=["surrogate.requested", "diagnosis.requested"],
                        default="diagnosis.requested")
    parser.add_argument("--scenarios", nargs="+", default=["anomaly", "anomaly", "normal"],
                        help="요청마다 input_payload.scenario에 들어갈 값 목록")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()

    control_url = f"{args.gateway}/api/v1/control"
    stream_url = f"{args.gateway}/api/v1/stream?run_id={args.run_id}&after_sequence=0"

    requests = build_requests(args.request_type, args.scenarios, args.run_id)
    print(f"run_id={args.run_id} -- {len(requests)}건을 제어 WS로 연속 전송합니다 (즉시 accepted만 확인).")
    accepted = submit_all(control_url, args.token, requests)
    print(f"접수 완료: {len(accepted)}건 모두 queued. 이제 스트림 WS를 별도로 열어 비동기 결과를 기다립니다.")

    results = wait_for_results(stream_url, accepted, args.timeout)

    print(json.dumps({"status": "passed", "run_id": args.run_id, "results": results},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
