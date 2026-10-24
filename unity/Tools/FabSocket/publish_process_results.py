"""Replay verified Jetson synthetic analyses over an authenticated SSH tunnel."""
import argparse
import asyncio
import hashlib
import json
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent / ".deps"))
from websockets.asyncio.client import connect
from process_analysis import from_result


async def publish(args):
    config = json.load(sys.stdin) if args.config_stdin else json.loads(args.config.read_text(encoding="utf-8-sig"))
    url = args.url or config["url"]
    parsed = urlparse(url)
    if parsed.scheme != "ws" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.path != "/fab":
        raise ValueError("Publisher requires a local SSH tunnel endpoint")
    token = config["token"]
    if not isinstance(token, str) or len(token) < 32:
        raise ValueError("Missing local process-AI credential")
    root = args.root
    result_path = args.result or root / "agent_high_precision_result.json"
    reference_path = args.reference or root / "agent_reference.json"
    result = json.loads(result_path.read_text(encoding="utf-8-sig"))
    basic = json.loads(reference_path.read_text(encoding="utf-8-sig"))
    if result.get("status") != "passed" or result.get("approval_or_recipe_application_executed") is not False:
        raise ValueError("Verified read-only diagnostic results required")
    baseline = "tcad-gp-" + hashlib.sha256((root / "최종ML" / "모델" / "gp.npz").read_bytes()).hexdigest()[:12]
    model = "agent-" + hashlib.sha256((root / "진단에이전트" / "진단에이전트.py").read_bytes()).hexdigest()[:12] + "+tabpfn9.2.0"
    run_id = "JTEST-" + uuid.uuid4().hex[:12]
    generated = int(result_path.stat().st_mtime * 1000)
    by_name = {item["name"]: item for item in result["results"]}
    cases = ["normal", "epi_minus40_without_bv", "epi_minus40_with_bv", "oxide_plus15"]
    sent = []
    async with connect(url, proxy=None, open_timeout=10, max_size=4000000) as socket:
        await socket.send(json.dumps(dict(type="hello", role="process_ai", token=token)))
        welcome = json.loads(await asyncio.wait_for(socket.recv(), 10))
        if welcome.get("type") != "welcome" or welcome.get("role") != "process_ai":
            raise RuntimeError("Process AI authentication failed; restart the updated server")
        for name in cases:
            case = by_name[name]
            ref = next(item for item in basic["results"] if item["name"] == name)
            payload = from_result(case, ref, run_id, baseline, model, generated)
            packet = dict(version=1, type="process_analysis", message_id=payload["proposal_id"], payload=payload)
            deadline = time.monotonic() + 60
            while True:
                await socket.send(json.dumps(packet, ensure_ascii=False, allow_nan=False))
                ack = json.loads(await asyncio.wait_for(socket.recv(), 10))
                if ack.get("type") == "ack" and ack.get("message_id") == packet["message_id"] and ack.get("status") in {"forwarded", "duplicate"}:
                    break
                if ack.get("code") not in {"TARGET_OFFLINE", "TARGET_UNAVAILABLE"} or time.monotonic() > deadline:
                    raise RuntimeError("Relay rejected result: " + str(ack.get("code", "invalid_ack")))
                print("Waiting for Unity Play connection...", flush=True)
                await asyncio.sleep(2)
            sent.append(dict(lot_id=payload["lot_id"], proposal_id=payload["proposal_id"], decision=payload["decision"]))
            print("FORWARDED", payload["lot_id"], payload["decision"], flush=True)
            await asyncio.sleep(.5)
    report = dict(status="passed", run_id=run_id, count=len(sent), delivery="synthetic_replay", results=sent)
    print("JETSON_PROCESS_PUBLISH_RESULT " + json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("process-ai.local.json"))
    parser.add_argument("--config-stdin", action="store_true")
    parser.add_argument("--url")
    parser.add_argument("--result", type=Path)
    parser.add_argument("--reference", type=Path)
    asyncio.run(publish(parser.parse_args()))
