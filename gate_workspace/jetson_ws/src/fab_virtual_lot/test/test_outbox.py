from uuid import uuid4

from fab_virtual_lot.outbox import Outbox


def test_persist_before_publish_and_ack(tmp_path):
    path = tmp_path / "outbox.sqlite"
    event_id, run_id = uuid4(), uuid4()
    with Outbox(path) as outbox:
        outbox.enqueue(event_id, run_id, '{"event_type":"anomaly.detected"}')
    with Outbox(path) as reopened:
        assert len(reopened.pending()) == 1
        assert reopened.pending()[0].event_id == event_id
        assert reopened.ack(event_id, uuid4(), 1) is False
        assert len(reopened.pending()) == 1
        assert reopened.ack(event_id, run_id, 1) is True
        assert reopened.pending() == []


def test_duplicate_enqueue_keeps_original(tmp_path):
    event_id, run_id = uuid4(), uuid4()
    with Outbox(tmp_path / "outbox.sqlite") as outbox:
        outbox.enqueue(event_id, run_id, '{"payload":1}')
        outbox.enqueue(event_id, run_id, '{"payload":1}')
        assert len(outbox.pending()) == 1


def test_dead_letter_receipt_stops_retry_but_retains_body(tmp_path):
    event_id, run_id = uuid4(), uuid4()
    with Outbox(tmp_path / "outbox.sqlite") as outbox:
        outbox.enqueue(event_id, run_id, '{"bad":true}')
        assert outbox.dead_letter(event_id, run_id) is True
        assert outbox.pending() == []
        assert outbox.connection.execute(
            "SELECT body,delivered_sequence FROM pending WHERE event_id=?", (str(event_id),)
        ).fetchone() == ('{"bad":true}', -1)
