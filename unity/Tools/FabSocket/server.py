"""Local-first WebSocket relay. It forwards messages; it never executes a recipe."""
import argparse
import asyncio
import hashlib
import json
import logging
import math
from pathlib import Path
import secrets
import ssl
import sys
import time
from collections import OrderedDict
from process_analysis import validate_analysis, validate_request, validate_status

sys.path.insert(0, str(Path(__file__).parent / ".deps"))
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

ROLES = {"unity", "jetson", "tcad", "process_ai"}
ROUTES = {"inspection_result": "jetson", "camera_frame": "jetson",
          "tcad_result": "tcad", "recipe_proposal": "tcad", "command": "unity", "process_analysis": "process_ai",
          "process_request": "unity", "process_status": "process_ai"}
MAX_BYTES = 4_000_000
LOG = logging.getLogger("fab.socket")


def object_json(raw):
    if not isinstance(raw, str):
        raise ValueError("Text JSON required")
    def invalid(value):
        raise ValueError("Non-finite number")
    data = json.loads(raw, parse_constant=invalid)
    if not isinstance(data, dict):
        raise ValueError("JSON object required")
    # Reject numbers such as 1e999, which JSON parsers may decode as infinity.
    json.dumps(data, allow_nan=False)
    return data


def identifier(value, name):
    if not isinstance(value, str) or not 1 <= len(value) <= 128 or any(ord(c) < 32 for c in value):
        raise ValueError(name + " required (1..128 characters)")


def validate(message, role):
    if message.get("version") != 1:
        raise ValueError("version must be 1")
    identifier(message.get("message_id"), "message_id")
    kind = message.get("type")
    if ROUTES.get(kind) != role:
        raise ValueError("Message type not allowed for this role")
    payload = message.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    target = "unity"
    if kind == "inspection_result":
        for key in ("result_id", "product_id", "frame_id"):
            identifier(payload.get(key), key)
        if payload.get("label") not in {"normal", "crash", "band", "scratch"}:
            raise ValueError("Unknown inspection label")
        confidence = payload.get("confidence")
        if type(confidence) not in (int, float) or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be 0..1")
        stamp = payload.get("captured_at_ms")
        if type(stamp) is not int or not -2000 <= int(time.time()*1000)-stamp <= 5000:
            raise ValueError("Inspection timestamp expired; synchronize device clocks")
    elif kind == "camera_frame":
        identifier(payload.get("frame_id"), "frame_id")
        if type(payload.get("captured_at_ms")) is not int:
            raise ValueError("captured_at_ms required")
        image = payload.get("jpeg_base64")
        if not isinstance(image, str) or not 1 <= len(image) <= 2_800_000:
            raise ValueError("jpeg_base64 required (max 2800000 characters)")
    elif kind in {"tcad_result", "recipe_proposal"}:
        identifier(payload.get("run_id"), "run_id")
        if kind == "tcad_result" and payload.get("status") not in {"running", "completed", "failed"}:
            raise ValueError("Unknown TCAD status")
        if payload.get("representation") not in {"physical", "normalized_ratio"}:
            raise ValueError("Explicit physical / normalized_ratio representation required")
        if payload["representation"] == "normalized_ratio":
            identifier(payload.get("baseline_version"), "baseline_version")
        elif not isinstance(payload.get("units"), dict):
            raise ValueError("units object required for physical values")
    elif kind == "process_analysis":
        validate_analysis(payload)
    elif kind == "process_request":
        validate_request(payload)
        if message["message_id"] != payload["request_id"]:
            raise ValueError("Request identity mismatch")
        target = "process_ai"
    elif kind == "process_status":
        validate_status(payload)
    elif kind == "command":
        target = message.get("target")
        if target not in {"jetson", "tcad"}:
            raise ValueError("Command target must be jetson or tcad")
        allowed = {"jetson": {"START_INSPECTION", "PAUSE", "CANCEL"},
                   "tcad": {"RUN_TCAD", "CANCEL"}}
        if payload.get("action") not in allowed[target]:
            raise ValueError("Unsupported command")
    return target


class Relay:
    def __init__(self, tokens):
        self.tokens = tokens
        self.clients = {}
        self.recent = OrderedDict()

    async def send(self, websocket, message):
        await asyncio.wait_for(websocket.send(json.dumps(message, ensure_ascii=False, allow_nan=False)), 2)

    async def error(self, websocket, code, message, message_id=None):
        await self.send(websocket, {"type": "error", "code": code, "message": message, "message_id": message_id})

    async def handler(self, websocket):
        role = None
        registered = False
        try:
            if websocket.request.path != "/fab":
                await websocket.close(1008, "Use /fab")
                return
            hello = object_json(await asyncio.wait_for(websocket.recv(), 5))
            role = hello.get("role")
            token = hello.get("token")
            if hello.get("type") != "hello" or role not in ROLES or not isinstance(token, str) or not secrets.compare_digest(token, self.tokens[role]):
                await self.error(websocket, "AUTH_FAILED", "Invalid role or token")
                await websocket.close(1008, "Authentication failed")
                return
            if role in self.clients:
                await self.error(websocket, "ROLE_IN_USE", "One connection per role")
                return
            self.clients[role] = websocket
            registered = True
            await self.send(websocket, {"type": "welcome", "version": 1, "role": role})
            LOG.info("connected role=%s", role)
            async for raw in websocket:
                message = {}
                try:
                    message = object_json(raw)
                    target = validate(message, role)
                    key = (role, message["message_id"])
                    digest = hashlib.sha256(json.dumps(message, sort_keys=True).encode()).hexdigest()
                    if key in self.recent:
                        if self.recent[key] != digest:
                            raise ValueError("message_id reused with different content")
                        await self.send(websocket, {"type": "ack", "message_id": key[1], "status": "duplicate"})
                        continue
                    recipient = self.clients.get(target)
                    if recipient is None:
                        await self.error(websocket, "TARGET_OFFLINE", target + " is not connected; retry later", message["message_id"])
                        continue
                    outbound = {k: message[k] for k in ("version", "type", "message_id", "payload")}
                    outbound.update(source=role, target=target, received_at_ms=int(time.time()*1000))
                    try:
                        await self.send(recipient, outbound)
                    except (ConnectionClosed, TimeoutError):
                        await recipient.close(1013, "Receiver unavailable")
                        await self.error(websocket, "TARGET_UNAVAILABLE", "Delivery incomplete; reconnect and reconcile by message_id", message["message_id"])
                        continue
                    self.recent[key] = digest
                    if len(self.recent) > 2048:
                        self.recent.popitem(last=False)
                    await self.send(websocket, {"type": "ack", "message_id": key[1], "status": "forwarded", "target": target})
                    LOG.info("forwarded type=%s source=%s target=%s", message["type"], role, target)
                except (ValueError, TypeError, RecursionError, OverflowError):
                    await self.error(websocket, "INVALID_MESSAGE", "Invalid message schema, role, timestamp, or numeric value", message.get("message_id"))
        except (ConnectionClosed, TimeoutError):
            pass
        except (ValueError, TypeError, RecursionError, OverflowError):
            await websocket.close(1008, "Invalid hello")
        finally:
            if registered and self.clients.get(role) is websocket:
                del self.clients[role]
                LOG.info("disconnected role=%s", role)


def load_config(path):
    if not path.exists():
        config = {"tokens": {role: secrets.token_urlsafe(32) for role in sorted(ROLES)}}
        with path.open("x", encoding="utf-8") as stream:
            json.dump(config, stream, indent=2)
    config = json.loads(path.read_text(encoding="utf-8"))
    if "process_ai" not in config["tokens"]:
        config["tokens"]["process_ai"] = secrets.token_urlsafe(32)
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    for role in ROLES:
        if not isinstance(config["tokens"].get(role), str) or len(config["tokens"][role]) < 32:
            raise ValueError("Invalid role token in local config")
    return config


async def main(args):
    context = None
    if args.cert and args.key:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(args.cert, args.key)
    if args.host not in {"127.0.0.1", "::1", "localhost"} and context is None:
        raise ValueError("LAN binding requires --cert and --key for wss://")
    relay = Relay(load_config(Path(args.config))["tokens"])
    async with serve(relay.handler, args.host, args.port, ssl=context, origins=[None],
                     max_size=MAX_BYTES, max_queue=4, compression=None,
                     ping_interval=20, ping_timeout=20, close_timeout=3) as server:
        LOG.info("FAB_SOCKET_READY %s://%s:%d/fab", "wss" if context else "ws", args.host, args.port)
        await server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--config", default=str(Path(__file__).with_name("server.local.json")))
    parser.add_argument("--cert")
    parser.add_argument("--key")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(main(parser.parse_args()))
    except KeyboardInterrupt:
        pass
