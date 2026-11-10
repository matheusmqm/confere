"""Decisão do MVP (E8): regra fixa no lugar do score calibrado (alfa, τ).

Sem nenhuma exceção aberta → aprovada sozinha; qualquer exceção de severidade `revisar` → em
revisão; `bloquear` → bloqueada. Quando o score calibrado existir, é esta função que se troca.
"""

from collections.abc import Iterable
from typing import Literal

StatusDecisao = Literal["aprovado_auto", "em_revisao", "bloqueado"]


def decidir_documento(severidades: Iterable[str]) -> StatusDecisao:
    """`severidades`: a de cada exceção aberta do documento (`info` não impede a aprovação)."""
    pesos = set(severidades)
    if "bloquear" in pesos:
        return "bloqueado"
    if "revisar" in pesos:
        return "em_revisao"
    return "aprovado_auto"
