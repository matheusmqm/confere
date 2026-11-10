"""MODEL: catálogo global de códigos de custo (CF-101). Chave natural: o código."""

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from confere_api.db.base import Base


class CodigoCusto(Base):
    """Sem `empresa_id`: catálogo igual para todos (carga de `config/codigos_custo.yaml`)."""

    __tablename__ = "codigo_custo"

    codigo: Mapped[str] = mapped_column(String(40), primary_key=True)
    descricao: Mapped[str] = mapped_column(Text)
    grupo: Mapped[str] = mapped_column(String(40))
    unidade: Mapped[str] = mapped_column(String(20))
