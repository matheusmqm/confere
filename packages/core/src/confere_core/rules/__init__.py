"""E7: regras de negócio. Importar este pacote registra as regras existentes em `REGISTRO`."""

from confere_core.rules import duplicidade, tolerancia  # noqa: F401
from confere_core.rules.base import AvaliacaoRegras, ContextoRegras, aplicar_regras

# TODO: `cambio` e `cobertura` (outras tarefas do E7) entram nesta linha quando existirem.

__all__ = ["AvaliacaoRegras", "ContextoRegras", "aplicar_regras"]
