"""Fixtures compartilhadas dos testes do synth."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from confere_core.fx.tabela import Cotacao, TabelaPTAX


@pytest.fixture(scope="session")
def ptax_completa() -> TabelaPTAX:
    """PTAX SINTÉTICA, diária, de USD e EUR (2026-07-01 a 2027-03-31), só para testes.

    Cobre todas as datas de emissão possíveis; o CSV real (`data/seed42/ptax.csv`) só vai até a
    última cotação publicada. Não é dado do BCB.
    """
    cotacoes: list[Cotacao] = []
    dia, i = date(2026, 7, 1), 0
    while dia <= date(2027, 3, 31):
        for moeda, base in (("USD", Decimal("5.30")), ("EUR", Decimal("6.10"))):
            venda = (base + Decimal(i % 17) / 100).quantize(Decimal("0.0001"))
            cotacoes.append(
                Cotacao(
                    data=dia,
                    moeda=moeda,
                    compra=venda - Decimal("0.0006"),
                    venda=venda,
                    boletim="Fechamento",
                )  # fmt: skip
            )
        dia += timedelta(days=1)
        i += 1
    return TabelaPTAX(cotacoes)
