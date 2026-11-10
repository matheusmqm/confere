"""Engine e sessão SQLAlchemy (síncronos)."""

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from confere_api.settings import get_settings

PORTA_POOLER_TRANSACTION = 6543


def make_engine(url: str) -> Engine:
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if make_url(url).port == PORTA_POOLER_TRANSACTION:
        # Pooler em modo transaction: sem pool local e sem prepared statements.
        kwargs["poolclass"] = NullPool
        kwargs["connect_args"] = {"prepare_threshold": None}
    return create_engine(url, **kwargs)


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings().database_url.get_secret_value())


SessionLocal = sessionmaker(autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal(bind=get_engine()) as session:
        yield session
