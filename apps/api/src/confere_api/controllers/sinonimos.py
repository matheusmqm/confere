"""CONTROLLER: fonte de sinônimos de código de custo no Postgres (CF-65).

Implementa o `FonteSinonimos` do core. Tudo filtra por `empresa_id` (multi-tenant); a transação
é de quem chama (a sessão não é confirmada aqui).
"""

import uuid

from confere_core.costcode.dicionario import Sinonimo
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from confere_api.models.sinonimo import SinonimoCusto


class FonteSinonimosSQL:
    def __init__(self, db: Session, empresa_id: uuid.UUID) -> None:
        self._db = db
        self._empresa_id = empresa_id

    def buscar(self, texto_norm: str, fornecedor_id: str | None) -> list[Sinonimo]:
        """Sinônimos do texto: do fornecedor (se informado) e os globais."""
        filtro_fornecedor = SinonimoCusto.fornecedor_id.is_(None)
        if fornecedor_id is not None:
            filtro_fornecedor = or_(
                filtro_fornecedor, SinonimoCusto.fornecedor_id == uuid.UUID(fornecedor_id)
            )
        linhas = self._db.scalars(
            select(SinonimoCusto).where(
                SinonimoCusto.empresa_id == self._empresa_id,
                SinonimoCusto.texto_normalizado == texto_norm,
                filtro_fornecedor,
            )
        )
        return [
            Sinonimo(
                texto_normalizado=linha.texto_normalizado,
                fornecedor_id=str(linha.fornecedor_id) if linha.fornecedor_id else None,
                codigo=linha.codigo_custo,
                origem=linha.origem,
            )
            for linha in linhas
        ]

    def gravar(
        self, texto_norm: str, fornecedor_id: str | None, codigo: str, origem: str
    ) -> None:
        """Upsert por (empresa, fornecedor, texto)."""
        valores = {
            "empresa_id": self._empresa_id,
            "fornecedor_id": uuid.UUID(fornecedor_id) if fornecedor_id else None,
            "texto_normalizado": texto_norm,
            "codigo_custo": codigo,
            "origem": origem,
        }
        comando = insert(SinonimoCusto).values(**valores)
        self._db.execute(
            comando.on_conflict_do_update(
                index_elements=["empresa_id", "fornecedor_id", "texto_normalizado"],
                set_={"codigo_custo": codigo, "origem": origem},
            )
        )
