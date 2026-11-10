"""CT-e 4.00 sintético (nfelib) e DACTE (brazilfiscalreport)."""

import random
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pymupdf
import pytest
from nfelib.cte.bindings.v4_0.cte_v4_00 import Cte

from confere_core.costcode.catalogo import Catalogo
from confere_synth import cte
from confere_synth.cte import (
    CIDADES_CLIENTE,
    COMPONENTES,
    MUNICIPIO_PORTO,
    CteGerado,
    chave_cte,
    chave_nfe_ficticia,
    chave_valida,
    dv_modulo11,
    gerar_ctes,
    gerar_dacte,
    gravar_xml,
    ler_xml,
    validar_xml,
)
from confere_synth.modelos import Mundo
from confere_synth.mundo import gerar_mundo
from confere_synth.render import TOMADOR_PADRAO

YAML = Path(__file__).resolve().parents[3] / "config" / "codigos_custo.yaml"
NS = {"c": "http://www.portalfiscal.inf.br/cte"}


@pytest.fixture(scope="module")
def mundo() -> Mundo:
    return gerar_mundo(42, Catalogo.carregar(YAML))


@pytest.fixture(scope="module")
def ctes(mundo: Mundo) -> list[CteGerado]:
    return gerar_ctes(random.Random(5), mundo)


def raiz(c: CteGerado) -> ET.Element:
    return ET.fromstring(c.xml.split("?>", 1)[1])


def txt(c: CteGerado, caminho: str) -> str:
    no = raiz(c).find(caminho, NS)
    assert no is not None and no.text is not None, caminho
    return no.text


def digitos(texto: str | None) -> str:
    return re.sub(r"\D", "", texto or "")


# --------------------------------------------------------------- chaves


@pytest.mark.parametrize(
    ("digitos_", "dv"),
    [("0", 0), ("12", 4), ("6", 0), ("5", 1), ("7", 8), ("99", 0)],
)
def test_dv_modulo11(digitos_: str, dv: int) -> None:
    # "12": 2*2 + 1*3 = 7 -> 11-7 = 4 ; "99": 9*2 + 9*3 = 45 -> resto 1 -> DV 0
    assert dv_modulo11(digitos_) == dv


def test_chave_valida_e_adulterada() -> None:
    chave = chave_cte(
        "23", __import__("datetime").date(2026, 9, 8), "00000126000166", 848, 52269391
    )
    assert len(chave) == 44 and chave_valida(chave)
    assert chave[:2] == "23" and chave[2:6] == "2609" and chave[20:22] == "57"
    errada = chave[:-1] + str((int(chave[-1]) + 1) % 10)
    assert not chave_valida(errada) and not chave_valida(chave[:-1])


def test_chave_nfe_ficticia() -> None:
    rng = random.Random(1)
    for _ in range(50):
        chave = chave_nfe_ficticia(
            rng, "23", __import__("datetime").date(2026, 9, 8), "00000500000150"
        )
        assert chave_valida(chave) and chave[20:22] == "55"


# ------------------------------------------------------------- cobertura


def test_um_cte_por_processo_com_transportadora(mundo: Mundo, ctes: list[CteGerado]) -> None:
    com_transp = {p.id for p in mundo.processos if p.transportadora_id}
    assert {c.documento.processo_id for c in ctes} == com_transp and len(ctes) == len(com_transp)
    assert len(ctes) == 21  # 13 marítimos com trecho + 8 rodoviários


def test_xml_valido_no_xsd_exceto_assinatura(ctes: list[CteGerado]) -> None:
    for c in ctes:
        assert validar_xml(c.xml) == [], c.documento.numero
    # o único erro do schema oficial é a falta do nó Signature (XML não assinado)
    restantes = Cte.schema_validation(ctes[0].xml)
    assert restantes and all("Signature" in e for e in restantes)
    assert "Signature" not in ctes[0].xml


def test_ler_xml_ida_e_volta(ctes: list[CteGerado]) -> None:
    for c in ctes[:5]:
        lido = ler_xml(c.xml)
        assert lido.infCte.Id == f"CTe{c.chave}" and lido.infCte.versao == "4.00"
        assert lido.to_xml() == c.xml


# ----------------------------------------------------------------- conteúdo


def test_chave_e_id(ctes: list[CteGerado]) -> None:
    for c in ctes:
        assert chave_valida(c.chave) and c.documento.chave_acesso == c.chave
        assert raiz(c).find("c:infCte", NS).attrib["Id"] == f"CTe{c.chave}"  # type: ignore[union-attr]
        assert txt(c, "c:infCte/c:ide/c:cDV") == c.chave[-1]
        assert txt(c, "c:infCte/c:ide/c:nCT") == str(int(c.chave[25:34]))
        assert txt(c, "c:infCte/c:ide/c:cCT") == c.chave[35:43]


def test_ide(mundo: Mundo, ctes: list[CteGerado]) -> None:
    proc = {p.id: p for p in mundo.processos}
    codigos_cliente = {m[0]: m[2] for m in CIDADES_CLIENTE}
    for c in ctes:
        p = proc[c.documento.processo_id or uuid.UUID(int=0)]
        assert txt(c, "c:infCte/c:ide/c:cUF") in ("23", "26")
        assert txt(c, "c:infCte/c:ide/c:mod") == "57"
        assert txt(c, "c:infCte/c:ide/c:natOp") == "Prestação de serviço de transporte"
        assert txt(c, "c:infCte/c:ide/c:modal") == "01"
        assert txt(c, "c:infCte/c:ide/c:tpServ") == "0"
        assert txt(c, "c:infCte/c:ide/c:tpAmb") == "2"  # homologação
        ini = MUNICIPIO_PORTO[p.destino_locode]
        assert txt(c, "c:infCte/c:ide/c:cMunIni") == ini[0]
        assert txt(c, "c:infCte/c:ide/c:UFIni") == ini[2]
        fim = txt(c, "c:infCte/c:ide/c:cMunFim")
        assert fim in codigos_cliente and txt(c, "c:infCte/c:ide/c:UFFim") == codigos_cliente[fim]
        cfop = txt(c, "c:infCte/c:ide/c:CFOP")
        assert cfop == ("5353" if ini[2] == codigos_cliente[fim] else "6353")
        assert txt(c, "c:infCte/c:ide/c:cUF") == c.chave[:2]


def test_municipios_com_codigos_ibge_reais() -> None:
    reais = {"2304400", "2307650", "2303709", "2611606", "2312403", "2607752", "3548500"}
    usados = {m[0] for m in MUNICIPIO_PORTO.values()} | {m[0] for m in CIDADES_CLIENTE}
    assert usados == reais


def test_partes(mundo: Mundo, ctes: list[CteGerado]) -> None:
    forn = {f.id: f for f in mundo.fornecedores}
    cli = {c.id: c for c in mundo.clientes}
    proc = {p.id: p for p in mundo.processos}
    for c in ctes:
        transp = forn[c.documento.fornecedor_id]
        cliente = cli[proc[c.documento.processo_id or uuid.UUID(int=0)].cliente_id]
        assert txt(c, "c:infCte/c:emit/c:CNPJ") == digitos(transp.cnpj_ficticio)
        assert txt(c, "c:infCte/c:emit/c:xNome") == transp.nome
        assert txt(c, "c:infCte/c:rem/c:CNPJ") == digitos(cliente.cnpj_ficticio)
        assert txt(c, "c:infCte/c:dest/c:CNPJ") == digitos(cliente.cnpj_ficticio)
        assert txt(c, "c:infCte/c:ide/c:toma4/c:CNPJ") == digitos(TOMADOR_PADRAO.cnpj)
        assert txt(c, "c:infCte/c:ide/c:toma4/c:xNome") == TOMADOR_PADRAO.nome
        assert txt(c, "c:infCte/c:emit/c:CNPJ") == c.chave[6:20]
        # CNPJs fictícios: raiz 00.000
        assert txt(c, "c:infCte/c:emit/c:CNPJ").startswith("00000")


def test_componentes_do_frete_e_gabarito(mundo: Mundo, ctes: list[CteGerado]) -> None:
    provs = {p.id: p for p in mundo.provisoes}
    for c in ctes:
        comps = [
            (
                n.findtext("c:xNome", namespaces=NS),
                Decimal(n.findtext("c:vComp", namespaces=NS) or "x"),
            )
            for n in raiz(c).findall("c:infCte/c:vPrest/c:Comp", NS)
        ]
        nomes = [n for n, _ in comps]
        assert "FRETE PESO" in nomes and set(nomes) <= set(COMPONENTES.values())
        total = sum((v for _, v in comps), Decimal(0))
        assert Decimal(txt(c, "c:infCte/c:vPrest/c:vTPrest")) == total == c.documento.total
        assert Decimal(txt(c, "c:infCte/c:vPrest/c:vRec")) == total
        # cada componente é uma linha do gabarito, ligada à provisão certa
        assert [(linha.descricao, linha.valor) for linha in c.documento.linhas] == comps
        for linha in c.documento.linhas:
            p = provs[linha.provisao_id or uuid.UUID(int=0)]
            assert COMPONENTES[p.codigo_custo] == linha.descricao
            assert (linha.codigo_custo, linha.processo_id) == (p.codigo_custo, p.processo_id)
            assert abs(linha.valor - p.valor) <= Decimal("0.50")
            assert linha.moeda == "BRL"


def test_documentos_nfe_e_modal(ctes: list[CteGerado]) -> None:
    for c in ctes:
        chaves = [
            n.text or ""
            for n in raiz(c).findall("c:infCte/c:infCTeNorm/c:infDoc/c:infNFe/c:chave", NS)
        ]
        assert 1 <= len(chaves) <= 3 and all(chave_valida(k) for k in chaves)
        rntrc = raiz(c).find("c:infCte/c:infCTeNorm/c:infModal/c:rodo/c:RNTRC", NS)
        assert rntrc is not None and re.fullmatch(r"\d{8}", rntrc.text or "")


def test_xobs_com_a_referencia_do_processo(mundo: Mundo, ctes: list[CteGerado]) -> None:
    proc = {p.id: p for p in mundo.processos}
    for c in ctes:
        obs = txt(c, "c:infCte/c:compl/c:xObs")
        m = re.fullmatch(r"REF: (\S+(?: \d+)?) / CNTR: (.+)", obs)
        assert m, obs
        p = proc[c.documento.processo_id or uuid.UUID(int=0)]
        valores = {r.valor for r in p.referencias}
        assert m.group(1) in valores
        containers = m.group(2).split(", ")
        assert containers == [r.valor for r in p.referencias if r.tipo == "conteiner"]
        assert [r.valor for r in c.documento.referencias] == [m.group(1), *containers]
        # preferência: BL house; senão referência do cliente
        tem_hbl = any(r.tipo == "bl_house" for r in p.referencias)
        assert m.group(1).startswith("HBL-") == tem_hbl


# ---------------------------------------------------------------- documento


def test_documento(mundo: Mundo, ctes: list[CteGerado]) -> None:
    proc = {p.id: p for p in mundo.processos}
    for c in ctes:
        d = c.documento
        assert (d.tipo, d.formato, d.moeda) == ("cte", "xml", "BRL")
        assert d.arquivo == f"documentos/{d.id}.xml"
        assert re.fullmatch(r"1-\d{6}", d.numero)
        eta = proc[d.processo_id or uuid.UUID(int=0)].eta
        assert eta <= d.emissao <= eta + timedelta(days=10)
        assert txt(c, "c:infCte/c:ide/c:dhEmi").startswith(d.emissao.isoformat())
        assert (d.vencimento - d.emissao).days in (15, 30) if d.vencimento else False
    assert len({c.documento.id for c in ctes}) == len(ctes)


def test_numeracao_cresce_por_transportadora(ctes: list[CteGerado]) -> None:
    por_transp: dict[str, list[CteGerado]] = {}
    for c in ctes:
        por_transp.setdefault(c.documento.fornecedor_id, []).append(c)
    for lista in por_transp.values():
        numeros = [int(c.documento.numero.split("-")[1]) for c in lista]
        assert len(set(numeros)) == len(numeros)
        ordenados = sorted(lista, key=lambda c: int(c.documento.numero.split("-")[1]))
        emissoes = [c.documento.emissao for c in ordenados]
        assert emissoes == sorted(emissoes)


def test_determinismo(mundo: Mundo) -> None:
    a = gerar_ctes(random.Random(5), mundo)
    assert [c.xml for c in a] == [c.xml for c in gerar_ctes(random.Random(5), mundo)]
    assert [c.xml for c in a] != [c.xml for c in gerar_ctes(random.Random(6), mundo)]


def test_gravar_xml(ctes: list[CteGerado], tmp_path: Path) -> None:
    caminho = gravar_xml(ctes[0], tmp_path)
    assert caminho == tmp_path / (ctes[0].documento.arquivo or "")
    texto = caminho.read_text(encoding="utf-8")
    assert texto.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert "Prestação de serviço de transporte" in texto
    assert ler_xml(texto).infCte.Id == f"CTe{ctes[0].chave}"
    with pytest.raises(ValueError, match="sem `arquivo`"):
        gravar_xml(
            CteGerado(ctes[0].documento.model_copy(update={"arquivo": None}), "<x/>", "0"), tmp_path
        )


# -------------------------------------------------------------------- DACTE


def test_dacte_gera_pdf_com_a_chave_e_os_componentes(ctes: list[CteGerado], tmp_path: Path) -> None:
    c = ctes[0]
    xml = gravar_xml(c, tmp_path)
    pdf = gerar_dacte(xml, tmp_path / "documentos" / f"{c.documento.id}_dacte.pdf")
    assert pdf.read_bytes().startswith(b"%PDF")
    with pymupdf.open(pdf) as doc:
        assert doc.page_count >= 1
        texto = doc[0].get_text()
    assert "SEM VALOR FISCAL" in texto  # homologação e sem protocolo
    assert c.chave in texto.replace(" ", "")
    assert "FRETE PESO" in texto


def test_dacte_e_reproduzivel(ctes: list[CteGerado], tmp_path: Path) -> None:
    xml = gravar_xml(ctes[0], tmp_path)
    a = gerar_dacte(xml, tmp_path / "a.pdf")
    b = gerar_dacte(xml, tmp_path / "b.pdf")
    assert a.read_bytes() == b.read_bytes()


def test_modulo_expoe_a_api_da_nfelib() -> None:
    assert "nfelib.cte.bindings.v4_0.cte_v4_00" in (cte.__doc__ or "")
    assert "NÃO É ASSINADO" in (cte.__doc__ or "")


def test_classificador_de_xml_do_core_reconhece_o_cte_gerado(ctes: list[CteGerado]) -> None:
    from confere_core.ingest.classificar_xml import classificar_xml

    for c in ctes:
        r = classificar_xml(c.xml.encode("utf-8"))
        assert (r.tipo, r.confianca, r.metodo) == ("cte", 1.0, "regra")
        assert r.fornecedor_provavel == c.documento.emitente.nome
