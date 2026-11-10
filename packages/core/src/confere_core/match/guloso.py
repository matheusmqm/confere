"""Casamento guloso linhas x provisões (E6) — versão do MVP mínimo.

Percorre as linhas NA ORDEM do documento e leva, para cada uma, a provisão livre do MESMO
código de custo e da mesma moeda com o valor mais próximo. É o baseline ingênuo B2 (CF-77); o
casamento ótimo (húngaro, CF-74/75) o substitui depois, com a mesma interface.
"""

import uuid
from decimal import Decimal

from pydantic import BaseModel

from confere_core.domain import CasamentoLinha, ResultadoCasamento


class LinhaParaCasar(BaseModel):
    id: uuid.UUID
    codigo_custo: str | None
    valor: Decimal
    moeda: str


class ProvisaoParaCasar(BaseModel):
    id: uuid.UUID
    codigo_custo: str
    valor: Decimal
    moeda: str


def casar_guloso(
    linhas: list[LinhaParaCasar],
    provisoes: list[ProvisaoParaCasar],
    ptax: Decimal | None = None,
) -> ResultadoCasamento:
    """Uma entrada por linha. `ptax` só vale para moeda estrangeira (BRL por unidade)."""
    livres = list(provisoes)
    casamentos: list[CasamentoLinha] = []
    for linha in linhas:
        candidatas = [
            p for p in livres if p.codigo_custo == linha.codigo_custo and p.moeda == linha.moeda
        ]
        if not candidatas:
            casamentos.append(CasamentoLinha(linha_id=linha.id, moeda=linha.moeda))
            continue
        melhor = min(candidatas, key=lambda p: abs(p.valor - linha.valor))
        livres.remove(melhor)
        casamentos.append(
            CasamentoLinha(
                linha_id=linha.id,
                provisao_id=melhor.id,
                cobrado=linha.valor,
                previsto=melhor.valor,
                moeda=linha.moeda,
                ptax=Decimal(1) if linha.moeda == "BRL" else ptax,
            )
        )
    return ResultadoCasamento(casamentos=casamentos)
