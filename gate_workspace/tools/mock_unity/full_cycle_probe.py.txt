"""One-shot test of the full knob -> surrogate -> diagnosis -> (conditional) TCAD cycle.

Surrogate and diagnosis are independent request types -- the Gateway never chains
them automatically. This script plays the role Unity would: it sends the knob
values to surrogate, waits for the predicted electrical characteristics, feeds
those values into a diagnosis request, and then (only if the diagnosis response's
compensation.route is "tcad_verify") watches the stream WS for the TCAD
verification events the Gateway queues on its own.

Usage:
    python tools/mock_unity/full_cycle_probe.py \
        --gateway ws://127.0.0.1:8000 --token "$UNITY_API_TOKEN" \
        --body-dose 7.7e12 --epi-doping 1.7e16 --oxide-thickness 0.06
"""

import argparse
import json
import time
from uuid import uuid4

from websockets.sync.client import connect


def send_and_wait_completed(control_url, stream_url, token, request, timeout):
    with connect(control_url, additional_headers={"x-unity-token": token}, open_timeout=5) as ws:
        ws.send(json.dumps(request))
        ack = json.loads(ws.recv(timeout=10))
    if ack.get("type") != "request.accepted":
        raise RuntimeError(f"request rejected: {ack}")

    completed_type = request["type"].replace(".requested", ".completed")
    deadline = time.monotonic() + timeout
    with connect(stream_url, open_timeout=5) as ws:
        while time.monotonic() < deadline:
            try:
                event = json.loads(ws.recv(timeout=1))
            except TimeoutError:
                continue
            payload = event.get("payload", {})
            if payload.get("request_id") == request["request_id"] and event["event_type"] == completed_type:
                return event
    raise TimeoutError(f"no {completed_type} event for request_id={request['request_id']}")


def watch_tcad_events(stream_url, timeout):
    deadline = time.monotonic() + timeout
    with connect(stream_url, open_timeout=5) as ws:
        while time.monotonic() < deadline:
            try:
                event = json.loads(ws.recv(timeout=1))
            except TimeoutError:
                continue
            if event["event_type"].startswith("tcad.verification."):
                print(json.dumps({"event_type": event["event_type"], "sequence": event["sequence"]},
                                 ensure_ascii=False))
                if event["event_type"] == "tcad.verification.batch_completed":
                    return
    raise TimeoutError("timed out waiting for tcad.verification.batch_completed")


def main():
    parser = argparse.ArgumentParser(
        description="노브 입력 -> surrogate -> diagnosis -> (조건부) TCAD 전체 사이클 1회 시험")
    parser.add_argument("--gateway", default="ws://127.0.0.1:8000")
    parser.add_argument("--token", required=True)
    parser.add_argument("--run-id", default=str(uuid4()))
    parser.add_argument("--body-dose", type=float, default=7.7e12)
    parser.add_argument("--epi-doping", type=float, default=1.7e16)
    parser.add_argument("--oxide-thickness", type=float, default=0.06)
    parser.add_argument("--timeout", type=float, default=60,
                        help="surrogate/diagnosis 각각의 완료 대기 시간(초)")
    parser.add_argument("--tcad-timeout", type=float, default=2400,
                        help="TCAD 검증 대기 시간(초). 실측 약 20~30분이 걸릴 수 있음")
    args = parser.parse_args()

    control_url = f"{args.gateway}/api/v1/control"
    stream_url = f"{args.gateway}/api/v1/stream?run_id={args.run_id}&after_sequence=0"

    surrogate_request = {
        "type": "surrogate.requested", "schema_version": 1,
        "request_id": str(uuid4()), "run_id": args.run_id,
        "lot_id": "FULL-CYCLE", "unit_id": "MOSFET-1", "stage_id": "electrical", "stage_attempt": 1,
        "model_contract_version": "fab-ml-v1",
        "input_payload": {
            "process_parameters": {
                "body_dose": args.body_dose, "epi_doping": args.epi_doping,
                "oxide_thickness": args.oxide_thickness,
            },
            "requested_outputs": ["vth", "gm", "id_on", "bv"],
        },
    }
    print(f"run_id={args.run_id}")
    print("1) surrogate 요청 전송 (노브 값 -> 전기적 특성 예측)...")
    surrogate_event = send_and_wait_completed(control_url, stream_url, args.token, surrogate_request, args.timeout)
    surrogate_response = surrogate_event["payload"]["response"]
    if surrogate_response.get("status") != "succeeded":
        raise RuntimeError(f"surrogate failed: {surrogate_response}")
    electrical = surrogate_response["result_payload"]
    print(json.dumps({"surrogate_result_payload": electrical}, ensure_ascii=False))

    diagnosis_request = {
        "type": "diagnosis.requested", "schema_version": 1,
        "request_id": str(uuid4()), "run_id": args.run_id,
        "lot_id": "FULL-CYCLE", "unit_id": "MOSFET-1", "stage_id": "diagnosis", "stage_attempt": 1,
        "model_contract_version": "fab-ml-v1",
        "input_payload": {
            "measurements": {
                "vth": electrical["vth"], "gm": electrical["gm"],
                "id_on": electrical["id_on"], "bv": electrical.get("bv"),
            },
            "n_wafers": 1, "refine": False,
        },
    }
    print("2) diagnosis 요청 전송 (surrogate 예측값을 measurements로 그대로 투입)...")
    diagnosis_event = send_and_wait_completed(control_url, stream_url, args.token, diagnosis_request, args.timeout)
    diagnosis_response = diagnosis_event["payload"]["response"]
    route = (diagnosis_response.get("result_payload") or {}).get("compensation", {}).get("route")
    print(json.dumps({"diagnosis_status": diagnosis_response.get("status"), "route": route},
                     ensure_ascii=False))

    if route == "tcad_verify":
        print("3) route=tcad_verify -> Gateway가 자동으로 TCAD 검증을 시작함. 이벤트 수신 대기...")
        watch_tcad_events(stream_url, args.tcad_timeout)
        print("TCAD 검증 배치 완료.")
    else:
        print(f"3) route={route} -> TCAD 호출 없음 (apply/no_action/manual은 정상적으로 TCAD를 타지 않음)")

    print(json.dumps({"status": "passed", "run_id": args.run_id}, ensure_ascii=False))


if __name__ == "__main__":
    main()
