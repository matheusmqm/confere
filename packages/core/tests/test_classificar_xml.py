"""classificar_xml: namespace, motivos e defesa contra XXE e billion laughs."""

import pytest
from pydantic import ValidationError

from confere_core.domain import ClassificacaoDocumento, CortePagina
from confere_core.ingest.classificar_xml import classificar_xml

CTE = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<CTe xmlns="http://www.portalfiscal.inf.br/cte"><infCte versao="4.00" Id="CTe1">'
    "<emit><CNPJ>00000126000166</CNPJ><xNome>Transportadora Mandacaru Ltda.</xNome></emit>"
    "</infCte></CTe>"
)
CTE_PROC = (
    '<cteProc xmlns="http://www.portalfiscal.inf.br/cte" versao="4.00">'
    "<CTe><infCte><emit><xNome>Rodoviário Ventania</xNome></emit></infCte></CTe></cteProc>"
)
NFE = '<NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe versao="4.00"/></NFe>'
OUTRO = '<fatura xmlns="http://exemplo.example/x"><total>10</total></fatura>'
SEM_NS = "<fatura><total>10</total></fatura>"


def test_cte_por_namespace_da_raiz() -> None:
    c = classificar_xml(CTE.encode("utf-8"))
    assert (c.tipo, c.confianca, c.metodo, c.motivo) == ("cte", 1.0, "regra", None)
    assert c.fornecedor_provavel == "Transportadora Mandacaru Ltda."
    assert c.paginas == []


def test_cte_processado() -> None:
    c = classificar_xml(CTE_PROC.encode("utf-8"))
    assert c.tipo == "cte" and c.fornecedor_provavel == "Rodoviário Ventania"


def test_cte_com_raiz_de_outro_namespace_e_infcte_no_namespace_certo() -> None:
    xml = (
        '<envelope xmlns="http://exemplo.example/env">'
        '<infCte xmlns="http://www.portalfiscal.inf.br/cte"/></envelope>'
    )
    assert classificar_xml(xml.encode()).tipo == "cte"


def test_cte_com_bom_utf8() -> None:
    assert classificar_xml(b"\xef\xbb\xbf" + CTE.encode("utf-8")).tipo == "cte"


def test_nfe_nao_suportada() -> None:
    c = classificar_xml(NFE.encode())
    assert (c.tipo, c.motivo, c.confianca, c.metodo) == ("outro", "nfe_nao_suportada", 1.0, "regra")


@pytest.mark.parametrize("xml", [OUTRO, SEM_NS, "<a/>"])
def test_xml_desconhecido(xml: str) -> None:
    c = classificar_xml(xml.encode())
    assert (c.tipo, c.motivo) == ("outro", "xml_desconhecido")


@pytest.mark.parametrize("conteudo", [b"", b"nao e xml", b"<a><b></a>", b"\x00\x01\x02", b"<a"])
def test_xml_invalido(conteudo: bytes) -> None:
    assert classificar_xml(conteudo).motivo == "xml_invalido"


XXE = b"""<?xml version="1.0"?>
<!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<CTe xmlns="http://www.portalfiscal.inf.br/cte"><infCte>&x;</infCte></CTe>"""

XXE_HTTP = b"""<?xml version="1.0"?>
<!DOCTYPE d [<!ENTITY x SYSTEM "http://127.0.0.1:9/segredo">]>
<d>&x;</d>"""

BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [
 <!ENTITY lol "lol">
 <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
 <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">
 <!ENTITY lol4 "&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;&lol3;">
]>
<lolz>&lol4;</lolz>"""

SO_DTD = b"""<?xml version="1.0"?><!DOCTYPE d [<!ELEMENT d ANY>]><d/>"""


@pytest.mark.parametrize("conteudo", [XXE, XXE_HTTP, BILLION_LAUGHS, SO_DTD])
def test_entidades_e_dtd_sao_recusados(conteudo: bytes) -> None:
    c = classificar_xml(conteudo)
    assert (c.tipo, c.motivo, c.confianca) == ("outro", "xml_inseguro", 1.0)


def test_payload_xxe_com_namespace_de_cte_nao_vira_cte() -> None:
    assert classificar_xml(XXE).tipo == "outro"


# -------------------------------------------------------------------- modelos


def test_corte_de_pagina_valida_o_intervalo() -> None:
    assert CortePagina(inicio=1, fim=2, tipo="fatura").fim == 2
    assert CortePagina(inicio=3, fim=3, tipo="bl").inicio == 3
    for inicio, fim in [(0, 1), (3, 2)]:
        with pytest.raises(ValidationError):
            CortePagina(inicio=inicio, fim=fim, tipo="fatura")


def test_classificacao_valida_tipo_e_confianca() -> None:
    ok = ClassificacaoDocumento(tipo="fatura", confianca=0.8, metodo="llm")
    assert ok.paginas == [] and ok.fornecedor_provavel is None and ok.motivo is None
    for dados in (
        {"tipo": "recibo", "confianca": 0.5, "metodo": "llm"},
        {"tipo": "fatura", "confianca": 1.1, "metodo": "llm"},
        {"tipo": "fatura", "confianca": 0.5, "metodo": "humano"},
    ):
        with pytest.raises(ValidationError):
            ClassificacaoDocumento.model_validate(dados)
