"""Tipos de coluna compartilhados pelos models."""

import uuid
from decimal import Decimal

from sqlalchemy import Enum, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm.properties import MappedColumn


def enum_texto(nome: str, valores: tuple[str, ...], tamanho: int = 20) -> Enum:
    """Enum guardado como VARCHAR + CHECK (mais fácil de migrar que enum nativo do Postgres)."""
    return Enum(
        *valores,
        name=nome,
        native_enum=False,
        length=tamanho,
        create_constraint=True,
        validate_strings=True,
    )


def dinheiro() -> Numeric[Decimal]:
    return Numeric(14, 2, asdecimal=True)


def pk_uuid() -> MappedColumn[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
