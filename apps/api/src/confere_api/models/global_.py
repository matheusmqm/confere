"""MODEL: tabelas globais, sem `empresa_id`: cache de PTAX e lista de espera (CF-103)."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CHAR, CheckConstraint, Date, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base, TimestampMixin
from confere_api.db.tipos import pk_uuid


class PtaxCache(Base, TimestampMixin):
    __tablename__ = "ptax_cache"

    moeda: Mapped[str] = mapped_column(CHAR(3), primary_key=True)
    data: Mapped[date] = mapped_column(Date, primary_key=True)
    compra: Mapped[Decimal] = mapped_column(Numeric(12, 6, asdecimal=True))
    venda: Mapped[Decimal] = mapped_column(Numeric(12, 6, asdecimal=True))
    fonte: Mapped[str] = mapped_column(String(20))
    boletim: Mapped[str | None] = mapped_column(String(40))


class Waitlist(Base, TimestampMixin):
    __tablename__ = "waitlist"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_minusculo"),)

    id: Mapped[uuid.UUID] = pk_uuid()
    email: Mapped[str] = mapped_column(String(200), unique=True)
    empresa: Mapped[str] = mapped_column(String(200))
    cargo: Mapped[str | None] = mapped_column(String(100))
    origem: Mapped[str | None] = mapped_column(String(100))  # utm
