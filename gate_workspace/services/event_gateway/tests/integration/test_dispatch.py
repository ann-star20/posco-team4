from pathlib import Path
from uuid import uuid4

from psycopg.types.json import Jsonb

from event_gateway.command_dispatcher import claim_due_commands
from event_gateway.migrate import apply_migrations


ROOT = Path(__file__).parents[4]


def test_dispatch_is_due_based_and_recoverable(test_connection):
    connection = test_connection
    apply_migrations(connection, ROOT / "database/migrations")
    run_id, event_id, proposal_id, command_id = (uuid4() for _ in range(4))
    connection.execute(
        "INSERT INTO integration_runs(run_id,tcad_mode,unity_mode,input_origin,baseline_version) "
        "VALUES (%s,'mock','mock','synthetic','demo-v1')", (run_id,))
    connection.execute(
        "INSERT INTO events(run_id,event_id,schema_version,event_type,source,severity,payload,occurred_at) "
        "VALUES (%s,%s,1,'correction.proposed','test','info','{}',now())", (run_id, event_id))
    connection.execute(
        "INSERT INTO correction_proposals(proposal_id,run_id,source_event_id,representation,"
        "x_current,delta_x,x_candidate,y_observed,targets) "
        "VALUES (%s,%s,%s,'normalized_ratio','{}','{}','{}','{}','{}')",
        (proposal_id, run_id, event_id))
    connection.execute(
        "INSERT INTO commands(command_id,proposal_id,run_id,scope,effective_from_lot,payload) "
        "VALUES (%s,%s,%s,'simulation','LOT-2',%s)",
        (command_id, proposal_id, run_id, Jsonb({"command_id": str(command_id)})))
    first = claim_due_commands(connection)
    assert first == [{"command_id": str(command_id)}]
    assert claim_due_commands(connection) == []
    connection.execute(
        "UPDATE commands SET next_attempt_at=now()-interval '1 second' WHERE command_id=%s",
        (command_id,))
    assert claim_due_commands(connection) == first
