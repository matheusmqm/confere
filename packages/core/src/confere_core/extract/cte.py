"""Extração de CT-e 4.00 (XML) com a nfelib, sem LLM (CF-49).

Mesmos bindings usados pelo gerador (`confere_synth/cte.py`):

    from nfelib.cte.bindings.v4_0.cte_v4_00 import Cte                 # raiz <CTe>
    from nfelib.cte.bindings.v4_0.proc_cte_v4_00 import CteProc        # raiz <cteProc> (com protocolo)

O XML passa antes pelo parser seguro (`defusedxml`, sem DTD/entidades): só depois vai ao xsdata.
Mapeamento: cada `vPrest/Comp` vira uma linha (na ordem do XML); sem `Comp`, uma linha "FRETE"
com `vTPrest`. As NF-e de `infDoc` vão para `referencias.outras`; o `compl/xObs`
("REF: ... / CNTR: ...") vira BL ou referência do cliente e contêineres validados (ISO 6346).
"""

import re
from datetime import date
from decimal import Decimal
from typing import Any

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from nfelib.cte.bindings.v4_0.cte_v4_00 import Cte
from nfelib.cte.bindings.v4_0.proc_cte_v4_00 import CteProc

from confere_core.domain import CabecalhoExtraido, FaturaExtraida, LinhaExtraida, Referencias
from confere_core.validators import iso6346

_REF = re.compile(r"REF:\s*([^/]*?)\s*(?:/|$)", re.IGNORECASE)
_CNTR = re.compile(r"CNTR:\s*(.*)$", re.IGNORECASE)
_BL_MASTER = re.compile(r"^[A-Z]{3,4}\d{9}$")


class CteInvalido(ValueError):
    """O XML não é um CT-e 4.00 legível (inseguro, malformado ou sem campos obrigatórios)."""


def _carregar(xml: bytes) -> Any:
    """Devolve o `Tcte` do XML (`<CTe>` ou `<cteProc>`), depois do parser seguro."""
    try:
        raiz = SafeET.fromstring(xml, forbid_dtd=True)
    except DefusedXmlException as erro:
        raise CteInvalido("XML inseguro (DTD ou entidades)") from erro
    except Exception as erro:
        raise CteInvalido(f"XML malformado: {erro}") from erro
    nome = raiz.tag.rsplit("}", 1)[-1]
    texto = xml.decode("utf-8-sig")
    try:
        if nome == "cteProc":
            tcte = CteProc.from_xml(texto).CTe
        elif nome == "CTe":
            tcte = Cte.from_xml(texto)
        else:
            raise CteInvalido(f"raiz inesperada: {nome}")
    except CteInvalido:
        raise
    except Exception as erro:
        raise CteInvalido(f"não é um CT-e 4.00: {erro}") from erro
    if tcte is None or tcte.infCte is None:
        raise CteInvalido("CT-e sem infCte")
    return tcte


def _referencias(inf: Any, avisos: list[str]) -> Referencias:
    outras: list[str] = []
    infdoc = getattr(inf.infCTeNorm, "infDoc", None) if inf.infCTeNorm else None
    for nfe in (infdoc.infNFe if infdoc else []) or []:
        if nfe.chave:
            outras.append(nfe.chave)

    bls: list[str] = []
    ref_cliente: list[str] = []
    conteineres: list[str] = []
    obs = (inf.compl.xObs if inf.compl and inf.compl.xObs else "") or ""
    achou_ref = _REF.search(obs)
    if achou_ref:
        ref = achou_ref.group(1).strip()
        if ref and ref != "-":
            eh_bl = ref.upper().startswith("HBL-") or _BL_MASTER.match(ref.upper())
            (bls if eh_bl else ref_cliente).append(ref)
    achou_cntr = _CNTR.search(obs)
    if achou_cntr:
        for candidato in re.split(r"[,;/\s]+", achou_cntr.group(1).strip()):
            if not candidato or candidato == "-":
                continue
            numero = iso6346.normalizar(candidato)
            if iso6346.valido(numero):
                if numero not in conteineres:
                    conteineres.append(numero)
            else:
                outras.append(candidato)
                avisos.append(f"conteiner_invalido: {candidato}")
    return Referencias(bls=bls, conteineres=conteineres, ref_cliente=ref_cliente, outras=outras)


def extrair_cte(xml: bytes) -> FaturaExtraida:
    """CT-e em XML → `FaturaExtraida` (origem `cte_xml`, confianças 1,0, sem bbox)."""
    inf = _carregar(xml).infCte
    if inf.emit is None or inf.ide is None or inf.vPrest is None:
        raise CteInvalido("CT-e sem emit, ide ou vPrest")

    avisos: list[str] = []
    try:
        total = Decimal(str(inf.vPrest.vTPrest))
        emissao = date.fromisoformat(str(inf.ide.dhEmi)[:10])
    except Exception as erro:
        raise CteInvalido(f"vTPrest ou dhEmi inválido: {erro}") from erro
    referencias = _referencias(inf, avisos)

    componentes = [(c.xNome, Decimal(str(c.vComp))) for c in (inf.vPrest.comp or [])]
    if componentes:
        linhas = [
            LinhaExtraida(
                ordem=i,
                descricao=str(nome),
                quantidade=None,
                valor=valor,
                moeda="BRL",
                confianca=1.0,
            )
            for i, (nome, valor) in enumerate(componentes, start=1)
        ]
        if sum((v for _, v in componentes), Decimal(0)) != total:
            avisos.append("soma_componentes_diverge")
    else:
        linhas = [LinhaExtraida(ordem=1, descricao="FRETE", valor=total, moeda="BRL")]

    cabecalho = CabecalhoExtraido(
        fornecedor_nome=str(inf.emit.xNome),
        fornecedor_documento=inf.emit.CNPJ or inf.emit.CPF,
        numero_documento=f"{inf.ide.nCT}/{inf.ide.serie}",
        data_emissao=emissao,
        data_vencimento=None,
        moeda="BRL",
        total=total,
        referencias=referencias,
        bbox_total=None,
    )
    return FaturaExtraida(cabecalho=cabecalho, linhas=linhas, origem="cte_xml", avisos=avisos)
