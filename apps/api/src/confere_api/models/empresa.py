"""MODEL: empresa (tenant) e usuário (CF-101)."""

import uuid
from typing import Any

import yaml
from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base, TenantMixin, TimestampMixin
from confere_api.db.tipos import enum_texto, pk_uuid
from confere_api.settings import RAIZ

PAPEIS = ("ap", "operacional", "gestor")
CAMINHO_POLITICA_PADRAO = RAIZ / "config" / "politica_padrao.yaml"


def politica_padrao() -> dict[str, Any]:
    """Política de uma empresa nova, de `config/politica_padrao.yaml`."""
    with open(CAMINHO_POLITICA_PADRAO, encoding="utf-8") as arquivo:
        dados: dict[str, Any] = yaml.safe_load(arquivo)
    return dados


class Empresa(Base, TimestampMixin):
    """Não tem `empresa_id`: é a raiz do tenant."""

    __tablename__ = "empresa"

    id: Mapped[uuid.UUID] = pk_uuid()
    nome: Mapped[str] = mapped_column(String(200))
    cnpj_ficticio: Mapped[str] = mapped_column(String(18))
    politica_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=politica_padrao)


class Usuario(Base, TenantMixin, TimestampMixin):
    __tablename__ = "usuario"
    __table_args__ = (UniqueConstraint("empresa_id", "email", name="uq_usuario_empresa_email"),)

    id: Mapped[uuid.UUID] = pk_uuid()
    email: Mapped[str] = mapped_column(String(200))
    nome: Mapped[str] = mapped_column(String(200))
    papel: Mapped[str] = mapped_column(enum_texto("papel", PAPEIS))
