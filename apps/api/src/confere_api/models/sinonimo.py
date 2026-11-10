"""MODEL: sinônimos de código de custo aprendidos (dicionário da E4, CF-65)."""

import uuid

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base, TenantMixin, TimestampMixin


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

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Nulo = sinônimo global. A FK para fornecedor.id entra quando essa tabela existir.
    fornecedor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    texto_normalizado: Mapped[str] = mapped_column(Text)
    codigo_custo: Mapped[str] = mapped_column(String(40))
    origem: Mapped[str] = mapped_column(String(20))  # catalogo | treino | humano | llm
