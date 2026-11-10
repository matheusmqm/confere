"""Câmbio do gerador sintético: PTAX de venda na data de emissão, com tolerância de dias sem
cotação (fim de semana e feriado).

Não é a regra de produção (a do último dia útil é da CF-71, no core): aqui basta olhar até
`JANELA_DIAS` para trás e devolver None se não houver cotação. Datas além do fim da tabela
(que vai até a última cotação já publicada) ficam sem câmbio: nada é inventado.
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from confere_core.fx.tabela import Cotacao, TabelaPTAX

PTAX_PADRAO = Path(__file__).resolve().parents[4] / "data" / "seed42" / "ptax.csv"
JANELA_DIAS = 5


def carregar_ptax_padrao() -> TabelaPTAX:
    """`data/seed42/ptax.csv`; sem o arquivo, uma tabela vazia (nenhuma conversão possível)."""
    return TabelaPTAX.carregar(PTAX_PADRAO) if PTAX_PADRAO.exists() else TabelaPTAX([])


def cotacao(tabela: TabelaPTAX, moeda: str, data: date) -> Cotacao | None:
    """Cotação de `moeda` em `data` (ou do dia anterior com cotação, até 5 dias)."""
    for dias in range(JANELA_DIAS + 1):
        c = tabela.get(moeda, data - timedelta(days=dias))
        if c is not None:
            return c
    return None


def venda(tabela: TabelaPTAX, moeda: str, data: date) -> Decimal | None:
    """PTAX de venda de `moeda` em `data`; BRL vale 1; None sem cotação."""
    if moeda == "BRL":
        return Decimal(1)
    c = cotacao(tabela, moeda, data)
    return None if c is None else c.venda


def ultima_data(tabela: TabelaPTAX, moeda: str) -> date | None:
    periodo = tabela.periodo(moeda)
    return periodo[1] if periodo else None


def para_brl(tabela: TabelaPTAX, valor: Decimal, moeda: str, data: date) -> Decimal | None:
    taxa = venda(tabela, moeda, data)
    return None if taxa is None else (valor * taxa).quantize(Decimal("0.01"))
