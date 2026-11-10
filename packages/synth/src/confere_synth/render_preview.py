"""Gera uma pré-visualização (PDF) de cada estilo, com dados fixos e fictícios.

Uso: `uv run python -m confere_synth.render_preview` → `data/preview/estilo_N.pdf`
(pasta no .gitignore). Precisa das bibliotecas do sistema do WeasyPrint (Pango); sem elas,
grava só os `.html` ao lado e sai com código 1 (veja docs/setup.md).
"""

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from confere_synth.render import (
    TOMADOR_PADRAO,
    ContextoRender,
    DocInfo,
    FornecedorInfo,
    LinhaRender,
    ProcessoRefs,
    renderizar_html,
)

RAIZ = Path(__file__).resolve().parents[4]
PASTA_PADRAO = RAIZ / "data" / "preview"

CONTEINERES = ["QZAU3400350", "QXAU8056351", "ZQBU1234563"]


def _linha(descricao: str, qtd: str, unit: str, moeda: str, **extra: object) -> LinhaRender:
    q, u = Decimal(qtd), Decimal(unit)
    return LinhaRender(
        descricao=descricao,
        qtd=q,
        valor_unit=u,
        valor=q * u,
        moeda=moeda,
        **extra,
    )


def _contexto(
    numero: str,
    moeda: str,
    fornecedor: FornecedorInfo,
    linhas: list[LinhaRender],
    refs: ProcessoRefs,
    observacoes: str = "",
    emissao: date = date(2026, 10, 14),
    vencimento: date | None = date(2026, 11, 13),
) -> ContextoRender:
    return ContextoRender(
        doc=DocInfo(
            numero=numero,
            emissao=emissao,
            vencimento=vencimento,
            moeda=moeda,
            total=sum((linha.valor for linha in linhas), Decimal(0)),
            observacoes=observacoes,
        ),
        fornecedor=fornecedor,
        tomador=TOMADOR_PADRAO,
        processo_refs=refs,
        linhas=linhas,
    )


def contextos_de_exemplo() -> dict[int, ContextoRender]:
    refs_maritimo = ProcessoRefs(
        bl_master="ATLX496348124",
        bl_house=["HBL-SUA-283060"],
        conteineres=CONTEINERES[:2],
        navio="MV Aurora Star",
        viagem="137W",
        ref_cliente="PO-30021",
    )

    e1 = _contexto(
        "AOL-INV-2026-004417",
        "USD",
        FornecedorInfo(
            nome="Atlântida Ocean Lines Pte. Ltd.",
            endereco="1 Fictional Quay, Singapore 000000 (fictitious address)",
            email="billing@atlantida-ocean.example",
        ),
        [
            _linha("Ocean Freight 40' HC", "2", "1850.00", "USD"),
            _linha("Bunker Adjustment Factor", "2", "224.50", "USD"),
            _linha("Origin Terminal Handling Charge", "2", "181.00", "USD"),
            _linha("B/L Fee", "1", "75.00", "USD"),
            _linha("Documentation Fee", "1", "60.00", "USD"),
        ],
        refs_maritimo,
        "Charges are due in the invoice currency. Fictitious sample document.",
    )

    e2 = _contexto(
        "NFP-DN-26-0971",
        "EUR",
        FornecedorInfo(
            nome="Nordhaven Freight Partners GmbH",
            endereco="Fiktivstrasse 12, 00000 Hamburg (fictitious address)",
            email="accounts@nordhaven-freight.example",
        ),
        [
            _linha(
                "Ocean Freight (agent share)", "2", "412.00", "EUR", refs_linha=[CONTEINERES[0]]
            ),
            _linha("Terminal Handling Origin", "1", "168.00", "EUR", refs_linha=[CONTEINERES[1]]),
            _linha("Agent Handling Fee", "1", "95.50", "EUR"),
            _linha("Courier", "1", "38.00", "EUR"),
        ],
        ProcessoRefs(
            bl_master="BORX771204455",
            conteineres=CONTEINERES[:2],
            navio="MV Boreal Voyager",
            viagem="024W",
            ref_agente="AGT-2026-48213",
        ),
    )

    e3 = _contexto(
        "TMA-2026/018277",
        "BRL",
        FornecedorInfo(
            nome="Terminal Mar Azul S.A.",
            endereco="Av. Fictícia, 500, Fortaleza/CE (endereço fictício)",
            cnpj="00.000.123/0001-45",
            email="faturamento@terminalmarazul.example",
        ),
        [
            _linha("Capatazia (THC destino)", "2", "1362.40", "BRL", codigo="SV-001"),
            _linha("Taxa ISPS", "2", "54.80", "BRL", codigo="SV-014"),
            _linha("Escaneamento de contêiner", "1", "187.00", "BRL", codigo="SV-032"),
            _linha("Levante", "2", "251.90", "BRL", codigo="SV-020"),
        ],
        refs_maritimo.model_copy(update={"ref_cliente": None, "bl_master": "TARX118820934"}),
    )

    e4 = _contexto(
        "NDB-000412",
        "BRL",
        FornecedorInfo(
            nome="Armazéns Gerais Carnaúba Ltda.",
            endereco="Rod. Fictícia km 12, Maracanaú/CE (endereço fictício)",
            cnpj="00.000.231/0001-03",
            email="cobranca@armazens-carnauba.example",
        ),
        [
            _linha(
                "Armazenagem alfandegada - 1º período",
                "1",
                "1050.00",
                "BRL",
                periodo=(date(2026, 10, 2), date(2026, 10, 12)),
                base_cif=Decimal("300000.00"),
                percentual=Decimal("0.35"),
            ),
            _linha(
                "Armazenagem alfandegada - 2º período",
                "1",
                "1050.00",
                "BRL",
                periodo=(date(2026, 10, 12), date(2026, 10, 22)),
                base_cif=Decimal("300000.00"),
                percentual=Decimal("0.35"),
            ),
            _linha("Desconsolidaçao de carga", "1", "431.20", "BRL"),
            _linha("Posicionamento", "2", "376.00", "BRL", refs_linha=[CONTEINERES[0]]),
            _linha("Lavagem de contêiner", "1", "158.00", "BRL"),
        ],
        refs_maritimo,
        "Período de armazenagem contado da data de entrada, inclusive. Documento fictício.",
    )

    longa = (
        "Os valores de reembolso correspondem a despesas pagas por conta e ordem do cliente, "
        "conforme comprovantes arquivados. Os honorários seguem a tabela contratada para "
        "importação marítima com desembaraço em recinto alfandegado. Eventuais diferenças "
        "de câmbio serão regularizadas no demonstrativo seguinte. O pagamento deve ser feito "
        "até a data de vencimento, mediante depósito na conta informada em contrato. "
        "Este é um documento fictício, gerado apenas para testes."
    )
    e5 = _contexto(
        "DD-2026-0377",
        "BRL",
        FornecedorInfo(
            nome="Despachos Aduaneiros Farol Ltda.",
            endereco="Rua Fictícia, 77, sala 3, Fortaleza/CE (endereço fictício)",
            cnpj="00.000.345/0001-71",
            email="financeiro@despachos-farol.example",
        ),
        [
            _linha("Taxa Siscomex (registro da DI)", "1", "154.23", "BRL", secao="reembolso"),
            _linha("AFRMM", "1", "1699.20", "BRL", secao="reembolso"),
            _linha("Sindicato dos despachantes (SDA)", "1", "96.00", "BRL", secao="reembolso"),
            _linha("Honorários de despacho aduaneiro", "1", "861.50", "BRL", secao="honorario"),
            _linha("Emissão de LI", "1", "187.00", "BRL", secao="honorario"),
        ],
        refs_maritimo,
        longa,
    )

    linhas6: list[LinhaRender] = []
    faturas = [("AOL-INV-004417", "ATLX496348124"), ("AOL-INV-004502", "ATLX118203775"),
               ("AOL-INV-004611", "ATLX902114560")]  # fmt: skip
    descricoes = [("Ocean Freight", "1850.00"), ("Bunker Adjustment Factor", "224.50"),
                  ("Origin THC", "181.00"), ("B/L Fee", "75.00")]  # fmt: skip
    for i in range(32):
        fatura, bl = faturas[i * len(faturas) // 32]
        desc, valor = descricoes[i % len(descricoes)]
        linhas6.append(
            LinhaRender(
                descricao=desc,
                valor_unit=Decimal(valor),
                valor=Decimal(valor),
                moeda="USD",
                fatura_no=fatura,
                bl=bl,
                container=CONTEINERES[i % len(CONTEINERES)],
            )
        )
    e6 = _contexto(
        "STM-2026-10",
        "USD",
        FornecedorInfo(
            nome="Boreal Container Line AS",
            endereco="Fiktivgata 3, 0000 Oslo (fictitious address)",
            email="statements@boreal-line.example",
        ),
        linhas6,
        ProcessoRefs(),
        "Statement of open items. Fictitious sample document.",
        vencimento=None,
    )
    return {1: e1, 2: e2, 3: e3, 4: e4, 5: e5, 6: e6}


def main(saida: Path | None = None, gerar_pdf: bool = True) -> int:
    """Grava os previews em `saida`. Devolve 0 se gerou PDFs, 1 se só conseguiu o HTML."""
    saida = saida or PASTA_PADRAO
    saida.mkdir(parents=True, exist_ok=True)
    htmls = {n: renderizar_html(n, ctx) for n, ctx in contextos_de_exemplo().items()}

    html_class = None
    if gerar_pdf:
        try:
            from weasyprint import HTML

            html_class = HTML
        except (ImportError, OSError) as erro:
            print(
                "WeasyPrint indisponível (faltam bibliotecas do sistema, veja docs/setup.md): "
                f"{erro}\nGravando só o HTML.",
                file=sys.stderr,
            )

    for n, html in htmls.items():
        if html_class is None:
            destino = saida / f"estilo_{n}.html"
            destino.write_text(html, encoding="utf-8")
        else:
            destino = saida / f"estilo_{n}.pdf"
            html_class(string=html).write_pdf(destino)
        print(destino)
    return 0 if html_class is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
