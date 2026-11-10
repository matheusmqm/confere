"""Migrações sobem e descem contra o banco `confere_test`."""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from confere_api.settings import get_settings

URL_TESTE = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://confere:confere@localhost:5432/confere_test"
)
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
EXTENSOES = {"vector", "pg_trgm", "unaccent"}

pytestmark = pytest.mark.db


@pytest.fixture
def cfg(monkeypatch: pytest.MonkeyPatch) -> Iterator[Config]:
    monkeypatch.setenv("DATABASE_URL_WORKER", URL_TESTE)
    get_settings.cache_clear()
    yield Config(str(ALEMBIC_INI))
    get_settings.cache_clear()


def test_upgrade_head_e_downgrade_base(cfg: Config) -> None:
    engine = create_engine(URL_TESTE)
    try:
        command.upgrade(cfg, "head")
        with engine.connect() as conn:
            extensoes = set(conn.scalars(text("select extname from pg_extension")))
            versao = conn.scalar(text("select version_num from alembic_version"))
        assert extensoes >= EXTENSOES
        assert versao == "0001"

        command.downgrade(cfg, "base")
        with engine.connect() as conn:
            assert conn.scalar(text("select count(*) from alembic_version")) == 0
            extensoes = set(conn.scalars(text("select extname from pg_extension")))
        assert extensoes >= EXTENSOES  # downgrade não remove extensões
    finally:
        engine.dispose()
