"""CONTROLLER base: todo acesso a dados passa pelo tenant (multi-tenant).

Regra: nenhuma query sem `self._q(Model)` e nenhum `session.get(...)` direto. Para buscar por id,
use `self.obter(Model, id)`, que filtra por empresa e levanta `NaoEncontrado` (404, nunca 403).
"""

import uuid
from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from confere_api.erros import NaoEncontrado
from confere_api.tenant import Tenant

M = TypeVar("M")


class RepositorioBase:
    def __init__(self, db: Session, tenant: Tenant) -> None:
        self.db = db
        self.tenant = tenant

    def _q(self, modelo: type[M]) -> Select[M]:
        """`select(modelo)` já filtrado pela empresa do tenant."""
        return select(modelo).where(
            modelo.empresa_id == self.tenant.empresa_id  # type: ignore[attr-defined]
        )

    def _g(self, modelo: type[M]) -> Select[M]:
        """`select(modelo)` de tabela GLOBAL (sem `empresa_id`: catálogo, PTAX). Só para elas."""
        return select(modelo)

    def obter(self, modelo: type[M], id_: uuid.UUID) -> M:
        achado = self.db.scalars(
            self._q(modelo).where(modelo.id == id_)  # type: ignore[attr-defined]
        ).first()
        if achado is None:
            raise NaoEncontrado
        return achado

    def adicionar(self, objeto: Any) -> None:
        """Grava um objeto novo na empresa do tenant (ignora um `empresa_id` diferente)."""
        objeto.empresa_id = self.tenant.empresa_id
        self.db.add(objeto)
