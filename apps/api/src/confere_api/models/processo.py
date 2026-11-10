"""MODEL: processo (job de importação) e suas referências (CF-101)."""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base, TenantMixin, TimestampMixin
from confere_api.db.tipos import enum_texto, pk_uuid

MODAIS = ("maritimo", "aereo", "rodoviario")
STATUS_PROCESSO = ("aberto", "faturado", "encerrado")
TIPOS_REFERENCIA = ("bl_master", "bl_house", "conteiner", "ref_cliente", "ref_agente")
ORIGENS_REFERENCIA = ("cadastro", "correcao")


class Processo(Base, TenantMixin, TimestampMixin):
    __tablename__ = "processo"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo", name="uq_processo_empresa_codigo"),)

    id: Mapped[uuid.UUID] = pk_uuid()
    codigo: Mapped[str] = mapped_column(String(40))
    cliente: Mapped[str] = mapped_column(String(200))
    modal: Mapped[str] = mapped_column(enum_texto("modal", MODAIS))
    origem: Mapped[str] = mapped_column(String(100))
    destino: Mapped[str] = mapped_column(String(100))
    navio: Mapped[str | None] = mapped_column(String(100))
    viagem: Mapped[str | None] = mapped_column(String(40))
    etd: Mapped[date | None] = mapped_column(Date)
    eta: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        enum_texto("status", STATUS_PROCESSO), default="aberto", server_default="aberto"
    )


class ProcessoReferencia(Base, TenantMixin, TimestampMixin):
    __tablename__ = "processo_referencia"
    __table_args__ = (
        Index("ix_processo_referencia_empresa_valor", "empresa_id", "valor_normalizado"),
        # Busca aproximada (fuzzy) por trigramas, usada pela resolução de processo (CF-58).
        Index(
            "ix_processo_referencia_valor_trgm",
            "valor_normalizado",
            postgresql_using="gin",
            postgresql_ops={"valor_normalizado": "gin_trgm_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = pk_uuid()
    processo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("processo.id", ondelete="CASCADE"), index=True
    )
    tipo: Mapped[str] = mapped_column(enum_texto("tipo", TIPOS_REFERENCIA))
    valor: Mapped[str] = mapped_column(String(100))
    valor_normalizado: Mapped[str] = mapped_column(String(100))
    origem: Mapped[str] = mapped_column(
        enum_texto("origem", ORIGENS_REFERENCIA), default="cadastro", server_default="cadastro"
    )
