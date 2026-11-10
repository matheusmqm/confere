"""TabelaPTAX: carga do CSV, consulta por data exata e validações."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from confere_core.fx.tabela import Cotacao, TabelaPTAX

CSV = """data,moeda,compra,venda,boletim
2026-11-06,EUR,6.1500,6.1512,Fechamento
2026-11-06,USD,5.5000,5.5006,Fechamento
2026-11-09,EUR,6.1729,6.1741,Fechamento
2026-11-09,USD,5.5140,5.5146,Fechamento
"""


@pytest.fixture
def tabela(tmp_path: Path) -> TabelaPTAX:
    arquivo = tmp_path / "ptax.csv"
    arquivo.write_text(CSV, encoding="utf-8")
    return TabelaPTAX.carregar(arquivo)


def test_get_devolve_a_cotacao_exata(tabela: TabelaPTAX) -> None:
    c = tabela.get("USD", date(2026, 11, 9))
    assert c == Cotacao(
        data=date(2026, 11, 9),
        moeda="USD",
        compra=Decimal("5.5140"),
        venda=Decimal("5.5146"),
        boletim="Fechamento",
    )
    assert isinstance(c.venda, Decimal) if c else False


def test_get_sem_cotacao_devolve_none(tabela: TabelaPTAX) -> None:
    assert tabela.get("USD", date(2026, 11, 7)) is None  # sábado: sem regra de dia útil aqui
    assert tabela.get("CNY", date(2026, 11, 9)) is None  # moeda sem PTAX
    assert tabela.get("usd", date(2026, 11, 9)) is None  # moeda em maiúsculas


def test_tamanho_moedas_e_periodo(tabela: TabelaPTAX) -> None:
    assert len(tabela) == 4 and tabela.moedas() == ["EUR", "USD"]
    assert tabela.periodo("EUR") == (date(2026, 11, 6), date(2026, 11, 9))
    assert tabela.periodo("CNY") is None


def test_cabecalho_errado(tmp_path: Path) -> None:
    arquivo = tmp_path / "x.csv"
    arquivo.write_text("data,moeda,venda\n2026-11-09,USD,5.5\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cabeçalho esperado"):
        TabelaPTAX.carregar(arquivo)


def test_cotacao_repetida(tmp_path: Path) -> None:
    arquivo = tmp_path / "x.csv"
    arquivo.write_text(CSV + "2026-11-09,USD,5.5,5.6,Fechamento\n", encoding="utf-8")
    with pytest.raises(ValueError, match="cotação repetida: USD em 2026-11-09"):
        TabelaPTAX.carregar(arquivo)


@pytest.mark.parametrize(
    "linha",
    [
        "2026-11-09,US,5.5,5.6,Fechamento",  # moeda inválida
        "2026-11-31,USD,5.5,5.6,Fechamento",  # data inexistente
        "2026-11-09,USD,0,5.6,Fechamento",  # taxa não positiva
        "2026-11-09,USD,abc,5.6,Fechamento",
    ],
)
def test_linha_invalida(tmp_path: Path, linha: str) -> None:
    arquivo = tmp_path / "x.csv"
    arquivo.write_text("data,moeda,compra,venda,boletim\n" + linha + "\n", encoding="utf-8")
    with pytest.raises(ValidationError):
        TabelaPTAX.carregar(arquivo)


def test_csv_congelado_do_repositorio_carrega() -> None:
    caminho = Path(__file__).resolve().parents[3] / "data" / "seed42" / "ptax.csv"
    if not caminho.exists():
        pytest.skip("data/seed42/ptax.csv ainda não foi gerado (infra/scripts/baixar_ptax.py)")
    tabela = TabelaPTAX.carregar(caminho)
    assert {"USD", "EUR"} <= set(tabela.moedas())
    inicio, _ = tabela.periodo("USD") or (None, None)
    assert inicio == date(2026, 7, 15)
    c = tabela.get("USD", date(2026, 11, 9))
    assert c is not None and c.venda > c.compra > 0
