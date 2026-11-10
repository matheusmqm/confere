"""Injeção de erros (CF-36): configuração, cada tipo, ordem, extratos e o cenário de câmbio."""

import random
import re
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from confere_core.costcode.catalogo import Catalogo
from confere_core.fx.tabela import TabelaPTAX
from confere_synth import cambio, erros, faturas
from confere_synth.erros import ConfigErros, _quantos, injetar
from confere_synth.faturas import contexto_do_documento, gerar_documentos_limpos
from confere_synth.modelos import DocumentoSintetico, ErroInjetado, Mundo
from confere_synth.mundo import gerar_mundo
from confere_synth.render import num_pt, renderizar_html

RAIZ = Path(__file__).resolve().parents[3]
CENTAVO = Decimal("0.01")
ORDEM_DOS_PASSOS = [
    "valor_acima",
    "taxa_nao_prevista",
    "cambio_errado",
    "referencia_cruzada",
    "duplicada",
]


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    return Catalogo.carregar(RAIZ / "config" / "codigos_custo.yaml")


@pytest.fixture(scope="module")
def mundo(catalogo: Catalogo) -> Mundo:
    return gerar_mundo(42, catalogo)


@pytest.fixture(scope="module")
def limpos(mundo: Mundo, catalogo: Catalogo, ptax_completa: TabelaPTAX) -> list[DocumentoSintetico]:
    return gerar_documentos_limpos(random.Random(7), mundo, catalogo, ptax_completa)


@pytest.fixture(scope="module")
def cfg() -> ConfigErros:
    return ConfigErros.carregar()


@pytest.fixture(scope="module")
def resultado(
    limpos: list[DocumentoSintetico], mundo: Mundo, cfg: ConfigErros, ptax_completa: TabelaPTAX
) -> tuple[list[DocumentoSintetico], list[ErroInjetado]]:
    return injetar(random.Random(3), limpos, mundo, cfg, ptax=ptax_completa)


def por_id(docs: list[DocumentoSintetico]) -> dict[uuid.UUID, DocumentoSintetico]:
    return {d.id: d for d in docs}


def do_tipo(lista: list[ErroInjetado], tipo: str) -> list[ErroInjetado]:
    return [e for e in lista if e.tipo == tipo]


def soma(doc: DocumentoSintetico) -> Decimal:
    return sum((linha.valor for linha in doc.linhas), Decimal(0))


# ---------------------------------------------------------------- configuração


def test_config_padrao_tem_os_valores_da_tarefa(cfg: ConfigErros) -> None:
    assert (cfg.valor_acima.taxa, cfg.valor_acima.fator_min, cfg.valor_acima.fator_max) == (0.06, 1.05, 1.40)
    assert cfg.duplicada.taxa == 0.02 and cfg.referencia_cruzada.taxa == 0.02
    assert cfg.taxa_nao_prevista.taxa == 0.04
    assert cfg.taxa_nao_prevista.descricoes == [
        "Documentation fee", "Taxa administrativa", "Handling fee", "Taxa de emissão de documento",
    ]  # fmt: skip
    assert (cfg.taxa_nao_prevista.valor_min_brl, cfg.taxa_nao_prevista.valor_max_brl) == (80, 450)
    assert (cfg.cambio_errado.taxa, cfg.cambio_errado.desvio_min, cfg.cambio_errado.desvio_max) == (0.03, 0.02, 0.05)
    assert cfg.cambio_errado.unidade == "fatura_brl_convertida"
    assert (cfg.ruido_visual.taxa, cfg.ruido_visual.unidade) == (0.15, "pdf")


def test_config_invalida(tmp_path: Path) -> None:
    base = (RAIZ / "config" / "erros.yaml").read_text(encoding="utf-8")
    for velho, novo in [
        ("fator_min: 1.05, fator_max: 1.40", "fator_min: 1.5, fator_max: 1.4"),
        ("taxa: 0.06", "taxa: 1.5"),
        ("desvio_min: 0.02, desvio_max: 0.05", "desvio_min: 0.06, desvio_max: 0.05"),
        ("valor_min_brl: 80, valor_max_brl: 450", "valor_min_brl: 500, valor_max_brl: 450"),
    ]:
        arquivo = tmp_path / "erros.yaml"
        arquivo.write_text(base.replace(velho, novo), encoding="utf-8")
        with pytest.raises(ValidationError):
            ConfigErros.carregar(arquivo)


@pytest.mark.parametrize(
    ("taxa", "n", "esperado"), [(0.06, 0, 0), (0.02, 10, 1), (0.5, 10, 5), (0.06, 100, 6)]
)
def test_cota_com_minimo_de_um(taxa: float, n: int, esperado: int) -> None:
    assert _quantos(taxa, n) == esperado


# ------------------------------------------------------------------- visão geral


def test_todos_os_tipos_aparecem_e_na_ordem_dos_passos(
    resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:
    _, lista = resultado
    tipos = [e.tipo for e in lista]
    assert set(tipos) == set(ORDEM_DOS_PASSOS)
    posicoes = [ORDEM_DOS_PASSOS.index(t) for t in tipos]
    assert posicoes == sorted(posicoes)  # valor_acima → taxa → câmbio → referência → duplicada


def test_ruido_visual_nao_e_aplicado_aqui(
    resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:
    assert not do_tipo(resultado[1], "ruido_visual")


def test_cada_erro_esta_no_documento_certo(
    resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:
    docs, lista = resultado
    mapa = por_id(docs)
    for e in lista:
        assert e in mapa[e.doc_id].erros
    assert sum(len(d.erros) for d in docs) == len(lista)


def test_so_faturas_e_notas_de_debito_em_pdf_recebem_erro(
    resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:
    docs, _ = resultado
    for d in docs:
        if d.erros:
            assert d.formato == "pdf" and d.tipo in ("fatura", "nota_debito")
    assert all(d.erros == [] for d in docs if d.tipo == "extrato")


def test_total_acompanha_as_linhas(resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]]) -> None:
    for d in resultado[0]:
        assert d.total == soma(d)


def test_determinismo(
    limpos: list[DocumentoSintetico], mundo: Mundo, cfg: ConfigErros, ptax_completa: TabelaPTAX,
    resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:  # fmt: skip
    igual = injetar(random.Random(3), limpos, mundo, cfg, ptax=ptax_completa)
    assert igual == resultado
    assert injetar(random.Random(4), limpos, mundo, cfg, ptax=ptax_completa) != resultado


def test_nao_altera_os_documentos_de_entrada(
    limpos: list[DocumentoSintetico], resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:
    assert all(d.erros == [] for d in limpos)
    assert len(resultado[0]) > len(limpos)  # as cópias da duplicada


# ----------------------------------------------------------------- valor_acima


def test_valor_acima(
    limpos: list[DocumentoSintetico], mundo: Mundo, ptax_completa: TabelaPTAX,
    resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:  # fmt: skip
    docs, lista = resultado
    antes, depois = por_id(limpos), por_id(docs)
    provs = {p.id: p for p in mundo.provisoes}
    erros_va = do_tipo(lista, "valor_acima")
    assert erros_va
    for e in erros_va:
        nova = depois[e.doc_id].linhas[(e.linha_ordem or 0) - 1]
        limpa = antes[e.doc_id].linhas[(e.linha_ordem or 0) - 1]
        assert Decimal("1.0499") <= nova.valor / limpa.valor <= Decimal("1.4001")
        previsto = provs[nova.provisao_id or uuid.UUID(int=0)].valor
        assert e.valor_erro_moeda == nova.valor - previsto > 0 and e.moeda == nova.moeda
        assert e.valor_erro_brl == cambio.para_brl(
            ptax_completa, nova.valor - previsto, nova.moeda, depois[e.doc_id].emissao
        )
        assert abs(nova.quantidade * nova.valor_unit - nova.valor) <= Decimal("0.05")


def test_valor_acima_fica_perto_de_6_por_cento_das_linhas(
    limpos: list[DocumentoSintetico], resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:
    elegiveis = sum(
        1
        for d in limpos
        if d.tipo in ("fatura", "nota_debito") and not any(ln.moeda_origem for ln in d.linhas)
        for ln in d.linhas
        if ln.provisao_id
    )
    assert abs(len(do_tipo(resultado[1], "valor_acima")) - round(0.06 * elegiveis)) <= 1


def test_faturas_convertidas_nao_recebem_valor_acima_nem_taxa(
    resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:
    docs, lista = resultado
    mapa = por_id(docs)
    for e in lista:
        if e.tipo in ("valor_acima", "taxa_nao_prevista"):
            assert not any(ln.moeda_origem for ln in mapa[e.doc_id].linhas)


# ------------------------------------------------------------ taxa_nao_prevista


def test_taxa_nao_prevista(
    mundo: Mundo, cfg: ConfigErros, ptax_completa: TabelaPTAX,
    resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:  # fmt: skip
    docs, lista = resultado
    mapa = por_id(docs)
    forn = {f.id: f for f in mundo.fornecedores}
    erros_tn = do_tipo(lista, "taxa_nao_prevista")
    assert erros_tn
    for e in erros_tn:
        doc = mapa[e.doc_id]
        nova = doc.linhas[(e.linha_ordem or 0) - 1]
        assert nova.provisao_id is None and nova.descricao in cfg.taxa_nao_prevista.descricoes
        assert nova.codigo_custo in ("DOC_FEE_ORIG", "HANDLING_AGENTE", erros.CODIGO_FORA_DO_CATALOGO)
        assert (e.valor_erro_moeda, e.moeda) == (nova.valor, doc.moeda) and nova.valor > 0
        assert e.valor_erro_brl is not None and Decimal("79") <= e.valor_erro_brl <= Decimal("451")
        em_portugues = nova.descricao.lower().startswith("taxa")
        assert em_portugues == (forn[doc.fornecedor_id].idioma == "pt")


def test_taxa_nao_prevista_codigo_mais_proximo() -> None:
    assert erros._CODIGO_PROXIMO["Documentation fee"] == "DOC_FEE_ORIG"
    assert erros._CODIGO_PROXIMO["Handling fee"] == "HANDLING_AGENTE"
    assert erros.CODIGO_FORA_DO_CATALOGO == "OUTROS"  # "Taxa administrativa" cai aqui


# ---------------------------------------------------------------- cambio_errado


def test_o_mundo_tem_faturas_em_brl_de_valor_previsto_em_dolar(
    limpos: list[DocumentoSintetico], ptax_completa: TabelaPTAX
) -> None:
    convertidas = [d for d in limpos if any(ln.moeda_origem for ln in d.linhas)]
    assert convertidas and all(d.fornecedor_id == "consolidadora-aurora" for d in convertidas)
    for d in convertidas:
        assert d.moeda == "BRL" and d.estilo_id == 3
        info = [ln for ln in d.linhas if ln.informativa]
        assert len(info) == 1 and info[0].descricao.startswith("Taxa de câmbio aplicada: ")
        taxa = cambio.venda(ptax_completa, "USD", d.emissao)
        for ln in d.linhas:
            if ln.informativa:
                continue
            assert ln.moeda == "BRL" and ln.moeda_origem == "USD" and ln.taxa_cambio == taxa
            assert ln.valor_origem is not None and ln.taxa_cambio is not None
            assert ln.valor == (ln.valor_origem * ln.taxa_cambio).quantize(CENTAVO)


def test_fatura_convertida_mostra_a_conta_na_linha(limpos: list[DocumentoSintetico]) -> None:
    doc = next(d for d in limpos if any(ln.moeda_origem for ln in d.linhas))
    ln = next(ln for ln in doc.linhas if not ln.informativa)
    assert ln.valor_origem is not None and ln.taxa_cambio is not None
    esperado = f"USD {num_pt(ln.valor_origem)} × taxa {num_pt(ln.taxa_cambio, 4)} = R$ {num_pt(ln.valor)}"
    texto = [c.cambio for c in contexto_do_documento(doc).linhas if c.cambio]
    assert esperado in texto
    html = renderizar_html(doc.estilo_id, contexto_do_documento(doc))
    assert esperado in html and "Taxa de câmbio aplicada" in html


def test_cambio_errado(
    limpos: list[DocumentoSintetico], resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:
    docs, lista = resultado
    antes, depois = por_id(limpos), por_id(docs)
    erros_c = do_tipo(lista, "cambio_errado")
    assert len(erros_c) >= 1  # cota mínima: o cenário sempre existe
    for e in erros_c:
        novo, limpo = depois[e.doc_id], antes[e.doc_id]
        assert novo.fornecedor_id == "consolidadora-aurora" and novo.moeda == "BRL"
        diferenca = Decimal(0)
        for ln_novo, ln_limpo in zip(novo.linhas, limpo.linhas, strict=True):
            if ln_novo.informativa:
                assert num_pt(ln_novo.taxa_cambio or Decimal(0), 4) in ln_novo.descricao
                continue
            assert ln_novo.taxa_cambio is not None and ln_limpo.taxa_cambio is not None
            desvio = ln_novo.taxa_cambio / ln_limpo.taxa_cambio - 1
            assert Decimal("0.0199") <= desvio <= Decimal("0.0501")
            assert ln_novo.valor == (ln_novo.valor_origem * ln_novo.taxa_cambio).quantize(CENTAVO)  # type: ignore[operator]
            assert ln_novo.valor > ln_limpo.valor
            diferenca += ln_novo.valor - ln_limpo.valor
        assert e.linha_ordem is None and e.moeda == "BRL"
        assert e.valor_erro_moeda == e.valor_erro_brl == diferenca > 0


# ------------------------------------------------------------- referencia_cruzada


def test_referencia_cruzada(
    limpos: list[DocumentoSintetico], mundo: Mundo,
    resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:  # fmt: skip
    docs, lista = resultado
    antes, depois = por_id(limpos), por_id(docs)
    proc = {p.id: p for p in mundo.processos}
    mestres = {
        next(r.valor for r in p.referencias if r.tipo == "bl_master"): p
        for p in mundo.processos
        if p.armador_id
    }
    erros_r = do_tipo(lista, "referencia_cruzada")
    assert erros_r
    for e in erros_r:
        novo, limpo = depois[e.doc_id], antes[e.doc_id]
        assert novo.processo_id == limpo.processo_id  # o gabarito mantém o processo verdadeiro
        verdadeiro = proc[novo.processo_id or uuid.UUID(int=0)]
        citado = next(r.valor for r in novo.referencias if r.tipo == "bl_master")
        antigo = next(r.valor for r in limpo.referencias if r.tipo == "bl_master")
        assert citado != antigo and mestres[antigo].id == verdadeiro.id
        outro = mestres[citado]
        assert outro.id != verdadeiro.id and outro.armador_id == verdadeiro.armador_id
        for ln_novo, ln_limpo in zip(novo.linhas, limpo.linhas, strict=True):
            if antigo in [r.valor for r in ln_limpo.referencias]:
                assert citado in [r.valor for r in ln_novo.referencias]
            assert antigo not in [r.valor for r in ln_novo.referencias]
        assert (e.valor_erro_moeda, e.valor_erro_brl, e.linha_ordem) == (None, None, None)
        assert citado in e.descricao and antigo in e.descricao


# ----------------------------------------------------------------------- duplicada


def test_duplicada(
    resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]], ptax_completa: TabelaPTAX
) -> None:
    docs, lista = resultado
    mapa = por_id(docs)
    copias = [d for d in docs if d.duplicata_de is not None]
    erros_d = do_tipo(lista, "duplicada")
    assert copias and len(copias) == len(erros_d)
    for copia in copias:
        original = mapa[copia.duplicata_de or uuid.UUID(int=0)]
        assert original.duplicata_de is None  # não se duplica cópia
        assert copia.id != original.id and copia.numero == original.numero
        assert copia.arquivo == f"documentos/{copia.id}.pdf" != original.arquivo
        assert copia.sha256 is None and copia.fornecedor_id == original.fornecedor_id
        # a cópia sai já com os outros erros do original (mesmas linhas e total)
        assert copia.linhas == original.linhas and copia.total == original.total
        (erro,) = copia.erros
        assert erro.tipo == "duplicada" and erro.doc_id == copia.id and erro.linha_ordem is None
        assert (erro.valor_erro_moeda, erro.moeda) == (original.total, original.moeda)
        assert all(e.tipo != "duplicada" for e in original.erros)  # o original é o legítimo
        if copia.duplicata_identica:
            assert copia.emissao == original.emissao and copia.vencimento == original.vencimento
        else:
            assert copia.emissao == original.emissao + timedelta(days=1)
            if original.vencimento:
                assert copia.vencimento == original.vencimento + timedelta(days=1)


def test_metade_das_duplicatas_e_identica(
    resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:
    copias = [d for d in resultado[0] if d.duplicata_de is not None]
    identicas = sum(d.duplicata_identica for d in copias)
    assert identicas == (len(copias) + 1) // 2 and len(copias) - identicas == len(copias) // 2
    if len(copias) >= 2:
        assert 0 < identicas < len(copias)  # os dois tipos existem


def test_duplicata_identica_copia_o_pdf_e_a_re_renderizada_nao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:  # fmt: skip
    def pdf_falso(html: str, destino: Path) -> None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"%PDF-falso " + html.encode("utf-8"))

    monkeypatch.setattr(faturas, "_escrever_pdf", pdf_falso)
    docs, _ = resultado
    mapa = por_id(docs)
    identica = next(d for d in docs if d.duplicata_identica)
    original = mapa[identica.duplicata_de or uuid.UUID(int=0)]

    with pytest.raises(FileNotFoundError, match="renderize o original"):
        faturas.renderizar(identica, tmp_path)  # sem o original no disco
    a = faturas.renderizar(original, tmp_path)
    b = faturas.renderizar(identica, tmp_path)
    assert a != b and a.read_bytes() == b.read_bytes()
    assert faturas.sha256_de(a) == faturas.sha256_de(b)

    re_renderizada = next((d for d in docs if d.duplicata_de and not d.duplicata_identica), None)
    if re_renderizada is not None:
        origem = faturas.renderizar(mapa[re_renderizada.duplicata_de or uuid.UUID(int=0)], tmp_path)
        copia = faturas.renderizar(re_renderizada, tmp_path)
        assert faturas.sha256_de(origem) != faturas.sha256_de(copia)  # emissão +1 dia


# ---------------------------------------------------------------------- extratos


def test_extratos_espelham_as_faturas_alteradas(
    resultado: tuple[list[DocumentoSintetico], list[ErroInjetado]],
) -> None:
    docs, _ = resultado
    faturas_ = {(d.fornecedor_id, d.numero): d for d in docs if d.tipo != "extrato" and d.duplicata_de is None}
    extratos = [d for d in docs if d.tipo == "extrato"]
    assert extratos
    for ext in extratos:
        assert ext.total == soma(ext)
        for ln in ext.linhas:
            origem = faturas_[(ext.fornecedor_id, ln.fatura_no or "")]
            esperado = [o for o in origem.linhas if o.provisao_id == ln.provisao_id and o.descricao == ln.descricao]
            assert esperado and esperado[0].valor == ln.valor
        listadas = {(ln.fatura_no, ln.provisao_id) for ln in ext.linhas}
        for numero in {ln.fatura_no for ln in ext.linhas}:
            origem = faturas_[(ext.fornecedor_id, numero or "")]
            assert {(numero, o.provisao_id) for o in origem.linhas if not o.informativa} <= listadas


# ------------------------------------------------------------------ sem PTAX


def test_sem_ptax_o_valor_em_brl_fica_nulo_e_nada_e_inventado(
    limpos: list[DocumentoSintetico], mundo: Mundo, cfg: ConfigErros
) -> None:
    docs, lista = injetar(random.Random(3), limpos, mundo, cfg, ptax=TabelaPTAX([]))
    mapa = por_id(docs)
    assert lista
    for e in lista:
        if e.valor_erro_moeda is None:
            continue
        if e.moeda == "BRL":
            assert e.valor_erro_brl == e.valor_erro_moeda
        else:
            assert e.valor_erro_brl is None  # sem cotação: não se converte
    for e in do_tipo(lista, "taxa_nao_prevista"):
        assert mapa[e.doc_id].moeda == "BRL"  # sem câmbio, só entra onde não precisa dele
