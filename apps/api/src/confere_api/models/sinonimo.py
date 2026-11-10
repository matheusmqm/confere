"""MODEL: sinônimos de código de custo aprendidos (dicionário da E4, CF-65 e CF-101)."""

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base, TenantMixin, TimestampMixin
from confere_api.db.tipos import enum_texto, pk_uuid

ORIGENS_SINONIMO = ("catalogo", "treino", "correcao")


class SinonimoCusto(Base, TenantMixin, TimestampMixin):
    __tablename__ = "sinonimo_custo"
    __table_args__ = (
        # NULLS NOT DISTINCT: o sinônimo global (fornecedor_id nulo) também é único por texto.
        Index(
            "uq_sinonimo_custo_empresa_fornecedor_texto",
            "empresa_id",
            "fornecedor_id",
            "texto_normalizado",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[uuid.UUID] = pk_uuid()
    # Nulo = sinônimo global.
    fornecedor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("fornecedor.id"), nullable=True
    )
    texto_normalizado: Mapped[str] = mapped_column(Text)
    codigo_custo: Mapped[str] = mapped_column(String(40), ForeignKey("codigo_custo.codigo"))
    origem: Mapped[str] = mapped_column(enum_texto("origem", ORIGENS_SINONIMO))
