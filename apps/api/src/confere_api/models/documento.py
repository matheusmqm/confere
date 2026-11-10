"""MODEL: documento e suas linhas (CF-102)."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base, TenantMixin, TimestampMixin
from confere_api.db.tipos import dinheiro, enum_texto, pk_uuid

TIPOS_DOCUMENTO = (
    "fatura",
    "nota_debito",
    "extrato",
    "cte",
    "bl",
    "aviso_chegada",
    "outro",
    "desconhecido",
)
TIPOS_ARQUIVO = ("pdf", "png", "jpg", "xml")
STATUS_DOCUMENTO = (
    "recebido",
    "processando",
    "aprovado_auto",
    "em_revisao",
    "bloqueado",
    "erro_arquivo",
    "separado",
    "arquivado",
    "aprovado_manual",  # aprovação humana (separada da `aprovado_auto` nas métricas)
)
ESTADOS_LINHA = (
    "ok",
    "acima_tolerancia",
    "abaixo_previsto",
    "sem_provisao",
    "duplicada",
    "cambio_divergente",
    "pendente",
)


def _confianca() -> Numeric[Decimal]:
    return Numeric(5, 4, asdecimal=True)


class Documento(Base, TenantMixin, TimestampMixin):
    __tablename__ = "documento"
    __table_args__ = (Index("ix_documento_empresa_sha256", "empresa_id", "sha256"),)

    id: Mapped[uuid.UUID] = pk_uuid()
    tipo: Mapped[str] = mapped_column(
        enum_texto("tipo", TIPOS_DOCUMENTO), default="desconhecido", server_default="desconhecido"
    )
    arquivo_path: Mapped[str | None] = mapped_column(Text)
    nome_original: Mapped[str] = mapped_column(Text)
    tipo_arquivo: Mapped[str | None] = mapped_column(enum_texto("tipo_arquivo", TIPOS_ARQUIVO))
    sha256: Mapped[str | None] = mapped_column(CHAR(64))
    remetente: Mapped[str | None] = mapped_column(String(200))
    fornecedor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fornecedor.id"))
    numero: Mapped[str | None] = mapped_column(String(80))
    numero_normalizado: Mapped[str | None] = mapped_column(String(80))
    emissao: Mapped[date | None] = mapped_column(Date)
    vencimento: Mapped[date | None] = mapped_column(Date)
    moeda: Mapped[str | None] = mapped_column(CHAR(3))
    total: Mapped[Decimal | None] = mapped_column(dinheiro())
    status: Mapped[str] = mapped_column(
        enum_texto("status", STATUS_DOCUMENTO), default="recebido", server_default="recebido"
    )
    confianca: Mapped[Decimal | None] = mapped_column(_confianca())
    score_decisao: Mapped[Decimal | None] = mapped_column(_confianca())
    tau: Mapped[Decimal | None] = mapped_column(_confianca())
    extracao_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # FaturaExtraida completa
    avisos: Mapped[list[Any] | None] = mapped_column(JSONB)
    documento_pai_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documento.id"))
    em_lote_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Linha(Base, TenantMixin, TimestampMixin):
    __tablename__ = "linha"

    id: Mapped[uuid.UUID] = pk_uuid()
    documento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documento.id", ondelete="CASCADE"), index=True
    )
    ordem: Mapped[int] = mapped_column(Integer)
    descricao: Mapped[str] = mapped_column(Text)
    descricao_normalizada: Mapped[str | None] = mapped_column(Text)
    qtd: Mapped[Decimal | None] = mapped_column(Numeric(14, 4, asdecimal=True))
    valor_unit: Mapped[Decimal | None] = mapped_column(Numeric(14, 4, asdecimal=True))
    valor: Mapped[Decimal] = mapped_column(dinheiro())
    moeda: Mapped[str] = mapped_column(CHAR(3))
    valor_brl: Mapped[Decimal | None] = mapped_column(dinheiro())
    refs_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    processo_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("processo.id"))
    codigo_custo: Mapped[str | None] = mapped_column(String(40), ForeignKey("codigo_custo.codigo"))
    conf_extracao: Mapped[Decimal | None] = mapped_column(_confianca())
    conf_processo: Mapped[Decimal | None] = mapped_column(_confianca())
    conf_codigo: Mapped[Decimal | None] = mapped_column(_confianca())
    metodo_codigo: Mapped[str | None] = mapped_column(String(40))
    estado: Mapped[str] = mapped_column(
        enum_texto("estado", ESTADOS_LINHA), default="pendente", server_default="pendente"
    )
    bbox_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
