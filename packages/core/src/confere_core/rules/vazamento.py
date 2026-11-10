"""Vazamento financeiro: quanto dinheiro uma cobrança indevida faria sair (CF-85).

Definições (também em `docs/avaliacao.md`):

- **Vazamento por linha** (`vazamento_linha`): `acima_tolerancia` → o excedente em BRL
  (`max(0, cobrado − previsto)`); `duplicada` → o valor da linha em BRL; `sem_provisao` → o valor
  em BRL SOMENTE se a decisão humana (ou o gabarito, no eval) disser que a cobrança não é
  legítima; `cambio_divergente` → a diferença de câmbio em BRL; demais estados → 0.
- **Detectado** = soma do vazamento das linhas, usando o resultado vencedor de cada uma.
- **Evitado** = vazamento bloqueado automaticamente (severidade `bloquear`) + o contestado ou
  bloqueado por humano. No modo demo (o jurado não decide tudo), soma também o em risco das
  exceções de severidade `revisar`.
- **Em risco** = detectado ainda sem decisão humana e fora do que já foi evitado.
- **Vazado** = detectado que um humano decidiu aprovar.
"""

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from confere_core.rules.base import AvaliacaoRegras, ResultadoRegra

Decisao = Literal["contestar", "bloquear", "aprovar"]


class VazamentoLote(BaseModel):
    detectado: Decimal = Decimal(0)
    evitado: Decimal = Decimal(0)
    em_risco: Decimal = Decimal(0)
    vazado: Decimal = Decimal(0)

    def somar(self, outro: "VazamentoLote") -> "VazamentoLote":
        return VazamentoLote(
            detectado=self.detectado + outro.detectado,
            evitado=self.evitado + outro.evitado,
            em_risco=self.em_risco + outro.em_risco,
            vazado=self.vazado + outro.vazado,
        )


def vazamento_linha(resultado: ResultadoRegra, legitima: bool | None = None) -> Decimal:
    """Vazamento em BRL de uma linha. `legitima` só vale para `sem_provisao`."""
    if resultado.estado == "acima_tolerancia":
        excedente = Decimal(resultado.dados.get("dif_brl", resultado.valor_brl_em_risco))
        return max(Decimal(0), excedente)
    if resultado.estado == "duplicada":
        return resultado.valor_brl_em_risco
    if resultado.estado == "sem_provisao":
        return resultado.valor_brl_em_risco if legitima is False else Decimal(0)
    if resultado.estado == "cambio_divergente":
        return Decimal(resultado.dados.get("dif_cambio_brl", resultado.valor_brl_em_risco))
    return Decimal(0)


def vazamento_documento(
    avaliacao: AvaliacaoRegras,
    decisoes: Mapping[str, Decisao] | None = None,
    legitimas: Mapping[str, bool] | None = None,
    modo_demo: bool = False,
) -> VazamentoLote:
    """Separa o vazamento do documento em detectado, evitado, em risco e vazado.

    `decisoes` e `legitimas` são indexadas pelo id da linha (texto).
    """
    decisoes = decisoes or {}
    legitimas = legitimas or {}
    total = VazamentoLote()
    for linha_id, resultado in avaliacao.estados_linha.items():
        valor = vazamento_linha(resultado, legitimas.get(linha_id))
        if valor <= 0:
            continue
        decisao = decisoes.get(linha_id)
        if decisao == "aprovar":
            parte = VazamentoLote(detectado=valor, vazado=valor)
        elif (
            resultado.severidade == "bloquear"
            or decisao in ("contestar", "bloquear")
            or (modo_demo and resultado.severidade == "revisar")
        ):
            parte = VazamentoLote(detectado=valor, evitado=valor)
        else:
            parte = VazamentoLote(detectado=valor, em_risco=valor)
        total = total.somar(parte)
    return total


def vazamento_lote(
    avaliacoes: Iterable[AvaliacaoRegras],
    decisoes: Mapping[str, Decisao] | None = None,
    legitimas: Mapping[str, bool] | None = None,
    modo_demo: bool = False,
) -> VazamentoLote:
    total = VazamentoLote()
    for avaliacao in avaliacoes:
        total = total.somar(vazamento_documento(avaliacao, decisoes, legitimas, modo_demo))
    return total
