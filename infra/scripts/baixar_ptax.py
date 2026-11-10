"""Baixa as cotações PTAX de FECHAMENTO do Banco Central (API Olinda) para `data/seed42/ptax.csv`.

    uv run python infra/scripts/baixar_ptax.py
    uv run python infra/scripts/baixar_ptax.py --inicio 2026-07-15 --fim 2026-11-30 --moedas USD EUR

Endpoint (OData, datas em MM-DD-AAAA):
    https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoMoedaPeriodo(
        moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)

CSV: `data,moeda,compra,venda,boletim` (data ISO, valores com 4 casas, ordenado por data e
moeda). Só entra o boletim "Fechamento". Dias sem cotação (fim de semana e feriado) NÃO entram:
a regra do último dia útil é da CF-71. Nenhuma cotação é inventada:

- datas depois da última cotação já publicada ficam de fora (rode de novo depois);
- moedas que o BCB não publica na PTAX (ex. CNY) ficam sem linhas e o script avisa.
"""

import argparse
import csv
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

BASE = "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata"
RECURSO = (
    "CotacaoMoedaPeriodo(moeda=@moeda,dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)"
)
BOLETIM = "Fechamento"
CABECALHO = ("data", "moeda", "compra", "venda", "boletim")
QUATRO_CASAS = Decimal("0.0001")
RAIZ = Path(__file__).resolve().parents[2]
SAIDA_PADRAO = RAIZ / "data" / "seed42" / "ptax.csv"


@dataclass(frozen=True)
class Linha:
    data: date
    moeda: str
    compra: Decimal
    venda: Decimal

    def como_csv(self) -> list[str]:
        return [
            self.data.isoformat(),
            self.moeda,
            f"{self.compra:.4f}",
            f"{self.venda:.4f}",
            BOLETIM,
        ]


def url(moeda: str, inicio: date, fim: date) -> str:
    """URL com os parâmetros OData na forma que a API espera (aspas simples, MM-DD-AAAA)."""
    return (
        f"{BASE}/{RECURSO}?@moeda='{moeda}'"
        f"&@dataInicial='{inicio:%m-%d-%Y}'&@dataFinalCotacao='{fim:%m-%d-%Y}'&$format=json"
    )


def buscar(cliente: httpx.Client, moeda: str, inicio: date, fim: date) -> list[dict[str, object]]:
    resposta = cliente.get(url(moeda, inicio, fim))
    resposta.raise_for_status()
    # parse_float=Decimal: sem passar por float binário
    dados = json.loads(resposta.text, parse_float=Decimal)
    registros: list[dict[str, object]] = dados["value"]
    return registros


def fechamentos(registros: Iterable[dict[str, object]], moeda: str) -> list[Linha]:
    """Só o boletim de fechamento; uma linha por data (erra se houver duas)."""
    linhas: dict[date, Linha] = {}
    for r in registros:
        if r["tipoBoletim"] != BOLETIM:
            continue
        dia = date.fromisoformat(str(r["dataHoraCotacao"])[:10])
        if dia in linhas:
            raise ValueError(f"{moeda}: mais de um fechamento em {dia}")
        linhas[dia] = Linha(
            dia,
            moeda,
            Decimal(str(r["cotacaoCompra"])).quantize(QUATRO_CASAS),
            Decimal(str(r["cotacaoVenda"])).quantize(QUATRO_CASAS),
        )
    return list(linhas.values())


def escrever_csv(linhas: Iterable[Linha], caminho: Path) -> int:
    ordenadas = sorted(linhas, key=lambda ln: (ln.data, ln.moeda))
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as arquivo:
        escritor = csv.writer(arquivo, lineterminator="\n")
        escritor.writerow(CABECALHO)
        escritor.writerows(ln.como_csv() for ln in ordenadas)
    return len(ordenadas)


def main(argv: list[str] | None = None, cliente: httpx.Client | None = None) -> int:
    parser = argparse.ArgumentParser(description="Baixa a PTAX de fechamento do BCB.")
    parser.add_argument("--inicio", type=date.fromisoformat, default=date(2026, 7, 15))
    parser.add_argument("--fim", type=date.fromisoformat, default=date(2026, 11, 30))
    parser.add_argument("--moedas", nargs="+", default=["USD", "EUR", "CNY"])
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    args = parser.parse_args(argv)

    todas: list[Linha] = []
    with cliente or httpx.Client(timeout=30.0) as http:
        for moeda in args.moedas:
            linhas = fechamentos(buscar(http, moeda, args.inicio, args.fim), moeda)
            if not linhas:
                print(
                    f"AVISO: o BCB não publica PTAX de fechamento para {moeda} no período "
                    "(nenhuma linha gravada; nada foi inventado).",
                    file=sys.stderr,
                )
                continue
            ultima = max(ln.data for ln in linhas)
            print(
                f"{moeda}: {len(linhas)} fechamentos, de {min(ln.data for ln in linhas)} a {ultima}"
            )
            if ultima < args.fim:
                print(
                    f"AVISO: {moeda} só tem cotação até {ultima}; faltam datas até {args.fim} "
                    "(rode de novo depois dessa data).",
                    file=sys.stderr,
                )
            todas += linhas

    if not todas:
        print("Nenhuma cotação baixada: o CSV não foi gravado.", file=sys.stderr)
        return 3
    n = escrever_csv(todas, args.saida)
    print(f"{n} linhas gravadas em {args.saida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
