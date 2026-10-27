from pathlib import Path
from uuid import uuid4

import pytest
from psycopg.types.json import Jsonb

from event_gateway.commands import approve_proposal, ApprovalConflict
from event_gateway.migrate import apply_migrations


ROOT = Path(__file__).parents[4]


def test_only_verified_proposal_can_create_one_command(test_connection):
    connection = test_connection
    apply_migrations(connection, ROOT / "database/migrations")
    run_id, event_id, proposal_id = uuid4(), uuid4(), uuid4()
    connection.execute(
        "INSERT INTO integration_runs(run_id,tcad_mode,unity_mode,input_origin,baseline_version) "
        "VALUES (%s,'mock','mock','synthetic','demo-v1')", (run_id,))
    connection.execute(
        "INSERT INTO events(run_id,event_id,schema_version,event_type,source,severity,payload,occurred_at) "
        "VALUES (%s,%s,1,'correction.proposed','test','info','{}',now())",
        (run_id, event_id))
    vector = {key: 1.0 for key in ("oxide_thickness", "body_dose", "diffusion_time", "epi_doping")}
    connection.execute(
        "INSERT INTO correction_proposals(proposal_id,run_id,source_event_id,representation,"
        "x_current,delta_x,x_candidate,y_observed,targets) "
        "VALUES (%s,%s,%s,'normalized_ratio',%s,%s,%s,'{}','{}')",
        (proposal_id, run_id, event_id, Jsonb(vector),
         Jsonb({key: 0 for key in vector}), Jsonb(vector)))
    with pytest.raises(ApprovalConflict):
        approve_proposal(connection, proposal_id, "operator", "LOT-2")
    connection.execute(
        "UPDATE correction_proposals SET status='verified',y_verified='{}',result_origin='mock' "
        "WHERE proposal_id=%s", (proposal_id,))
    first = approve_proposal(connection, proposal_id, "operator", "LOT-2")
    second = approve_proposal(connection, proposal_id, "operator", "LOT-2")
    assert first == second
    assert connection.execute("SELECT count(*) FROM commands").fetchone() == (1,)
    with pytest.raises(ApprovalConflict):
        approve_proposal(connection, proposal_id, "other", "LOT-3")
