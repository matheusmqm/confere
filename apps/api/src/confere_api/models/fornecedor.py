"""MODEL: fornecedor e seus aliases (CF-101)."""

import uuid

from sqlalchemy import CHAR, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base, TenantMixin, TimestampMixin
from confere_api.db.tipos import enum_texto, pk_uuid

TIPOS_FORNECEDOR = (
    "armador",
    "agente_exterior",
    "terminal",
    "armazem",
    "transportadora",
    "despachante",
)


class Fornecedor(Base, TenantMixin, TimestampMixin):
    __tablename__ = "fornecedor"
    __table_args__ = (UniqueConstraint("empresa_id", "nome", name="uq_fornecedor_empresa_nome"),)

    id: Mapped[uuid.UUID] = pk_uuid()
    nome: Mapped[str] = mapped_column(String(200))
    tipo: Mapped[str] = mapped_column(enum_texto("tipo", TIPOS_FORNECEDOR))
    pais: Mapped[str] = mapped_column(CHAR(2))
    moeda_padrao: Mapped[str] = mapped_column(CHAR(3))
    dominio_email: Mapped[str] = mapped_column(String(200))
    idioma: Mapped[str] = mapped_column(CHAR(2))


class FornecedorAlias(Base, TenantMixin, TimestampMixin):
    __tablename__ = "fornecedor_alias"

    id: Mapped[uuid.UUID] = pk_uuid()
    fornecedor_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("fornecedor.id", ondelete="CASCADE"), index=True
    )
    alias: Mapped[str] = mapped_column(String(200))
    alias_normalizado: Mapped[str] = mapped_column(String(200), index=True)
