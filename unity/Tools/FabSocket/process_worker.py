"""Authenticated request listener; each job executes the installed diagnostic model."""
import argparse
import asyncio
import hashlib
import importlib.util
import json
import sys
import time
from collections import OrderedDict
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent / ".deps"))
from process_analysis import validate_analysis, validate_request


def verify_model(root, reference_file=None):
    from agent_check import fingerprint
    reference = json.loads(Path(reference_file or root / "agent_reference.json").read_text(encoding="utf-8-sig"))
    if reference.get("status") != "passed" or fingerprint(root) != reference["hashes"]:
        raise ValueError("Verified model/source fingerprints changed")
    return reference


def compute(root, request, basic_only=False, reference_file=None):
    import numpy as np
    validate_request(request, fresh=False)
    sys.path.insert(0, str(root))
    reference = verify_model(root, reference_file)
    baseline = "tcad-gp-" + reference["hashes"]["최종ML/모델/gp.npz"][:12]
    if request["baseline_version"] != baseline:
        raise ValueError("Baseline differs from installed model")
    spec = importlib.util.spec_from_file_location("request_agent", root / "진단에이전트/진단에이전트.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    started = time.perf_counter()
    agent, pipe = module.build_agent(high_precision=not basic_only)
    agent.rng = np.random.default_rng(0)
    diagnosis = agent.diagnose(request["measurement"], request["n_wafers"])
    rec = agent.recommend(diagnosis)
    prop = agent.compensate(diagnosis)
    fallback = ""
    hp = {}
    if not basic_only and pipe.high_precision_available:
        try:
            hp = agent.final_check(diagnosis, prop)
            if not hp.get("실시") or hp.get("모드") != "고정밀(GP+TabPFN)":
                raise RuntimeError("High precision did not run")
        except Exception as error:
            hp = {}
            fallback = "고정밀 오류: " + type(error).__name__ + " · 기본 GP 결과"
    else:
        reason = " ".join(str(getattr(pipe,"hp_error","미설치")).split())[:120]
        fallback = "기본 GP 요청" if basic_only else "고정밀 사용 불가 ("+reason+") · 기본 GP 결과"
    high = bool(hp.get("실시"))
    cause = hp["판정_후"] if high else diagnosis["최다"]
    probability = float(hp["최다확률_후"] if high else diagnosis["최다확률"])
    decided = probability >= .70
    mean = [float(k["평균"]) for k in diagnosis["노브"]]
    candidate = np.array(mean) * [prop["도즈배율"], 1, prop["산화막배율"]]
    warning = prop["경고"] or ""
    if high and hp["판정바뀜"]:
        warning += " · 고정밀 원인 후보 변경: 보정안은 기본 GP 사후분포 기반, 추가 검토 필요"
    if not bool(agent.sur.domain(np.array([candidate]))[0]):
        warning += " · 보정 후보가 모델 영역 밖: 적용 불가"
    warning = (warning + " · " + fallback).strip(" ·")[:500]
    now = int(time.time()*1000)
    p = dict(lot_id=request["lot_id"], request_id=request["request_id"], run_id=request["request_id"],
             proposal_id=request["request_id"] + "-proposal", baseline_version=baseline,
             model_version="agent-" + reference["hashes"]["진단에이전트/진단에이전트.py"][:12],
             data_source="synthetic", delivery="computed", mode="gp_tabpfn" if high else "gp_only",
             decision="ambiguous" if not decided else "normal" if cause == "정상" else "diagnosed",
             decided=decided, top_cause=cause, top_probability=probability,
             dose_factor=float(prop["도즈배율"]), oxide_factor=float(prop["산화막배율"]),
             estimated_dose=mean[0], estimated_epi=mean[1], estimated_oxide=mean[2],
             basic_candidates=[dict(name=k, probability=float(v)) for k,v in diagnosis["범주확률"].items()],
             recommendation=rec["권고"], warning=warning, duration_seconds=time.perf_counter()-started,
             tcad_status="not_run", applied=False, generated_at_ms=now, sent_at_ms=now, input=request)
    validate_analysis(p)
    return p


async def run_job(root, request, basic_only=False, timeout=180, reference_file=None):
    args = [sys.executable, "-u", str(Path(__file__).resolve()), "--job", "--root", str(root)]
    if basic_only:
        args.append("--basic-only")
    if reference_file:
        args.extend(["--reference", str(reference_file)])
    process = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        output, error = await asyncio.wait_for(process.communicate(json.dumps(request).encode()), timeout)
        if process.returncode:
            raise RuntimeError("Diagnostic job failed; inspect process-worker-error.log")
        marker = next(line[18:] for line in output.decode("utf-8").splitlines() if line.startswith("COMPUTED_ANALYSIS "))
        result = json.loads(marker)
        validate_analysis(result)
        return result
    except BaseException:
        if process.returncode is None:
            process.kill()
            await process.wait()
        raise
    finally:
        if 'error' in locals() and error:
            log_dir = Path(reference_file).resolve().parent if reference_file else root
            (log_dir / "process-worker-error.log").write_bytes(error)


async def listen(args, config):
    from websockets.asyncio.client import connect
    verify_model(args.root, args.reference)
    print("PROCESS_MODEL_VERIFIED", flush=True)
    parsed = urlparse(config["url"])
    if parsed.scheme != "ws" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.path != "/fab":
        raise ValueError("Local SSH tunnel required")
    cache = OrderedDict()
    # shortcut: deduplication lasts this worker session (256 requests); no automatic Unity retries.
    while True:
        task = None
        try:
            async with connect(config["url"], proxy=None, open_timeout=10, max_size=4_000_000) as socket:
                await socket.send(json.dumps(dict(type="hello", role="process_ai", token=config["token"])))
                welcome = json.loads(await asyncio.wait_for(socket.recv(), 10))
                if welcome.get("type") != "welcome":
                    raise ValueError("Worker authentication failed or process_ai role already in use")
                print("PROCESS_WORKER_CONNECTED", flush=True)

                async def status(state, p=None, detail=""):
                    await socket.send(json.dumps(dict(version=1, type="process_status", message_id="status-"+str(time.time_ns()),
                        payload=dict(state=state, request_id=p["request_id"] if p else "", lot_id=p["lot_id"] if p else "", detail=detail)), ensure_ascii=False))

                async def execute(p, key):
                    try:
                        await status("running", p, "Jetson 계산 중")
                        answer = await run_job(args.root, p, args.basic_only, reference_file=args.reference)
                        packet = dict(version=1, type="process_analysis", message_id=p["request_id"]+"-result", payload=answer)
                        cache[key][1] = packet
                        await socket.send(json.dumps(packet, ensure_ascii=False, allow_nan=False))
                        print("COMPLETED", p["request_id"], answer["mode"], answer["decision"], flush=True)
                    except asyncio.CancelledError:
                        raise
                    except Exception as error:
                        cache[key][1] = None
                        await status("failed", p, "계산 실패: "+type(error).__name__+" · 로그 확인 필요")
                        print("REQUEST_FAILED", p["request_id"], type(error).__name__, flush=True)

                async def heartbeat():
                    while True:
                        await status("ready", detail="busy" if task and not task.done() else "ready")
                        await asyncio.sleep(5)

                pulse = asyncio.create_task(heartbeat())
                try:
                    async for raw in socket:
                        event = json.loads(raw)
                        if event.get("type") != "process_request":
                            if event.get("type") == "error":
                                print("RELAY", event.get("code"), flush=True)
                            continue
                        if event.get("source") != "unity" or event.get("target") != "process_ai":
                            continue
                        p = event["payload"]
                        validate_request(p)
                        key = p["request_id"]
                        digest = hashlib.sha256(json.dumps(p, sort_keys=True).encode()).hexdigest()
                        if key in cache:
                            if cache[key][0] != digest:
                                await status("failed", p, "요청 ID가 다른 입력에 재사용됨")
                            elif cache[key][1]:
                                cache[key][1]["payload"]["sent_at_ms"] = int(time.time()*1000)
                                # A fresh transport ID allows replay after a server reconnect.
                                cached = dict(cache[key][1], message_id=key+"-retry-"+str(time.time_ns()))
                                await socket.send(json.dumps(cached, ensure_ascii=False))
                            else:
                                await status("failed", p, "이전 요청 상태 확인 필요 · 새 요청으로 진행")
                            continue
                        if task and not task.done():
                            await status("failed", p, "다른 분석 계산 중 · 완료 후 요청")
                            continue
                        cache[key] = [digest, None]
                        if len(cache)>256:
                            cache.popitem(last=False)
                        task = asyncio.create_task(execute(p, key))
                finally:
                    pulse.cancel()
                    if task and not task.done():
                        task.cancel()
                    await asyncio.gather(pulse, *([task] if task else []), return_exceptions=True)
        except ValueError:
            raise
        except Exception as error:
            print("WORKER_RECONNECT", type(error).__name__, flush=True)
            await asyncio.sleep(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--job", action="store_true")
    parser.add_argument("--basic-only", action="store_true")
    parser.add_argument("--config-stdin", action="store_true")
    args = parser.parse_args()
    if args.job:
        result = compute(args.root, json.load(sys.stdin), args.basic_only, args.reference)
        print("COMPUTED_ANALYSIS "+json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
    elif args.config_stdin:
        asyncio.run(listen(args, json.load(sys.stdin)))
    else:
        parser.error("--config-stdin required; credentials never passed as arguments")
