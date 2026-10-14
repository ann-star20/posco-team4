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
    with psycopg.connect(settings.test_database_url, autocommit=True) as admin:
        admin.execute(f'CREATE SCHEMA "{schema}"')
    try:
        with psycopg.connect(settings.test_database_url, autocommit=True,
                             options=f"-c search_path={schema}") as connection:
            yield connection
    finally:
        with psycopg.connect(settings.test_database_url, autocommit=True) as admin:
            admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
