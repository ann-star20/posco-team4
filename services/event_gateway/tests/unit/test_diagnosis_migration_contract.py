from pathlib import Path


def test_diagnosis_migration_defines_results_and_attempt_metrics():
    path = Path(__file__).parents[4] / "database/migrations/008_diagnosis_and_ml_executions.sql"
    sql = path.read_text(encoding="utf-8")
    assert "CREATE TABLE diagnosis_results" in sql
    assert "CREATE TABLE ml_inference_executions" in sql
    assert "task_type IN ('aoi','surrogate','diagnosis')" in sql
    assert "compensation_route IN ('tcad_verify','no_action','manual')" in sql
    assert "UNIQUE(job_id, attempt)" in sql
    assert "stage_metrics JSONB" in sql
