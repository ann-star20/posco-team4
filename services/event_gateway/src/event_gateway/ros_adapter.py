"""ROS-facing JSON parser and WSL bridge entry point."""

import json
import logging
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Thread
import time
from uuid import UUID, uuid5

import psycopg
from pydantic import ValidationError

from .config import Settings
from .command_dispatcher import claim_due_commands
from .command_auth import sign_command
from .contracts import CorrectionProposal, EventCreate
from .dead_letters import record_dead_letter
from .inference_jobs import claim_due_aoi_requests
from .repository import EventConflict, EventRepository


def shutdown_ros(ros) -> None:
    if ros.ok():
        ros.shutdown()


def spin_ros(node, ros) -> None:
    try:
        ros.spin(node)
    except KeyboardInterrupt:
        pass


def store_ros_event(repository: EventRepository, event: EventCreate,
                    run_id: str, settings: Settings):
    run_uuid = UUID(run_id)
    run_tcad_mode, _, _, baseline = repository.resolve_run(
        run_uuid, settings.tcad_mode, settings.unity_mode)
    if event.event_type == 'surrogate.completed':
        from .surrogate import ingest_surrogate
        return ingest_surrogate(repository,event,run_uuid,settings)
    if event.event_type != "correction.proposed":
        return repository.ingest(event, run_uuid)
    proposal = CorrectionProposal.model_validate(event.payload)
    if proposal.run_id != run_uuid:
        raise ValueError("proposal run_id mismatch")
    if proposal.baseline_version != baseline:
        raise ValueError("proposal baseline mismatch")
    endpoint = (settings.tcad_mock_url if run_tcad_mode == "mock"
                else settings.tcad_prod_url)
    if not endpoint:
        raise ValueError("TCAD endpoint for pinned run is missing")
    return repository.ingest_proposal(
        event, proposal, uuid5(event.event_id, "tcad-verification"),
        run_tcad_mode, endpoint,
    )


class RosEventAdapter:
    def __init__(self, on_event, on_error):
        self.on_event = on_event
        self.on_error = on_error

    def receive(self, raw: str) -> bool:
        try:
            data = json.loads(raw)
            run_id = str(UUID(data.pop("run_id")))
            event = EventCreate.model_validate(data)
        except (ValueError, KeyError, TypeError, ValidationError) as exc:
            self.on_error((type(exc).__name__, raw))
            return False
        return self.on_event((event, run_id, raw)) is not False


def main() -> None:
    """Run inside an already sourced WSL ROS 2 environment."""
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String

    settings = Settings.load(Path(".env"))
    if not settings.ros_command_key:
        raise ValueError("ROS_COMMAND_KEY is required for bridge")
    queue: Queue[tuple[EventCreate, str, str]] = Queue(maxsize=1000)
    dead_queue: Queue[tuple[str, str]] = Queue(maxsize=1000)
    logger = logging.getLogger(__name__)
    rclpy.init()

    class Bridge(Node):
        def __init__(self):
            super().__init__("fab_gateway_bridge")
            self.ack_pub = self.create_publisher(String, settings.ros_event_ack_topic, 10)
            self.command_pub = self.create_publisher(String, settings.ros_command_topic, 10)
            self.inference_pub = self.create_publisher(String, settings.ros_inference_request_topic, 10)
            self.surrogate_pub = self.create_publisher(String, settings.ros_surrogate_request_topic, 10)
            self.adapter = RosEventAdapter(self.enqueue, self.enqueue_dead)
            self.create_subscription(String, settings.ros_event_topic,
                                     lambda msg: self.adapter.receive(msg.data), 10)

        def enqueue(self, item):
            try:
                queue.put_nowait(item)
                return True
            except Full:
                logger.error("event queue full")
                return False

        def enqueue_dead(self, item):
            try:
                dead_queue.put_nowait(item)
            except Full:
                logger.error("dead-letter queue full")

    node = Bridge()

    def publish_receipt(event_id, run_id, status, sequence=None):
        ack = String()
        ack.data = json.dumps({
            "event_id": str(event_id), "run_id": str(run_id),
            "sequence": sequence, "status": status,
        })
        node.ack_pub.publish(ack)

    def record_invalid(reason, raw):
        event_id = run_id = None
        try:
            data = json.loads(raw)
            event_id = UUID(data["event_id"])
            run_id = UUID(data["run_id"])
        except (ValueError, KeyError, TypeError):
            pass
        with psycopg.connect(settings.database_url, autocommit=True) as connection:
            record_dead_letter(connection, raw, reason, event_id, run_id)
        if event_id is not None and run_id is not None:
            publish_receipt(event_id, run_id, "dead_lettered")

    def worker():
        while rclpy.ok():
            try:
                reason, raw = dead_queue.get_nowait()
            except Empty:
                pass
            else:
                try:
                    record_invalid(reason, raw)
                except psycopg.Error:
                    logger.exception("dead-letter storage failed; producer will retry")
                continue
            try:
                event, run_id, raw = queue.get(timeout=0.25)
            except Empty:
                continue
            try:
                with psycopg.connect(settings.database_url, autocommit=True) as connection:
                    repository = EventRepository(connection, settings.ros_command_key)
                    receipt = store_ros_event(repository, event, run_id, settings)
            except (ValueError, EventConflict, ValidationError, psycopg.IntegrityError) as exc:
                try:
                    record_invalid(type(exc).__name__, raw)
                except psycopg.Error:
                    logger.exception("dead-letter storage failed; producer will retry")
                continue
            except Exception:
                logger.exception("event storage failed; producer will retry")
                continue
            publish_receipt(receipt.event_id, receipt.run_id, "committed", receipt.sequence)

    thread = Thread(target=worker, daemon=True)
    thread.start()

    def dispatch_commands():
        while rclpy.ok():
            try:
                with psycopg.connect(settings.database_url, autocommit=True) as connection:
                    due = claim_due_commands(connection)
                for payload in due:
                    message = String()
                    message.data = json.dumps(
                        sign_command(payload, settings.ros_command_key), separators=(",", ":"))
                    node.command_pub.publish(message)
            except Exception:
                logger.exception("command dispatch failed; database retry remains due")
            time.sleep(0.5)

    Thread(target=dispatch_commands, daemon=True).start()

    def dispatch_inference():
        while rclpy.ok():
            try:
                with psycopg.connect(settings.database_url, autocommit=True) as connection:
                    due = claim_due_aoi_requests(connection)
                for payload in due:
                    message = String()
                    message.data = json.dumps(payload, separators=(",", ":"))
                    publisher = node.surrogate_pub if payload['task_type']=='surrogate' else node.inference_pub
                    publisher.publish(message)
            except Exception:
                logger.exception("AOI request dispatch failed; DB outbox remains due")
            time.sleep(0.5)

    Thread(target=dispatch_inference, daemon=True).start()
    try:
        spin_ros(node, rclpy)
    finally:
        node.destroy_node()
        shutdown_ros(rclpy)


if __name__ == "__main__":
    main()
