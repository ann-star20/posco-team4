"""Persist simulation recipe commands before reporting applied."""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import sqlite3
from pathlib import Path
from uuid import UUID, uuid4

from .outbox import Outbox


RECIPE_KEYS = {"oxide_thickness", "body_dose", "diffusion_time", "epi_doping"}


def _mac(payload: dict, key: str) -> str:
    if not key:
        raise ValueError("ROS command key is required")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False).encode("utf-8")
    return hmac.new(key.encode("utf-8"), canonical, hashlib.sha256).hexdigest()


def verify_command(command: dict, key: str) -> bool:
    unsigned = {name: value for name, value in command.items() if name != "command_mac"}
    actual = command.get("command_mac")
    return isinstance(actual, str) and hmac.compare_digest(actual, _mac(unsigned, key))


def make_applied_receipt(command: dict, event_id: UUID, key: str) -> dict:
    payload = {name: command[name] for name in (
        "command_id", "proposal_id", "run_id", "effective_from_lot")}
    return payload | {"receipt_mac": _mac(payload | {"event_id": str(event_id)}, key)}


class RecipeStore:
    def __init__(self, path: Path, signing_key: str):
        if not signing_key:
            raise ValueError("ROS command key is required")
        self.signing_key = signing_key
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS applied_commands("
            "command_id TEXT PRIMARY KEY,body TEXT NOT NULL,effective_from_lot TEXT NOT NULL,"
            "event_id TEXT NOT NULL UNIQUE,applied_at TEXT NOT NULL)"
        )
        self.connection.commit()

    def apply(self, command: dict) -> UUID:
        if not verify_command(command, self.signing_key):
            raise ValueError("invalid command signature")
        command_id = UUID(command["command_id"])
        run_id = UUID(command["run_id"])
        if command.get("scope") != "simulation":
            raise ValueError("physical control is forbidden")
        candidate = command.get("x_candidate")
        current = command.get("x_current")
        if not isinstance(candidate, dict) or not isinstance(current, dict):
            raise ValueError("correction vectors are required")
        if set(candidate) != RECIPE_KEYS or set(current) != RECIPE_KEYS:
            raise ValueError("incorrect recipe keys")
        if candidate["epi_doping"] != current["epi_doping"]:
            raise ValueError("epi doping cannot be changed")
        lot = command.get("effective_from_lot")
        if not isinstance(lot, str) or not lot.strip():
            raise ValueError("effective lot is required")
        body = json.dumps(command, sort_keys=True, separators=(",", ":"))
        with self.connection:
            existing = self.connection.execute(
                "SELECT body,event_id FROM applied_commands WHERE command_id=?",
                (str(command_id),),
            ).fetchone()
            if existing:
                if existing[0] != body:
                    raise ValueError("command_id has different content")
                return UUID(existing[1])
            event_id = uuid4()
            self.connection.execute(
                "INSERT INTO applied_commands(command_id,body,effective_from_lot,event_id,applied_at) "
                "VALUES (?,?,?,?,?)", (str(command_id), body, lot, str(event_id),
                                        datetime.now(timezone.utc).isoformat()),
            )
        return event_id

    def applied_at(self, command_id: UUID) -> str:
        row = self.connection.execute(
            "SELECT applied_at FROM applied_commands WHERE command_id=?", (str(command_id),)
        ).fetchone()
        if row is None:
            raise ValueError("command not applied")
        return row[0]

    def recipe_for(self, lot: str) -> dict | None:
        row = self.connection.execute(
            "SELECT body FROM applied_commands WHERE effective_from_lot=? "
            "ORDER BY rowid DESC LIMIT 1", (lot,),
        ).fetchone()
        return json.loads(row[0])["x_candidate"] if row else None

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def main() -> None:
    import os
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    root = Path(os.environ.get("JETSON_PROJECT_PATH", "/home/jetson/project/smart_factory"))
    signing_key = os.environ.get("ROS_COMMAND_KEY", "")
    store = RecipeStore(root / "data" / "recipes.sqlite", signing_key)
    outbox = Outbox(root / "data" / "event-outbox.sqlite")
    rclpy.init()

    class CommandSubscriber(Node):
        def __init__(self):
            super().__init__("fab_command_subscriber")
            topic = os.environ.get("ROS_COMMAND_TOPIC", "/fab/commands")
            self.create_subscription(String, topic, self.on_command, 10)

        def on_command(self, message):
            try:
                command = json.loads(message.data)
                event_id = store.apply(command)
                run_id = UUID(command["run_id"])
                event = {
                    "schema_version": 1, "event_id": str(event_id),
                    "run_id": str(run_id), "event_type": "correction.applied",
                    "source": "jetson.virtual_lot", "severity": "info",
                    "occurred_at": store.applied_at(UUID(command["command_id"])),
                    "payload": make_applied_receipt(command, event_id, signing_key),
                }
                outbox.enqueue(event_id, run_id, json.dumps(event, separators=(",", ":")))
            except (ValueError, KeyError, TypeError) as exc:
                self.get_logger().warning(f"command rejected: {type(exc).__name__}")

    node = CommandSubscriber()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        store.close()
        outbox.close()
        rclpy.shutdown()
