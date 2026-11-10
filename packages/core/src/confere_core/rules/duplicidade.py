"""Regra `duplicidade` (ordem 1, roda primeiro) (CF-82).

1. `sha256` igual ao de outro documento da empresa (não cancelado) → todas as linhas `duplicada`.
2. (fornecedor, número normalizado) igual ao de outro documento → idem.
3. Por linha: (fornecedor, processo, código, valor, moeda) igual a uma linha JÁ APROVADA de outro
   documento → aquela linha `duplicada`.

Tudo com severidade `bloquear`. Nos casos 1 e 2 o risco de cada linha é o seu `valor_brl`, então
a soma é o total do documento em BRL (sem contar duas vezes); `dados` traz `original_id`.
O primeiro documento recebido é o original e o segundo, a duplicata: quem chama o histórico
registra cada documento só depois de avaliá-lo.
"""

import re

from confere_core.rules.base import ContextoRegras, ResultadoRegra, regra

NOME = "duplicidade"


def normalizar_numero(numero: str) -> str:
    """Maiúsculas, sem espaços e sem zeros à esquerda ("nf 000123" → "NF000123"; "000123" → "123")."""
    sem_espacos = re.sub(r"\s+", "", numero.upper())
    return sem_espacos.lstrip("0") or "0"


@regra(NOME, ordem=1)
def duplicidade(ctx: ContextoRegras) -> list[ResultadoRegra]:
    historico = ctx.historico
    if historico is None:
        return []
    doc = ctx.documento

    def todas_as_linhas(original: object, criterio: str) -> list[ResultadoRegra]:
        return [
            ResultadoRegra(
                regra=NOME,
                alvo="linha",
                alvo_id=str(linha.id),
                estado="duplicada",
                severidade="bloquear",
                valor_brl_em_risco=linha.valor_brl,
                dados={
                    "original_id": str(original),
                    "criterio": criterio,
                    "total_documento_brl": doc.total_brl,
                },
            )
            for linha in ctx.linhas
        ]

    if doc.sha256:
        original = historico.existe_sha256(doc.empresa_id, doc.sha256, doc.id)
        if original is not None:
            return todas_as_linhas(original, "sha256")
    original = historico.existe_numero(
        doc.empresa_id, doc.fornecedor_id, normalizar_numero(doc.numero), doc.id
    )
    if original is not None:
        return todas_as_linhas(original, "numero_documento")

    resultados: list[ResultadoRegra] = []
    for linha in ctx.linhas:
        if linha.codigo_custo is None or linha.processo_id is None:
            continue
        outro = historico.linha_aprovada_igual(
            doc.empresa_id,
            doc.fornecedor_id,
            linha.processo_id,
            linha.codigo_custo,
            linha.valor,
            linha.moeda,
            doc.id,
        )
        if outro is not None:
            resultados.append(
                ResultadoRegra(
                    regra=NOME,
                    alvo="linha",
                    alvo_id=str(linha.id),
                    estado="duplicada",
                    severidade="bloquear",
                    valor_brl_em_risco=linha.valor_brl,
                    dados={"original_id": str(outro), "criterio": "linha_aprovada_igual"},
                )
            )
    return resultados
