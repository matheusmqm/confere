"""MODEL: fila de jobs do worker (CF-103)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base, TenantMixin, TimestampMixin
from confere_api.db.tipos import enum_texto, pk_uuid

TIPOS_JOB = ("processar", "reprocessar", "reset_demo")
STATUS_JOB = ("pendente", "executando", "feito", "falhou")


class Job(Base, TenantMixin, TimestampMixin):
    __tablename__ = "job"
    __table_args__ = (
        # A consulta do worker só olha jobs pendentes: índice parcial pequeno.
        Index(
            "ix_job_pendente_executar_apos",
            "executar_apos",
            postgresql_where=text("status = 'pendente'"),
        ),
    )

    id: Mapped[uuid.UUID] = pk_uuid()
    tipo: Mapped[str] = mapped_column(enum_texto("tipo", TIPOS_JOB))
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        enum_texto("status", STATUS_JOB), default="pendente", server_default="pendente"
    )
    tentativas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    max_tentativas: Mapped[int] = mapped_column(Integer, default=3, server_default="3")
    executar_apos: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    erro: Mapped[str | None] = mapped_column(Text)
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    terminado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
