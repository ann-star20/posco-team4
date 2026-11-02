from pathlib import Path


ROOT = Path(__file__).parents[4]
MIGRATION = ROOT / "database/migrations/013_capa_sessions.sql"


def test_capa_sessions_migration_defines_registration_tables():
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE factory_sessions" in sql
    assert "CREATE TABLE factory_session_equipment" in sql
    assert "CREATE TABLE factory_lots" in sql
    assert "status IN ('active','ended')" in sql
    assert "CHECK ((status = 'ended') = (ended_at IS NOT NULL))" in sql
    assert "PRIMARY KEY (factory_session_id, equipment_id)" in sql
    assert (
        "equipment_kind IN ('oxidation','film_inspection','ion_implant','aoi','oht','stocker')"
        in sql
    )
    assert "lot_kind IN ('wafer_route','aoi_product')" in sql
    assert "PRIMARY KEY (factory_session_id, lot_id)" in sql
    assert "representative_wafer_id IS NOT NULL AND product_id IS NULL" in sql
    assert "product_id IS NOT NULL AND representative_wafer_id IS NULL" in sql
