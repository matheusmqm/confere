"""MODEL: embeddings de linhas e de exemplos, para a busca vetorial da E4 (CF-102)."""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base, TenantMixin, TimestampMixin
from confere_api.db.tipos import enum_texto, pk_uuid

ORIGENS_EMBEDDING = ("treino", "correcao", "linha")
DIMENSAO_EMBEDDING = 768  # `output_dimensionality` do Gemini


class LinhaEmbedding(Base, TenantMixin, TimestampMixin):
    __tablename__ = "linha_embedding"
    __table_args__ = (
        Index(
            "ix_linha_embedding_vetor_hnsw",
            "vetor",
            postgresql_using="hnsw",
            postgresql_ops={"vetor": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = pk_uuid()
    linha_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("linha.id", ondelete="CASCADE"))
    fornecedor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fornecedor.id"))
    texto_normalizado: Mapped[str] = mapped_column(Text)
    codigo_custo: Mapped[str] = mapped_column(String(40), ForeignKey("codigo_custo.codigo"))
    origem: Mapped[str] = mapped_column(enum_texto("origem", ORIGENS_EMBEDDING))
    vetor: Mapped[list[float]] = mapped_column(Vector(DIMENSAO_EMBEDDING))
