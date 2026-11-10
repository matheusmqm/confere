"""MODEL: eventos do pipeline (trilha de auditoria e fonte do SSE) e chamadas ao LLM (CF-103)."""

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base, TenantMixin, TimestampMixin
from confere_api.db.tipos import enum_texto, pk_uuid

ETAPAS_EVENTO = (
    "recebido",
    "lido",
    "extraido",
    "processo",
    "codigos",
    "casado",
    "decidido",
    "reconferido",
    "erro",
)
STATUS_EVENTO = ("ok", "aviso", "erro")


class Evento(Base, TenantMixin, TimestampMixin):
    __tablename__ = "evento"
    # O SSE lê "eventos da empresa depois do id X".
    __table_args__ = (Index("ix_evento_empresa_id_id", "empresa_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("job.id", ondelete="SET NULL"))
    documento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documento.id", ondelete="SET NULL")
    )
    etapa: Mapped[str] = mapped_column(enum_texto("etapa", ETAPAS_EVENTO))
    status: Mapped[str] = mapped_column(enum_texto("status", STATUS_EVENTO))
    mensagem: Mapped[str] = mapped_column(Text)
    dados_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class LLMCall(Base, TenantMixin, TimestampMixin):
    __tablename__ = "llm_call"

    id: Mapped[uuid.UUID] = pk_uuid()
    documento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documento.id", ondelete="SET NULL")
    )
    etapa: Mapped[str] = mapped_column(String(30))
    modelo: Mapped[str] = mapped_column(String(80))
    prompt_id: Mapped[str] = mapped_column(String(80))
    prompt_versao: Mapped[int] = mapped_column(Integer)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    custo_usd: Mapped[Decimal] = mapped_column(Numeric(12, 6, asdecimal=True), default=Decimal(0))
    latencia_ms: Mapped[int] = mapped_column(Integer, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
