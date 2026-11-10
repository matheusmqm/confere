"""Classificação de arquivos XML por namespace (CF-43), com parser seguro.

Usa `defusedxml`: DTD, entidades e recursos externos são recusados, o que barra XXE e
"billion laughs". XML recusado ou malformado vira `tipo="outro"` com `motivo` explicando; o
conteúdo do arquivo nunca é executado nem interpretado como instrução.
"""

import re
from xml.etree.ElementTree import Element, ParseError

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException

from confere_core.domain import ClassificacaoDocumento

NS_CTE = "http://www.portalfiscal.inf.br/cte"
NS_NFE = "http://www.portalfiscal.inf.br/nfe"


def _separar(tag: str) -> tuple[str, str]:
    """`{namespace}nome` → (namespace, nome)."""
    m = re.fullmatch(r"\{(.*)\}(.*)", tag)
    return (m.group(1), m.group(2)) if m else ("", tag)


def _namespace_do_documento(raiz: Element, interno: str) -> str:
    """Namespace da raiz; se for estranho, o do primeiro nó `interno` (ex. infCte)."""
    ns, _ = _separar(raiz.tag)
    if ns in (NS_CTE, NS_NFE):
        return ns
    for no in raiz.iter():
        ns_no, nome = _separar(no.tag)
        if nome == interno:
            return ns_no
    return ns


def _outro(motivo: str) -> ClassificacaoDocumento:
    return ClassificacaoDocumento(tipo="outro", confianca=1.0, metodo="regra", motivo=motivo)


def _emitente_do_cte(raiz: Element) -> str | None:
    for no in raiz.iter():
        if _separar(no.tag)[1] == "emit":
            for filho in no:
                if _separar(filho.tag)[1] == "xNome" and filho.text:
                    return filho.text.strip()
    return None


def classificar_xml(conteudo: bytes) -> ClassificacaoDocumento:
    """CT-e (namespace `.../cte`) → `cte`; NF-e → `outro` (nfe_nao_suportada); o resto → `outro`."""
    try:
        raiz = SafeET.fromstring(conteudo, forbid_dtd=True)
    except DefusedXmlException:
        return _outro("xml_inseguro")  # DTD/entidades/recursos externos
    except (ParseError, ValueError):
        return _outro("xml_invalido")

    ns = _namespace_do_documento(raiz, "infCte")
    if ns == NS_CTE:
        return ClassificacaoDocumento(
            tipo="cte",
            confianca=1.0,
            metodo="regra",
            fornecedor_provavel=_emitente_do_cte(raiz),
        )
    if ns == NS_NFE or _namespace_do_documento(raiz, "infNFe") == NS_NFE:
        return _outro("nfe_nao_suportada")
    return _outro("xml_desconhecido")
