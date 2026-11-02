from pathlib import Path


ROOT = Path(__file__).parents[4]
MIGRATION = ROOT / "database/migrations/014_capa_state_versions.sql"


def test_capa_state_versions_migration_defines_version_tracking_table():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE factory_object_versions" in sql
    assert "state_version INTEGER NOT NULL CHECK (state_version > 0)" in sql
    assert "last_event_id UUID NOT NULL REFERENCES events(event_id)" in sql
    assert "PRIMARY KEY (factory_session_id, object_key)" in sql
