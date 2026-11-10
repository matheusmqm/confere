"""Faturas sintéticas limpas: gabarito por linha, valores, numeração, extratos e renderização."""

import random
import re
import uuid
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from confere_core.costcode.catalogo import Catalogo
from confere_core.fx.tabela import TabelaPTAX
from confere_synth import faturas
from confere_synth.faturas import (
    ENDERECOS,
    NUMEROS,
    contexto_do_documento,
    gerar_documentos_limpos,
    renderizar,
    sha256_de,
)
from confere_synth.modelos import DocumentoSintetico, Mundo
from confere_synth.mundo import gerar_mundo
from confere_synth.render import num_en, num_pt, renderizar_html

YAML = Path(__file__).resolve().parents[3] / "config" / "codigos_custo.yaml"
PT = {3, 4, 5}


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    return Catalogo.carregar(YAML)


@pytest.fixture(scope="module")
def mundo(catalogo: Catalogo) -> Mundo:
    return gerar_mundo(42, catalogo)


@pytest.fixture(scope="module")
def docs(mundo: Mundo, catalogo: Catalogo, ptax_completa: TabelaPTAX) -> list[DocumentoSintetico]:
    return gerar_documentos_limpos(random.Random(7), mundo, catalogo, ptax_completa)


@pytest.fixture(scope="module")
def faturas_(docs: list[DocumentoSintetico]) -> list[DocumentoSintetico]:
    return [d for d in docs if d.tipo != "extrato"]


@pytest.fixture(scope="module")
def extratos(docs: list[DocumentoSintetico]) -> list[DocumentoSintetico]:
    return [d for d in docs if d.tipo == "extrato"]


# ------------------------------------------------------------- cobertura


def test_toda_provisao_vira_uma_linha_exceto_transportadora(
    mundo: Mundo, faturas_: list[DocumentoSintetico]
) -> None:
    tipo = {f.id: f.tipo for f in mundo.fornecedores}
    esperadas = {p.id for p in mundo.provisoes if tipo[p.fornecedor_id] != "transportadora"}
    linhas = [linha.provisao_id for d in faturas_ for linha in d.linhas if not linha.informativa]
    assert len(linhas) == len(set(linhas)) == len(esperadas)
    assert set(linhas) == esperadas


def test_nenhum_documento_de_transportadora(mundo: Mundo, docs: list[DocumentoSintetico]) -> None:
    transportadoras = {f.id for f in mundo.fornecedores if f.tipo == "transportadora"}
    assert not {d.fornecedor_id for d in docs} & transportadoras


def test_gabarito_da_linha_bate_com_a_provisao(
    mundo: Mundo, faturas_: list[DocumentoSintetico]
) -> None:
    provs = {p.id: p for p in mundo.provisoes}
    for d in faturas_:
        for linha in d.linhas:
            if linha.informativa:  # "Taxa de câmbio aplicada": sem provisão
                assert linha.provisao_id is None and linha.valor == 0
                continue
            p = provs[linha.provisao_id or uuid.UUID(int=0)]
            assert (linha.processo_id, linha.codigo_custo) == (p.processo_id, p.codigo_custo)
            assert p.fornecedor_id == d.fornecedor_id and linha.moeda == d.moeda
            # fornecedor nacional fatura em BRL o que é previsto em moeda estrangeira
            assert p.moeda == (linha.moeda_origem or linha.moeda)


def test_uma_fatura_por_processo_fornecedor_e_moeda(
    mundo: Mundo, faturas_: list[DocumentoSintetico]
) -> None:
    donos: dict[tuple[uuid.UUID, str, str], int] = Counter()
    for d in faturas_:
        for pid in {linha.processo_id for linha in d.linhas}:
            donos[(pid or uuid.UUID(int=0), d.fornecedor_id, d.moeda)] += 1
    assert set(donos.values()) == {1}


# ------------------------------------------------------------------ valores


def test_valores_das_linhas(mundo: Mundo, faturas_: list[DocumentoSintetico]) -> None:
    provs = {p.id: p for p in mundo.provisoes}
    iguais = inteiros = centavos = 0
    todas = [linha for d in faturas_ for linha in d.linhas if not linha.informativa]
    for linha in todas:
        p = provs[linha.provisao_id or uuid.UUID(int=0)]
        valor = linha.valor_origem if linha.valor_origem is not None else linha.valor
        dif = abs(valor - p.valor)  # nas convertidas, compara o valor na moeda de origem
        assert linha.valor > 0 and dif <= Decimal("0.50")
        if dif == 0:
            iguais += 1
        elif valor == valor.quantize(Decimal(1)) and valor != p.valor:
            inteiros += 1
        else:
            centavos += 1
    n = len(todas)
    assert iguais / n > 0.75
    assert 0.04 < (inteiros + centavos) / n < 0.25  # ~10% inteiros + ~5% centavos
    assert inteiros > 0 and centavos > 0


def test_total_e_a_soma_exata_das_linhas(docs: list[DocumentoSintetico]) -> None:
    for d in docs:
        assert d.total == sum((linha.valor for linha in d.linhas), Decimal(0))
        assert {linha.moeda for linha in d.linhas} == {d.moeda}


def test_quantidade_vezes_unitario_perto_do_valor(faturas_: list[DocumentoSintetico]) -> None:
    for d in faturas_:
        for linha in d.linhas:
            assert abs(linha.quantidade * linha.valor_unit - linha.valor) <= Decimal("0.05")


def test_descricao_vem_dos_nomes_de_taxa_do_fornecedor(
    mundo: Mundo, faturas_: list[DocumentoSintetico]
) -> None:
    nomes = {f.id: f.nomes_taxa for f in mundo.fornecedores}
    com_conteiner = 0
    for d in faturas_:
        for linha in d.linhas:
            if linha.informativa:
                continue
            m = re.fullmatch(r"(.*) - ([A-Z]{4}\d{7})", linha.descricao)
            base = m.group(1) if m else linha.descricao
            com_conteiner += bool(m)
            assert base in nomes[d.fornecedor_id][linha.codigo_custo]
    assert com_conteiner > 0


# -------------------------------------------------------------- documentos


def _padrao_numero(forn_id: str) -> re.Pattern[str]:
    antes, resto = NUMEROS[forn_id].split("{n:")
    largura = int(resto[1 : resto.index("d")])
    depois = resto[resto.index("}") + 1 :]
    return re.compile(re.escape(antes) + rf"(\d{{{largura}}})" + re.escape(depois))


def test_numeros_unicos_com_padrao_do_fornecedor_e_crescentes(
    faturas_: list[DocumentoSintetico],
) -> None:
    por_forn: dict[str, list[DocumentoSintetico]] = defaultdict(list)
    for d in faturas_:
        por_forn[d.fornecedor_id].append(d)
    for forn_id, ds in por_forn.items():
        padrao = _padrao_numero(forn_id)
        numeros = {}
        for d in ds:
            m = padrao.fullmatch(d.numero)
            assert m, (forn_id, d.numero)
            numeros[d.numero] = int(m.group(1))
        assert len(set(numeros.values())) == len(ds)
        emissoes = [d.emissao for d in sorted(ds, key=lambda d: numeros[d.numero])]
        assert emissoes == sorted(emissoes), forn_id  # o número cresce com a emissão
    exemplo = next(d for d in faturas_ if d.fornecedor_id == "atlantida-ocean-lines")
    assert re.fullmatch(r"ATL-INV-26-\d{6}", exemplo.numero)


def test_emissao_e_vencimento(mundo: Mundo, faturas_: list[DocumentoSintetico]) -> None:
    eta = {p.id: p.eta for p in mundo.processos}
    for d in faturas_:
        base = min(eta[linha.processo_id] for linha in d.linhas if linha.processo_id)
        assert base - timedelta(days=5) <= d.emissao <= base + timedelta(days=20)
        assert d.vencimento is not None
        assert (d.vencimento - d.emissao).days in (15, 30)


def test_estilo_tipo_e_arquivo(mundo: Mundo, docs: list[DocumentoSintetico]) -> None:
    forn = {f.id: f for f in mundo.fornecedores}
    for d in docs:
        assert d.arquivo == f"documentos/{d.id}.pdf"
        assert d.formato == "pdf" and d.sha256 is None
        if d.tipo == "extrato":
            assert d.estilo_id == 6
        else:
            assert d.estilo_id == forn[d.fornecedor_id].estilo_id
            assert d.tipo == (
                "nota_debito"
                if forn[d.fornecedor_id].tipo in ("agente_exterior", "armazem")
                else "fatura"
            )
    assert len({d.id for d in docs}) == len(docs)


def test_emitente_ficticio(mundo: Mundo, docs: list[DocumentoSintetico]) -> None:
    forn = {f.id: f for f in mundo.fornecedores}
    assert set(ENDERECOS) == set(forn)
    for d in docs:
        assert d.emitente.email.endswith(".example")
        assert d.emitente.cnpj == forn[d.fornecedor_id].cnpj_ficticio


def test_fatura_de_dois_processos_em_15_por_cento_das_de_armador_e_agente(
    mundo: Mundo, faturas_: list[DocumentoSintetico]
) -> None:
    tipo = {f.id: f.tipo for f in mundo.fornecedores}
    alvo = [d for d in faturas_ if tipo[d.fornecedor_id] in ("armador", "agente_exterior")]
    juntas = [d for d in alvo if len({linha.processo_id for linha in d.linhas}) == 2]
    assert 0.08 <= len(juntas) / len(alvo) <= 0.22
    for d in juntas:
        assert d.processo_id is None and d.referencias == []
        assert all(
            linha.referencias for linha in d.linhas if not linha.informativa
        )  # referências por linha
    outras = [d for d in faturas_ if d not in juntas]
    assert all(d.processo_id is not None for d in outras)
    # só armador e agente juntam processos
    assert all(tipo[d.fornecedor_id] in ("armador", "agente_exterior") for d in juntas)


def test_o_que_cada_fornecedor_cita(mundo: Mundo, faturas_: list[DocumentoSintetico]) -> None:
    tipo = {f.id: f.tipo for f in mundo.fornecedores}
    proc = {p.id: p for p in mundo.processos}
    for d in faturas_:
        if d.processo_id is None:
            continue
        reais = {(r.tipo, r.valor) for r in proc[d.processo_id].referencias}
        assert {(r.tipo, r.valor) for r in d.referencias} <= reais
        if tipo[d.fornecedor_id] == "armador":
            assert any(r.tipo == "bl_master" for r in d.referencias)
            assert d.navio == proc[d.processo_id].navio
    tipos_citados = {tipo[d.fornecedor_id]: {r.tipo for r in d.referencias} for d in faturas_
                     if tipo[d.fornecedor_id] == "despachante" and d.processo_id}  # fmt: skip
    assert "ref_cliente" in tipos_citados["despachante"]


def test_linhas_de_armazenagem_e_secoes(faturas_: list[DocumentoSintetico]) -> None:
    arm = [linha for d in faturas_ for linha in d.linhas if linha.codigo_custo == "ARMAZENAGEM"]
    assert arm and all(linha.periodo and linha.base_cif and linha.percentual for linha in arm)
    assert all((e - s).days == 10 for linha in arm if linha.periodo for s, e in [linha.periodo])
    desp = [linha for d in faturas_ if d.fornecedor_id.startswith(("despachos", "lagoa"))
            for linha in d.linhas]  # fmt: skip
    assert {linha.secao for linha in desp} == {"reembolso", "honorario"}
    assert all(
        (linha.secao == "honorario") == (linha.codigo_custo in ("HONORARIO_DESPACHO", "EMISSAO_LI"))
        for linha in desp
    )


# ------------------------------------------------------------------ extratos


def test_um_extrato_por_armador(mundo: Mundo, extratos: list[DocumentoSintetico]) -> None:
    armadores = {f.id for f in mundo.fornecedores if f.tipo == "armador" and f.pais != "BR"}
    assert {d.fornecedor_id for d in extratos} == armadores and len(extratos) == 3
    for d in extratos:
        assert d.estilo_id == 6 and d.processo_id is None and d.moeda == "USD"
        processos = {linha.processo_id for linha in d.linhas}
        assert 4 <= len(processos) <= 8
        assert re.fullmatch(r"STM-[A-Z]{3}-\d{6}", d.numero)


def test_linhas_do_extrato_apontam_para_faturas_existentes(
    faturas_: list[DocumentoSintetico], extratos: list[DocumentoSintetico]
) -> None:
    por_numero = {(d.fornecedor_id, d.numero): d for d in faturas_}
    for ext in extratos:
        for linha in ext.linhas:
            assert linha.fatura_no and linha.bl
            origem = por_numero[(ext.fornecedor_id, linha.fatura_no)]
            assert linha.provisao_id in {x.provisao_id for x in origem.linhas}
        assert ext.emissao > max(por_numero[(ext.fornecedor_id, x.fatura_no or "")].emissao
                                 for x in ext.linhas)  # fmt: skip


# ----------------------------------------------------------- determinismo


def test_determinismo(mundo: Mundo, catalogo: Catalogo, ptax_completa: TabelaPTAX) -> None:
    a = gerar_documentos_limpos(random.Random(7), mundo, catalogo, ptax_completa)
    assert a == gerar_documentos_limpos(random.Random(7), mundo, catalogo, ptax_completa)
    assert a != gerar_documentos_limpos(random.Random(8), mundo, catalogo, ptax_completa)


# ------------------------------------------------------------- renderização


def test_todo_documento_renderiza_com_numero_e_total(docs: list[DocumentoSintetico]) -> None:
    for d in docs:
        html = renderizar_html(d.estilo_id, contexto_do_documento(d))
        assert d.numero in html
        formatar = num_pt if d.estilo_id in PT else num_en
        assert formatar(d.total) in html, (d.numero, d.estilo_id)
        assert "SINTÉTICO — dados fictícios" in html


def test_extrato_longo_pagina(extratos: list[DocumentoSintetico]) -> None:
    for d in extratos:
        html = renderizar_html(6, contexto_do_documento(d))
        esperado = -(-len(d.linhas) // 25)
        assert html.count('<section class="pagina') == esperado


def test_renderizar_grava_no_caminho_do_documento(
    docs: list[DocumentoSintetico], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def falso(html: str, destino: Path) -> None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(b"%PDF-falso " + html.encode("utf-8"))

    monkeypatch.setattr(faturas, "_escrever_pdf", falso)
    caminho = renderizar(docs[0], tmp_path)
    assert caminho == tmp_path / (docs[0].arquivo or "")
    assert (
        caminho.read_bytes().startswith(b"%PDF-falso")
        and docs[0].numero.encode() in caminho.read_bytes()
    )
    assert re.fullmatch(r"[0-9a-f]{64}", sha256_de(caminho))


def test_renderizar_exige_arquivo(docs: list[DocumentoSintetico], tmp_path: Path) -> None:
    sem_arquivo = docs[0].model_copy(update={"arquivo": None})
    with pytest.raises(ValueError, match="sem `arquivo`"):
        renderizar(sem_arquivo, tmp_path)


def test_pdf_real_e_reproduzivel(docs: list[DocumentoSintetico], tmp_path: Path) -> None:
    try:
        renderizar(docs[0], tmp_path / "a")
    except faturas.WeasyPrintIndisponivelError:
        pytest.skip("WeasyPrint sem as bibliotecas do sistema (Pango)")
    a = renderizar(docs[0], tmp_path / "a")
    b = renderizar(docs[0], tmp_path / "b")
    assert a.read_bytes().startswith(b"%PDF") and sha256_de(a) == sha256_de(b)


def test_sem_weasyprint_o_erro_e_especifico(
    docs: list[DocumentoSintetico], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins

    real = builtins.__import__

    def sem_weasyprint(nome: str, *args: object, **kwargs: object) -> object:
        if nome == "weasyprint":
            raise OSError("cannot load library 'libgobject-2.0-0'")
        return real(nome, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(builtins, "__import__", sem_weasyprint)
    with pytest.raises(faturas.WeasyPrintIndisponivelError, match="libgobject"):
        renderizar(docs[0], tmp_path)
    assert not (tmp_path / "documentos").exists()  # nada gravado
