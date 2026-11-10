"""Templates de fatura: renderização, formatação PT/EN, rodapé sintético e paginação."""

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from confere_synth import render_preview
from confere_synth.render import (
    ESTILOS,
    TOMADOR_PADRAO,
    ContextoRender,
    DocInfo,
    FornecedorInfo,
    LinhaRender,
    ProcessoRefs,
    data_en,
    data_pt,
    dinheiro_en,
    dinheiro_pt,
    num_en,
    num_pt,
    qtd_en,
    qtd_pt,
    renderizar_html,
)

PT = (3, 4, 5)
EN = (1, 2, 6)
NUMERO = "FT-2026-000042"
TOTAL = Decimal("1234.56")


def contexto(n_linhas: int = 2, **doc: object) -> ContextoRender:
    linhas = [
        LinhaRender(
            descricao=f"Serviço {i}",
            valor_unit=Decimal("100.00"),
            valor=Decimal("100.00"),
            moeda="BRL",
            fatura_no=f"INV-{i}",
            bl="ATLX123456789",
            container="QZAU3400350",
        )
        for i in range(n_linhas)
    ]
    return ContextoRender(
        doc=DocInfo(
            **{
                "numero": NUMERO,
                "emissao": date(2026, 10, 14),
                "moeda": "BRL",
                "total": TOTAL,
                **doc,
            }
        ),
        fornecedor=FornecedorInfo(
            nome="Fornecedor Teste", endereco="Rua Fictícia, 1", email="x@teste.example"
        ),
        tomador=TOMADOR_PADRAO,
        processo_refs=ProcessoRefs(bl_master="ATLX123456789", conteineres=["QZAU3400350"]),
        linhas=linhas,
    )


# ------------------------------------------------------------- formatação


@pytest.mark.parametrize(
    ("valor", "pt", "en"),
    [
        (Decimal("1234.56"), "1.234,56", "1,234.56"),
        (Decimal("0.5"), "0,50", "0.50"),
        (Decimal("1234567.891"), "1.234.567,89", "1,234,567.89"),
        (Decimal("-12.345"), "-12,34", "-12.34"),  # ROUND_HALF_EVEN
        (Decimal("0.125"), "0,12", "0.12"),
        (Decimal("2.675"), "2,68", "2.68"),
        (0, "0,00", "0.00"),
    ],
)
def test_formatos_numericos(valor: Decimal | int, pt: str, en: str) -> None:
    assert num_pt(valor) == pt and num_en(valor) == en


def test_quantidade_sem_zeros_a_direita() -> None:
    assert qtd_pt(Decimal(2)) == "2" and qtd_en(Decimal(2)) == "2"
    assert qtd_pt(Decimal("2.50")) == "2,5" and qtd_en(Decimal("2.50")) == "2.5"
    assert qtd_pt(Decimal(1500)) == "1.500" and qtd_en(Decimal(1500)) == "1,500"


def test_dinheiro_e_datas() -> None:
    assert dinheiro_pt(Decimal("12345.67"), "BRL") == "R$ 12.345,67"
    assert dinheiro_pt(Decimal(380), "USD") == "USD 380,00"
    assert dinheiro_en(Decimal(380), "USD") == "USD 380.00"
    assert data_pt(date(2026, 10, 4)) == "04/10/2026"
    assert data_en(date(2026, 10, 4)) == "04 Oct 2026"


# -------------------------------------------------------------- templates


@pytest.mark.parametrize("estilo", ESTILOS)
def test_renderiza_com_numero_e_total_formatado(estilo: int) -> None:
    html = renderizar_html(estilo, contexto())
    assert NUMERO in html
    if estilo in PT:
        assert "1.234,56" in html and "1,234.56" not in html
    else:
        assert "1,234.56" in html and "1.234,56" not in html


@pytest.mark.parametrize("estilo", ESTILOS)
def test_rodape_sintetico_e_pagina_a4(estilo: int) -> None:
    html = renderizar_html(estilo, contexto())
    assert "SINTÉTICO — dados fictícios" in html
    assert re.search(r"size:\s*A4;\s*margin:\s*14mm", html)
    assert '<html lang="' in html and "<!doctype html>" in html


@pytest.mark.parametrize("estilo", ESTILOS)
def test_sem_recursos_externos(estilo: int) -> None:
    html = renderizar_html(estilo, contexto())
    assert not re.search(r"(src|href)\s*=", html)
    assert not re.search(r"url\(|@import|https?://", html)


@pytest.mark.parametrize("estilo", ESTILOS)
def test_texto_de_documento_e_escapado(estilo: int) -> None:
    ctx = contexto()
    ctx = ctx.model_copy(update={"fornecedor": ctx.fornecedor.model_copy(
        update={"nome": "A&B <script>alert(1)</script> Ltda."}
    )})  # fmt: skip
    html = renderizar_html(estilo, ctx)
    assert "<script>" not in html and "A&amp;B &lt;script&gt;" in html


@pytest.mark.parametrize("estilo", ESTILOS)
def test_sem_linhas_nem_vencimento_nao_quebra(estilo: int) -> None:
    html = renderizar_html(estilo, contexto(n_linhas=0))
    assert NUMERO in html


def test_estilo_invalido() -> None:
    for n in (0, 7):
        with pytest.raises(ValueError, match="entre 1 e 6"):
            renderizar_html(n, contexto())


def test_templates_existem_no_pacote() -> None:
    pasta = Path(render_preview.__file__).parent / "templates"
    assert {p.name for p in pasta.glob("estilo_*.html.j2")} == {
        f"estilo_{n}.html.j2" for n in ESTILOS
    }


# ---------------------------------------------------- particularidades


def test_estilo_1_bloco_de_embarque() -> None:
    html = renderizar_html(1, contexto())
    for rotulo in ("INVOICE", "Bill of Lading", "Vessel / Voyage", "Containers", "<svg"):
        assert rotulo in html
    assert "Description" in html and "Qty" in html and "Rate" in html and "Amount" in html


def test_estilo_2_sem_logo_e_com_refs_por_linha() -> None:
    ctx = contexto(moeda="EUR")
    linha = ctx.linhas[0].model_copy(update={"refs_linha": ["QZAU3400350"], "moeda": "EUR"})
    ctx = ctx.model_copy(update={"linhas": [linha, *ctx.linhas[1:]]})
    html = renderizar_html(2, ctx)
    assert "DEBIT NOTE" in html.upper() and "<svg" not in html
    assert "QZAU3400350" in html and "EUR 1,234.56" in html


def test_estilo_3_processo_do_cliente_vazio_ou_preenchido() -> None:
    sem = renderizar_html(3, contexto())
    assert "Processo do cliente:" in sem and '<span class="valor"></span>' in sem
    ctx = contexto()
    ctx = ctx.model_copy(
        update={"processo_refs": ctx.processo_refs.model_copy(update={"ref_cliente": "PO-12345"})}
    )
    assert '<span class="valor">PO-12345</span>' in renderizar_html(3, ctx)
    for col in ("Código", "Descrição", "Quantidade", "Valor Unit.", "Valor Total", "R$ 1.234,56"):
        assert col in sem


def test_estilo_4_periodo_dias_e_percentual() -> None:
    ctx = contexto()
    linha = ctx.linhas[0].model_copy(
        update={
            "periodo": (date(2026, 10, 2), date(2026, 10, 12)),
            "base_cif": Decimal("300000.00"),
            "percentual": Decimal("0.35"),
        }
    )
    html = renderizar_html(4, ctx.model_copy(update={"linhas": [linha]}))
    assert "02/10/2026" in html and "12/10/2026" in html
    assert ">10<" in html and "300.000,00" in html and "0,35" in html


def test_estilo_5_subtotais_por_secao() -> None:
    ctx = contexto()
    linhas = [
        ctx.linhas[0].model_copy(update={"secao": "reembolso", "valor": Decimal("200.50")}),
        ctx.linhas[1].model_copy(update={"secao": "honorario", "valor": Decimal("1034.06")}),
    ]
    html = renderizar_html(5, ctx.model_copy(update={"linhas": linhas}))
    assert "Subtotal A" in html and "Subtotal B" in html
    assert "200,50" in html and "1.034,06" in html and "1.234,56" in html


@pytest.mark.parametrize(("n_linhas", "paginas"), [(1, 1), (25, 1), (26, 2), (50, 2), (51, 3)])
def test_estilo_6_pagina_a_cada_25_linhas(n_linhas: int, paginas: int) -> None:
    html = renderizar_html(6, contexto(n_linhas=n_linhas))
    assert len(re.findall(r'<section class="pagina', html)) == paginas
    assert f"Page {paginas} of {paginas}" in html
    assert html.count("TOTAL DUE") == 1  # só na última página
    assert "INV-0" in html and f"INV-{n_linhas - 1}" in html


# --------------------------------------------------------------- modelos


def test_email_do_fornecedor_deve_ser_example() -> None:
    with pytest.raises(ValidationError):
        FornecedorInfo(nome="X", endereco="Y", email="contato@empresa.com")


def test_tomador_padrao_e_ficticio() -> None:
    assert TOMADOR_PADRAO.nome == "Agência Demo Cargas Ltda. (fictícia)"
    assert TOMADOR_PADRAO.cnpj and TOMADOR_PADRAO.cnpj.startswith("00.000.")


# --------------------------------------------------------------- preview


def test_exemplos_de_preview_renderizam_nos_6_estilos() -> None:
    exemplos = render_preview.contextos_de_exemplo()
    assert set(exemplos) == set(ESTILOS)
    for n, ctx in exemplos.items():
        html = renderizar_html(n, ctx)
        assert ctx.doc.numero in html
        assert (num_pt if n in PT else num_en)(ctx.doc.total) in html
    assert html.count("<section") == 2  # extrato com 32 linhas → 2 páginas


def test_main_grava_html_quando_nao_pede_pdf(tmp_path: Path) -> None:
    assert render_preview.main(tmp_path, gerar_pdf=False) == 1
    assert {p.name for p in tmp_path.iterdir()} == {f"estilo_{n}.html" for n in ESTILOS}


def test_main_grava_pdfs_quando_o_weasyprint_funciona(tmp_path: Path) -> None:
    try:
        import weasyprint  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("WeasyPrint sem as bibliotecas do sistema (Pango)")
    assert render_preview.main(tmp_path) == 0
    pdfs = sorted(tmp_path.glob("estilo_*.pdf"))
    assert len(pdfs) == 6 and all(p.read_bytes().startswith(b"%PDF") for p in pdfs)
