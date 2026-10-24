from pathlib import Path


ROOT = Path(__file__).parents[4]
MIGRATION = ROOT / "database/migrations/010_create_tcad_candidate_queue.sql"


def test_tcad_candidate_migration_defines_durable_queue_contract():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE tcad_proposal_groups" in sql
    assert "CREATE TABLE tcad_verification_candidates" in sql
    assert "source_event_id UUID NOT NULL UNIQUE" in sql
    assert "UNIQUE(proposal_id, candidate_index)" in sql
    assert "tcad_request_id UUID PRIMARY KEY" in sql
    assert "status IN ('queued','running','completed','failed','cancelled','review_required')" in sql
    assert "status IN ('pending','submitting','queued','running','succeeded','failed','cancelled','expired')" in sql
    assert "jsonb_typeof(process_parameters) = 'object'" in sql
    assert "jsonb_typeof(predicted_outputs) = 'object'" in sql
    assert "jsonb_typeof(requested_outputs) = 'array'" in sql
    assert "CHECK ((lease_token IS NULL) = (lease_until IS NULL))" in sql
    assert "WHERE status IN ('pending','submitting','queued','running')" in sql
    assert "selected_tcad_request_id" in sql
    assert "ADD COLUMN tcad_proposal_group_id UUID" in sql
