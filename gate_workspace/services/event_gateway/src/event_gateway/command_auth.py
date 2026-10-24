"""Shared-key signatures for simulation command and applied receipt transport."""

import hashlib
import hmac
import json
from uuid import UUID


RECEIPT_FIELDS = ("command_id", "proposal_id", "run_id", "effective_from_lot")


def _mac(payload: dict, key: str) -> str:
    if not key:
        raise ValueError("ROS command key is required")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    return hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def sign_command(command: dict, key: str) -> dict:
    unsigned = {name: value for name, value in command.items() if name != "command_mac"}
    return unsigned | {"command_mac": _mac(unsigned, key)}


def verify_applied_receipt(payload: dict, event_id: UUID, key: str) -> bool:
    try:
        expected = _mac({name: payload[name] for name in RECEIPT_FIELDS}
                        | {"event_id": str(event_id)}, key)
        actual = payload["receipt_mac"]
        return isinstance(actual, str) and hmac.compare_digest(actual, expected)
    except (KeyError, TypeError, ValueError):
        return False
