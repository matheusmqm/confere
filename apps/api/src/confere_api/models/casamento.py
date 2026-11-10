"""MODEL: casamento ótimo entre uma linha e uma provisão (E6, CF-102)."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CHAR, Date, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base, TenantMixin, TimestampMixin
from confere_api.db.tipos import dinheiro, pk_uuid


class Casamento(Base, TenantMixin, TimestampMixin):
    __tablename__ = "casamento"

    id: Mapped[uuid.UUID] = pk_uuid()
    linha_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("linha.id", ondelete="CASCADE"), unique=True
    )
    provisao_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("provisao.id"))
    custo: Mapped[Decimal] = mapped_column(Numeric(10, 6, asdecimal=True))
    diferenca: Mapped[Decimal] = mapped_column(dinheiro())
    moeda_comparacao: Mapped[str] = mapped_column(CHAR(3))
    diferenca_brl: Mapped[Decimal] = mapped_column(dinheiro())
    ptax: Mapped[Decimal | None] = mapped_column(Numeric(12, 6, asdecimal=True))
    ptax_data: Mapped[date | None] = mapped_column(Date)
    solver: Mapped[str] = mapped_column(String(20))
