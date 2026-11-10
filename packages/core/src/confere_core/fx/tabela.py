"""Tabela PTAX congelada (`data/seed42/ptax.csv`), carregada de arquivo, sem rede.

Colunas: `data,moeda,compra,venda,boletim`. A consulta é por data EXATA: dia sem cotação
(fim de semana, feriado) devolve `None`; a regra do último dia útil é da CF-71.
"""

import csv
from collections.abc import Iterable
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field

CABECALHO = ("data", "moeda", "compra", "venda", "boletim")


class Cotacao(BaseModel):
    model_config = ConfigDict(frozen=True)

    data: date
    moeda: str = Field(pattern=r"^[A-Z]{3}$")
    compra: Decimal = Field(gt=0)
    venda: Decimal = Field(gt=0)  # taxa de venda: a usada na conversão de faturas
    boletim: str


class TabelaPTAX:
    def __init__(self, cotacoes: Iterable[Cotacao]) -> None:
        self._por_chave: dict[tuple[str, date], Cotacao] = {}
        for c in cotacoes:
            chave = (c.moeda, c.data)
            if chave in self._por_chave:
                raise ValueError(f"cotação repetida: {c.moeda} em {c.data}")
            self._por_chave[chave] = c

    @classmethod
    def carregar(cls, path: str | Path) -> Self:
        with open(path, encoding="utf-8", newline="") as arquivo:
            leitor = csv.DictReader(arquivo)
            if tuple(leitor.fieldnames or ()) != CABECALHO:
                raise ValueError(f"cabeçalho esperado {CABECALHO}, veio {leitor.fieldnames}")
            return cls(Cotacao.model_validate(linha) for linha in leitor)

    def get(self, moeda: str, data: date) -> Cotacao | None:
        """Cotação de fechamento da moeda na data exata, ou None se não houve."""
        return self._por_chave.get((moeda, data))

    def moedas(self) -> list[str]:
        return sorted({m for m, _ in self._por_chave})

    def periodo(self, moeda: str) -> tuple[date, date] | None:
        datas = [d for m, d in self._por_chave if m == moeda]
        return (min(datas), max(datas)) if datas else None

    def __len__(self) -> int:
        return len(self._por_chave)
