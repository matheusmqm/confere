"""CONTROLLER: fornecedores e seus aliases."""

import uuid

from rapidfuzz import fuzz, process

from confere_api.controllers.base import RepositorioBase
from confere_api.models.fornecedor import FornecedorAlias
from confere_core.resolve.normalizar import normalizar_nome

SIMILARIDADE_MINIMA = 90


class FornecedorController(RepositorioBase):
    def resolver_por_nome(self, nome: str) -> uuid.UUID | None:
        """Fornecedor cujo alias é parecido com `nome` (rapidfuzz ≥ 90), ou None."""
        alvo = normalizar_nome(nome)
        if not alvo:
            return None
        aliases = {
            alias.id: alias
            for alias in self.db.scalars(self._q(FornecedorAlias)).all()
            if alias.alias_normalizado
        }
        achado = process.extractOne(
            alvo,
            {i: a.alias_normalizado for i, a in aliases.items()},
            scorer=fuzz.token_set_ratio,
            score_cutoff=SIMILARIDADE_MINIMA,
        )
        return aliases[achado[2]].fornecedor_id if achado else None
