from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg

from event_gateway.config import Settings
from event_gateway.contracts import EventCreate
from event_gateway.inference_jobs import claim_due_aoi_requests, submit_inference_job
from event_gateway.migrate import apply_migrations
from event_gateway.repository import EventRepository
from event_gateway.ros_adapter import store_ros_event
from event_gateway.tcad_candidate_worker import TcadCandidateWorker
from mock_surrogate.app import diagnose


ROOT = Path(__file__).parents[4]


def admit_two(connection):
    apply_migrations(connection, ROOT / "database/migrations")
    request = {
        "request_id": str(uuid4()), "run_id": str(uuid4()), "lot_id": "LOT-1",
        "unit_id": "UNIT-1", "stage_id": "diagnosis", "stage_attempt": 1,
        "model_contract_version": "fab-ml-v1", "input_payload": {"scenario": "anomaly"},
        "diagnosis_mode": "mock",
    }
    submit_inference_job(connection, request, "mock", "mock", "diagnosis")
    dispatch = claim_due_aoi_requests(connection)[0]
    response = diagnose(dispatch)
    second = deepcopy(response["tcad_proposal"]["candidates"][0])
    second["process_parameters"]["oxide_thickness"] = 0.065
    response["tcad_proposal"]["candidates"].append(second)
    event = EventCreate(
        schema_version=1, event_id=uuid4(), event_type="diagnosis.completed",
        source="jetson.diagnosis", severity="info", occurred_at=datetime.now(timezone.utc),
        payload={**dispatch, "response": response},
    )
    settings = Settings(database_url="unused", tcad_poll_interval_seconds=0,
                        tcad_max_concurrent_jobs=1)
    store_ros_event(EventRepository(connection), event, request["run_id"], settings)
    return settings


class StatefulTransport:
    def __init__(self, terminal="succeeded", submit_status=202):
        self.terminal = terminal
        self.submit_status = submit_status
        self.requests = []
        self.polls = {}

    def __call__(self, request):
        self.requests.append((request.method, request.url.path))
        request_id = request.url.path.rsplit("/", 1)[-1]
        if request.method == "POST":
            body = __import__("json").loads(request.content)
            request_id = body["request_id"]
            if self.submit_status != 202:
                return httpx.Response(self.submit_status, json={"detail": "synthetic"})
            return httpx.Response(202, json={
                "request_id": request_id, "status": "queued", "queue_position": 1,
                "estimated_seconds": 5400, "accepted_at": "2026-10-21T12:00:00Z",
            })
        count = self.polls.get(request_id, 0) + 1
        self.polls[request_id] = count
        if count == 1:
            return httpx.Response(200, json={
                "request_id": request_id, "status": "running",
                "progress": {"stage": "iv", "stages": []},
            })
        if self.terminal == "succeeded":
            return httpx.Response(200, json={
                "request_id": request_id, "status": "succeeded",
                "result_payload": {"vth": 2.1, "gm": 10, "id_on": 20, "bv": 40},
                "metadata": {"result_origin": "mock"},
            })
        if self.terminal == "cancelled":
            return httpx.Response(200, json={
                "request_id": request_id, "status": "cancelled",
                "cancelled_at": "2026-10-21T12:01:00Z",
            })
        return httpx.Response(200, json={
            "request_id": request_id, "status": "failed", "result_payload": None,
            "error_code": "SILVACO_FAILED", "error_message": "failed",
        })


class LeaseStealingTransport(StatefulTransport):
    def __init__(self, connection):
        super().__init__()
        self.connection = connection

    def __call__(self, request):
        response = super().__call__(request)
        request_id = (
            __import__("json").loads(request.content)["request_id"]
            if request.method == "POST" else request.url.path.rsplit("/", 1)[-1]
        )
        self.connection.execute(
            "UPDATE tcad_verification_candidates SET lease_token=%s,"
            "lease_until=now()+interval '1 minute' WHERE tcad_request_id=%s",
            (uuid4(), request_id),
        )
        return response


def make_worker(connection, settings, transport):
    return TcadCandidateWorker(
        connection, settings,
        lambda url: httpx.Client(transport=httpx.MockTransport(transport), base_url=url),
    )


def test_worker_submits_and_polls_one_candidate_before_next(test_connection):
    settings = admit_two(test_connection)
    transport = StatefulTransport()
    worker = make_worker(test_connection, settings, transport)

    assert worker.run_once() == 1  # submit candidate 0
    assert test_connection.execute(
        "SELECT status FROM tcad_verification_candidates ORDER BY candidate_index"
    ).fetchall() == [("queued",), ("pending",)]
    assert worker.run_once() == 1  # poll candidate 0: running
    assert worker.run_once() == 1  # poll candidate 0: succeeded
    assert worker.run_once() == 1  # only now submit candidate 1

    assert [method for method, _ in transport.requests] == ["POST", "GET", "GET", "POST"]
    assert test_connection.execute(
        "SELECT status FROM tcad_verification_candidates ORDER BY candidate_index"
    ).fetchall() == [("succeeded",), ("queued",)]


def test_worker_aggregates_terminal_candidates_to_review_required(test_connection):
    settings = admit_two(test_connection)
    transport = StatefulTransport()
    worker = make_worker(test_connection, settings, transport)
    for _ in range(6):
        assert worker.run_once() == 1
    group = test_connection.execute(
        "SELECT status,terminal_count FROM tcad_proposal_groups"
    ).fetchone()
    assert group == ("review_required", 2)
    types = [row[0] for row in test_connection.execute(
        "SELECT event_type FROM events WHERE event_type LIKE 'tcad.verification.%' ORDER BY sequence"
    ).fetchall()]
    assert types.count("tcad.verification.candidate_succeeded") == 2
    assert types[-2:] == [
        "tcad.verification.batch_completed", "tcad.verification.review_required",
    ]


def test_worker_retries_server_error_without_losing_pending_candidate(test_connection):
    settings = admit_two(test_connection)
    worker = make_worker(test_connection, settings, StatefulTransport(submit_status=503))
    assert worker.run_once() == 1
    row = test_connection.execute(
        "SELECT status,last_error_code,lease_token FROM tcad_verification_candidates "
        "ORDER BY candidate_index LIMIT 1"
    ).fetchone()
    assert row == ("pending", "http_503", None)


def test_worker_expires_candidate_past_deadline_without_http(test_connection):
    settings = admit_two(test_connection)
    test_connection.execute(
        "UPDATE tcad_verification_candidates SET deadline_at=now()-interval '1 second'"
    )
    transport = StatefulTransport()
    worker = make_worker(test_connection, settings, transport)
    assert worker.run_once() == 1
    assert test_connection.execute(
        "SELECT count(*) FROM tcad_verification_candidates WHERE status='expired'"
    ).fetchone() == (2,)
    assert transport.requests == []


def test_worker_reclaims_expired_submitting_lease_with_same_post(test_connection):
    settings = admit_two(test_connection)
    request_id = test_connection.execute(
        "SELECT tcad_request_id FROM tcad_verification_candidates ORDER BY candidate_index LIMIT 1"
    ).fetchone()[0]
    test_connection.execute(
        "UPDATE tcad_verification_candidates SET status='submitting',lease_token=%s,"
        "lease_until=now()-interval '1 second' WHERE tcad_request_id=%s",
        (uuid4(), request_id),
    )
    transport = StatefulTransport()
    worker = make_worker(test_connection, settings, transport)

    assert worker.run_once() == 1
    assert transport.requests == [("POST", "/api/v1/tcad/verify")]
    assert test_connection.execute(
        "SELECT status FROM tcad_verification_candidates WHERE tcad_request_id=%s",
        (request_id,),
    ).fetchone() == ("queued",)


def test_expiry_emits_correlated_events_once(test_connection):
    settings = admit_two(test_connection)
    test_connection.execute(
        "UPDATE tcad_verification_candidates SET deadline_at=now()-interval '1 second'"
    )
    worker = make_worker(test_connection, settings, StatefulTransport())

    assert worker.run_once() == 1
    assert worker.run_once() == 0
    rows = test_connection.execute(
        "SELECT event_type,payload FROM events WHERE event_type LIKE 'tcad.verification.%' "
        "ORDER BY sequence"
    ).fetchall()
    assert [row[0] for row in rows].count("tcad.verification.candidate_expired") == 2
    assert [row[0] for row in rows].count("tcad.verification.batch_completed") == 1
    for _, payload in rows:
        assert payload["job_id"]


def test_lost_lease_does_not_emit_or_commit_acceptance(test_connection):
    settings = admit_two(test_connection)
    worker = make_worker(test_connection, settings, LeaseStealingTransport(test_connection))

    assert worker.run_once() == 1
    assert test_connection.execute(
        "SELECT count(*) FROM events WHERE event_type='tcad.verification.candidate_queued'"
    ).fetchone() == (0,)
    assert test_connection.execute(
        "SELECT status FROM tcad_verification_candidates ORDER BY candidate_index LIMIT 1"
    ).fetchone() == ("submitting",)


def test_lost_lease_does_not_emit_or_commit_poll_transition(test_connection):
    settings = admit_two(test_connection)
    normal = make_worker(test_connection, settings, StatefulTransport())
    assert normal.run_once() == 1
    stale = make_worker(test_connection, settings, LeaseStealingTransport(test_connection))

    assert stale.run_once() == 1
    assert test_connection.execute(
        "SELECT count(*) FROM events WHERE event_type='tcad.verification.candidate_running'"
    ).fetchone() == (0,)
    assert test_connection.execute(
        "SELECT status FROM tcad_verification_candidates ORDER BY candidate_index LIMIT 1"
    ).fetchone() == ("queued",)


def test_batch_terminal_events_are_emitted_once(test_connection):
    settings = admit_two(test_connection)
    worker = make_worker(test_connection, settings, StatefulTransport())
    for _ in range(6):
        worker.run_once()
    proposal_id, run_id, request_id = test_connection.execute(
        "SELECT proposal_id,run_id,original_request_id FROM tcad_proposal_groups"
    ).fetchone()

    with test_connection.transaction():
        worker._aggregate_group(proposal_id, run_id, request_id)
    assert test_connection.execute(
        "SELECT count(*) FROM events WHERE event_type='tcad.verification.batch_completed'"
    ).fetchone() == (1,)
    assert test_connection.execute(
        "SELECT count(*) FROM events WHERE event_type='tcad.verification.review_required'"
    ).fetchone() == (1,)


def test_worker_recovers_409_by_polling_same_request(test_connection):
    settings = admit_two(test_connection)
    transport = StatefulTransport(submit_status=409)
    worker = make_worker(test_connection, settings, transport)

    assert worker.run_once() == 1
    transport.submit_status = 202
    assert worker.run_once() == 1
    assert [method for method, _ in transport.requests] == ["POST", "GET"]


def test_worker_retries_429_but_fails_400(test_connection):
    settings = admit_two(test_connection)
    retry_worker = make_worker(test_connection, settings, StatefulTransport(submit_status=429))
    assert retry_worker.run_once() == 1
    assert test_connection.execute(
        "SELECT status,last_error_code FROM tcad_verification_candidates "
        "ORDER BY candidate_index LIMIT 1"
    ).fetchone() == ("pending", "http_429")

    test_connection.execute(
        "UPDATE tcad_verification_candidates SET next_attempt_at=now() WHERE candidate_index=0"
    )
    fail_worker = make_worker(test_connection, settings, StatefulTransport(submit_status=400))
    assert fail_worker.run_once() == 1
    assert test_connection.execute(
        "SELECT status,last_error_code FROM tcad_verification_candidates "
        "ORDER BY candidate_index LIMIT 1"
    ).fetchone() == ("failed", "http_400")


def test_two_worker_connections_enforce_global_concurrency_limit(test_connection):
    settings = admit_two(test_connection)
    schema = test_connection.execute("SELECT current_schema()").fetchone()[0]
    test_connection.execute("""
        CREATE FUNCTION slow_tcad_claim() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM pg_sleep(0.5);
          RETURN NEW;
        END $$
    """)
    test_connection.execute("""
        CREATE TRIGGER slow_tcad_claim_trigger
        BEFORE UPDATE OF status ON tcad_verification_candidates
        FOR EACH ROW WHEN (OLD.status='pending' AND NEW.status='submitting')
        EXECUTE FUNCTION slow_tcad_claim()
    """)

    database_url = Settings.load(ROOT / ".env").test_database_url
    def claim_once():
        with psycopg.connect(
            database_url, autocommit=True, options=f"-c search_path={schema}"
        ) as connection:
            return TcadCandidateWorker(connection, settings)._claim()

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(lambda _: claim_once(), range(2)))

    assert sum(claim is not None for claim in claims) == 1
    assert test_connection.execute(
        "SELECT count(*) FROM tcad_verification_candidates WHERE status='submitting'"
    ).fetchone() == (1,)
