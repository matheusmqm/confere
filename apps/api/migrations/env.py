"""Ambiente do Alembic: migrações rodam na conexão direta/session (database_url_worker)."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import confere_api.models  # noqa: F401  (registra os models em Base.metadata)
from confere_api.db.base import Base
from confere_api.settings import get_settings

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
target_metadata = Base.metadata


def _url() -> str:
    return get_settings().database_url_worker.get_secret_value()


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
