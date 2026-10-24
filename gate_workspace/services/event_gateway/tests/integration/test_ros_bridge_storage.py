import json
from pathlib import Path
from uuid import uuid4

from event_gateway.config import Settings
from event_gateway.migrate import apply_migrations
from event_gateway.repository import EventRepository
from event_gateway.ros_adapter import RosEventAdapter, store_ros_event
from fab_virtual_lot.publisher import make_demo_proposal


ROOT = Path(__file__).parents[4]


def test_ros_proposal_creates_one_job_and_reuses_pinned_mode(test_connection):
    connection = test_connection
    apply_migrations(connection, ROOT / "database/migrations")
    repository = EventRepository(connection)
    run_id = uuid4()
    raw = json.dumps(make_demo_proposal(run_id))
    accepted = []
    adapter = RosEventAdapter(accepted.append, lambda error: None)
    assert adapter.receive(raw)
    event, parsed_run, _ = accepted[0]
    first_settings = Settings(database_url="unused", tcad_mode="mock", unity_mode="mock",
                              tcad_mock_url="http://mock.test")
    first = store_ros_event(repository, event, parsed_run, first_settings)
    second_settings = Settings(database_url="unused", tcad_mode="prod", unity_mode="prod",
                               tcad_mock_url="http://mock.test",
                               tcad_prod_url="http://prod.test")
    repeated = store_ros_event(repository, event, parsed_run, second_settings)
    assert first == repeated
    assert connection.execute("SELECT count(*) FROM correction_proposals").fetchone() == (1,)
    assert connection.execute(
        "SELECT tcad_mode,endpoint_url FROM verification_jobs"
    ).fetchone() == ("mock", "http://mock.test")
