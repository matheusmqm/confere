"""Regra `tolerancia` (ordem 10): cobrado × previsto com tolerância absoluta e relativa (CF-81).

    dif = cobrado − previsto (na moeda de comparação)
    tol = max(tol_abs_brl convertido para essa moeda pela MESMA PTAX, tol_rel · previsto)

`dif > tol` → `acima_tolerancia` (revisar); `dif < −tol` → `abaixo_previsto` (info: sugestão de
aprovar e ajustar a provisão, sem risco); senão `ok`.

`valor_brl_em_risco` de `acima_tolerancia` é o excedente INTEIRO em BRL (`dif_brl`), não só o
que passa da tolerância: se a cobrança é contestada, é o valor todo da diferença que se evita.

Casamentos sem provisão ou sem cotação (moeda estrangeira sem PTAX) ficam para as regras de
cobertura e de câmbio.
"""

from decimal import Decimal

from confere_core.rules.base import (
    ContextoRegras,
    EstadoLinha,
    ResultadoRegra,
    Severidade,
    regra,
)

_CENTAVO = Decimal("0.01")
NOME = "tolerancia"


@regra(NOME, ordem=10)
def tolerancia(ctx: ContextoRegras) -> list[ResultadoRegra]:
    resultados: list[ResultadoRegra] = []
    for c in ctx.casamento.casamentos:
        if c.provisao_id is None or c.previsto is None or c.cobrado is None:
            continue
        ptax = Decimal(1) if c.moeda == "BRL" else c.ptax
        if ptax is None:
            continue
        dif = c.cobrado - c.previsto
        dif_brl = (dif * ptax).quantize(_CENTAVO)
        tol = max(ctx.politica.tol_abs_brl / ptax, ctx.politica.tol_rel * abs(c.previsto))
        dados = {
            "cobrado": c.cobrado,
            "previsto": c.previsto,
            "moeda": c.moeda,
            "dif": dif,
            "dif_brl": dif_brl,
            "tol": tol,
            "ptax": ptax,
            "ptax_data": c.ptax_data,
        }
        estado: EstadoLinha
        severidade: Severidade
        if dif > tol:
            estado, severidade, risco = "acima_tolerancia", "revisar", dif_brl
        elif dif < -tol:
            dados["sugestao"] = "aprovar e ajustar a provisão"
            estado, severidade, risco = "abaixo_previsto", "info", Decimal(0)
        else:
            estado, severidade, risco = "ok", "info", Decimal(0)
        resultados.append(
            ResultadoRegra(
                regra=NOME,
                alvo="linha",
                alvo_id=str(c.linha_id),
                estado=estado,
                severidade=severidade,
                valor_brl_em_risco=risco,
                dados=dados,
            )
        )
    return resultados
