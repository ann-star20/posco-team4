from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from event_gateway.config import Settings


ROOT = Path(__file__).parents[4]


@pytest.fixture
def test_connection():
    settings = Settings.load(ROOT / ".env")
    if not settings.test_database_url:
        pytest.fail("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    schema = "test_" + uuid4().hex
    try:
        with psycopg.connect(settings.test_database_url, autocommit=True) as admin:
            admin.execute(f'CREATE SCHEMA "{schema}"')
    except psycopg.OperationalError:
        pytest.fail("전용 PostgreSQL 테스트 DB에 연결할 수 없습니다.", pytrace=False)
    try:
        try:
            with psycopg.connect(settings.test_database_url, autocommit=True,
                                 options=f"-c search_path={schema}") as connection:
                yield connection
        except psycopg.OperationalError:
            pytest.fail("전용 PostgreSQL 테스트 DB 연결이 끊겼습니다.", pytrace=False)
    finally:
        try:
            with psycopg.connect(settings.test_database_url, autocommit=True) as admin:
                admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        except psycopg.OperationalError:
            pytest.fail("테스트 스키마 정리에 실패했습니다.", pytrace=False)
