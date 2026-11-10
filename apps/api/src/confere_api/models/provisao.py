"""MODEL: provisão, o custo previsto de um fornecedor num processo (CF-101)."""

import uuid
from decimal import Decimal

from sqlalchemy import CHAR, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base, TenantMixin, TimestampMixin
from confere_api.db.tipos import dinheiro, enum_texto, pk_uuid

STATUS_PROVISAO = ("aberta", "casada", "parcial", "cancelada")


class Provisao(Base, TenantMixin, TimestampMixin):
    __tablename__ = "provisao"
    __table_args__ = (
        Index(
            "ix_provisao_empresa_processo_fornecedor", "empresa_id", "processo_id", "fornecedor_id"
        ),
    )

    id: Mapped[uuid.UUID] = pk_uuid()
    processo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("processo.id"))
    fornecedor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("fornecedor.id"))
    codigo_custo: Mapped[str] = mapped_column(String(40), ForeignKey("codigo_custo.codigo"))
    moeda: Mapped[str] = mapped_column(CHAR(3))
    valor: Mapped[Decimal] = mapped_column(dinheiro())
    status: Mapped[str] = mapped_column(
        enum_texto("status", STATUS_PROVISAO), default="aberta", server_default="aberta"
    )
