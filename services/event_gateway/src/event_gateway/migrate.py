"""Apply numbered SQL migrations without deleting existing data."""

from hashlib import sha256
from pathlib import Path

import psycopg

from .config import Settings


EXPECTED_001_COLUMNS = {
    "sequence", "event_id", "schema_version", "event_type", "source", "severity",
    "correlation_id", "causation_id", "payload", "occurred_at", "received_at",
}
EXPECTED_001_INDEXES = {
    "events_pkey", "events_event_id_key", "events_type_sequence_idx",
    "events_correlation_sequence_idx", "events_occurred_at_idx",
}
EXPECTED_001_CONSTRAINTS = {
    "events_pkey", "events_event_id_key", "events_schema_version_check",
    "events_severity_check",
}


def adopt_existing_001(connection: psycopg.Connection, directory: Path) -> None:
    """Record a pre-existing 001 table only after strict structural checks."""
    path = directory / "001_create_events.sql"
    columns = {
        row[0]: row[1:] for row in connection.execute(
            "SELECT column_name,data_type,is_nullable,is_identity "
            "FROM information_schema.columns WHERE table_schema=current_schema() "
            "AND table_name='events'"
        ).fetchall()
    }
    indexes = {row[0] for row in connection.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname=current_schema() "
        "AND tablename='events'"
    ).fetchall()}
    constraints = {row[0] for row in connection.execute(
        "SELECT conname FROM pg_constraint WHERE conrelid='events'::regclass"
    ).fetchall()}
    if (set(columns) != EXPECTED_001_COLUMNS
            or not EXPECTED_001_INDEXES <= indexes
            or not EXPECTED_001_CONSTRAINTS <= constraints
            or columns["sequence"] != ("bigint", "NO", "YES")
            or columns["payload"][:2] != ("jsonb", "NO")
            or columns["occurred_at"][:2] != ("timestamp with time zone", "NO")
            or columns["received_at"][:2] != ("timestamp with time zone", "NO")):
        raise ValueError("existing events table does not match migration 001")
    checksum = sha256(path.read_bytes()).hexdigest()
    with connection.transaction():
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations("
            "version TEXT PRIMARY KEY,checksum TEXT NOT NULL,"
            "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        connection.execute(
            "INSERT INTO schema_migrations(version,checksum) VALUES (%s,%s) "
            "ON CONFLICT (version) DO NOTHING", (path.name, checksum),
        )
        row = connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version=%s", (path.name,)
        ).fetchone()
        if row[0] != checksum:
            raise ValueError("migration 001 checksum differs")


def apply_migrations(connection: psycopg.Connection, directory: Path, start_at: int = 1) -> list[str]:
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations("
        "version TEXT PRIMARY KEY, checksum TEXT NOT NULL, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
    )
    applied: list[str] = []
    for path in sorted(directory.glob("[0-9][0-9][0-9]_*.sql")):
        if int(path.name[:3]) < start_at:
            continue
        raw_sql = path.read_bytes()
        sql = raw_sql.decode("utf-8")
        checksum = sha256(raw_sql).hexdigest()
        row = connection.execute(
            "SELECT checksum FROM schema_migrations WHERE version=%s", (path.name,)
        ).fetchone()
        if row:
            if row[0] != checksum:
                raise ValueError(f"migration checksum changed: {path.name}")
            continue
        with connection.transaction():
            connection.execute(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version,checksum) VALUES (%s,%s)",
                (path.name, checksum),
            )
        applied.append(path.name)
    return applied


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="비파괴 PostgreSQL 스키마 마이그레이션")
    parser.add_argument("--apply", action="store_true", help="미적용 SQL을 실제 적용")
    parser.add_argument("--adopt-existing-001", action="store_true",
                        help="기존 001 구조를 검증하여 이력 기준선으로 기록")
    args = parser.parse_args()
    settings = Settings.load(Path(".env"))
    directory = Path(__file__).resolve().parents[4] / "database" / "migrations"
    with psycopg.connect(settings.database_url, autocommit=True) as connection:
        existing = connection.execute(
            "SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' "
            "ORDER BY tablename"
        ).fetchall()
        print("기존 테이블:", ", ".join(row[0] for row in existing) or "없음")
        if args.adopt_existing_001:
            adopt_existing_001(connection, directory)
            print("001 기존 구조를 검증해 이력에 기록했습니다.")
        if args.apply:
            print("적용:", ", ".join(apply_migrations(connection, directory)) or "변경 없음")
        else:
            print("읽기 전용 점검입니다. 적용하려면 --apply를 지정하세요.")


if __name__ == "__main__":
    main()
