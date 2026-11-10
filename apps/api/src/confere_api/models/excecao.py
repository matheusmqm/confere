"""MODEL: exceção (achado que pede atenção) e a decisão humana sobre ela (CF-102)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base, TenantMixin, TimestampMixin
from confere_api.db.tipos import dinheiro, enum_texto, pk_uuid

TIPOS_EXCECAO = (
    "acima_tolerancia",
    "sem_provisao",
    "duplicada",
    "cambio_divergente",
    "provisao_sem_fatura",
    "sem_processo",
    "confirmar_processo",
    "codigo_incerto",
    "extracao_inconsistente",
    "documento_protegido",
    "moeda_sem_cotacao",
    "possivel_duplicata_exata",
)
SEVERIDADES = ("info", "revisar", "bloquear")
STATUS_EXCECAO = ("aberta", "resolvida", "descartada")
ACOES_DECISAO = (
    "aprovar",
    "contestar",
    "corrigir_processo",
    "corrigir_codigo",
    "repassar",
    "bloquear",
)


class Excecao(Base, TenantMixin, TimestampMixin):
    __tablename__ = "excecao"
    __table_args__ = (
        Index(
            "ix_excecao_empresa_status_valor",
            "empresa_id",
            "status",
            text("valor_brl_em_risco DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = pk_uuid()
    documento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documento.id", ondelete="CASCADE"), index=True
    )
    linha_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("linha.id", ondelete="CASCADE"))
    provisao_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("provisao.id"))
    tipo: Mapped[str] = mapped_column(enum_texto("tipo", TIPOS_EXCECAO, tamanho=30))
    severidade: Mapped[str] = mapped_column(enum_texto("severidade", SEVERIDADES))
    valor_brl_em_risco: Mapped[Decimal] = mapped_column(
        dinheiro(), default=Decimal("0.00"), server_default="0"
    )
    explicacao: Mapped[str | None] = mapped_column(Text)
    explicacao_origem: Mapped[str | None] = mapped_column(String(20))  # ex. llm | template
    acao_sugerida: Mapped[str | None] = mapped_column(Text)
    dados_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        enum_texto("status", STATUS_EXCECAO), default="aberta", server_default="aberta"
    )
    resolvida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Decisao(Base, TenantMixin, TimestampMixin):
    __tablename__ = "decisao"

    id: Mapped[uuid.UUID] = pk_uuid()
    excecao_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("excecao.id"))
    documento_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documento.id"), index=True)
    usuario_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("usuario.id"))
    acao: Mapped[str] = mapped_column(enum_texto("acao", ACOES_DECISAO))
    comentario: Mapped[str | None] = mapped_column(Text)
    dados_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
