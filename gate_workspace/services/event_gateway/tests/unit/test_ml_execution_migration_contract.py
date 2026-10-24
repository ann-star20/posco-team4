from pathlib import Path


def test_followup_migration_allows_multiple_worker_executions():
    path = Path(__file__).parents[4] / "database/migrations/009_ml_execution_attempts.sql"
    sql = path.read_text(encoding="utf-8")
    assert "ADD COLUMN execution_attempt" in sql
    assert "UNIQUE(job_id, attempt, execution_attempt)" in sql
