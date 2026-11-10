"""Faturas sintéticas "limpas" (sem erro injetado) a partir das provisões, e sua renderização.

`gerar_documentos_limpos` cria, para cada (processo, fornecedor, moeda) com provisões, uma
fatura cujas linhas têm o gabarito (processo, provisão, código de custo). Transportadoras
ficam de fora: o documento delas é o CT-e (CF-34). Os erros entram depois (CF-36).

Decisões:
- Uma fatura por moeda: se um fornecedor tem provisões em moedas diferentes no processo
  (ex. armador cobrando frete em USD e taxa local em BRL), saem duas faturas, para o valor da
  linha continuar igual ao da provisão (sem conversão cambial).
- O extrato (estilo 6) lista linhas de faturas já emitidas pelo armador, com o número da fatura
  em cada linha: é um documento de conferência, não uma cobrança nova.
- `valor_unit` = valor / quantidade com 2 casas; por isso quantidade x valor_unit pode
  diferir do valor em até alguns centavos, como em faturas reais.
"""

import hashlib
import random
import shutil
import uuid
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Literal

from confere_core.costcode.catalogo import Catalogo
from confere_core.fx.tabela import Cotacao, TabelaPTAX
from confere_synth import cambio
from confere_synth.modelos import (
    DocumentoSintetico,
    Emitente,
    Fornecedor,
    LinhaSintetica,
    Mundo,
    Processo,
    Provisao,
    Referencia,
    TipoDocumento,
    TipoReferencia,
)
from confere_synth.render import (
    TOMADOR_PADRAO,
    ContextoRender,
    DocInfo,
    FornecedorInfo,
    LinhaRender,
    ProcessoRefs,
    data_pt,
    num_pt,
    renderizar_html,
)

PCT_LINHAS_INTEIRAS = 0.10
PCT_LINHAS_CENTAVOS = 0.05
PCT_FATURAS_COM_DOIS_PROCESSOS = 0.15
PROCESSOS_POR_EXTRATO = (4, 8)
ESTILO_EXTRATO = 6
_CENTAVO = Decimal("0.01")

# Padrão de numeração de cada fornecedor.
NUMEROS = {
    "atlantida-ocean-lines": "ATL-INV-26-{n:06d}",
    "boreal-container-line": "BCL{n:08d}",
    "tarquin-marine-lines": "TML/INV/{n:06d}",
    "consolidadora-aurora": "CMA-{n:06d}",
    "jade-river-logistics": "JRL-DN-2026-{n:05d}",
    "nordhaven-freight": "NFP-DN-26-{n:04d}",
    "terminal-mar-azul": "TMA-2026/{n:06d}",
    "terminal-cajueiro-pecem": "FS {n:07d}",
    "terminal-mare-alta-suape": "MA-{n:06d}",
    "armazens-gerais-carnauba": "NDB-{n:06d}",
    "entreposto-barlavento": "NF-DEB {n:04d}",
    "despachos-farol": "DD-2026-{n:04d}",
    "lagoa-azul-assessoria": "DEM {n:05d}-26",
}

# Endereços FICTÍCIOS (nenhum é real).
ENDERECOS = {
    "atlantida-ocean-lines": "1 Fictional Quay, Singapore 000000 (fictitious address)",
    "boreal-container-line": "Fiktivgata 3, 0000 Oslo (fictitious address)",
    "tarquin-marine-lines": "10 Imaginary Wharf, London EC0A 0AA (fictitious address)",
    "jade-river-logistics": "Room 000, Fictional Tower, Shenzhen (fictitious address)",
    "nordhaven-freight": "Fiktivstrasse 12, 00000 Hamburg (fictitious address)",
    "consolidadora-aurora": "Av. Fictícia, 321, Fortaleza/CE (endereço fictício)",
    "terminal-mar-azul": "Av. Fictícia, 500, Fortaleza/CE (endereço fictício)",
    "terminal-cajueiro-pecem": "Via Fictícia s/n, São Gonçalo do Amarante/CE (endereço fictício)",
    "terminal-mare-alta-suape": "Rod. Fictícia km 3, Ipojuca/PE (endereço fictício)",
    "armazens-gerais-carnauba": "Rod. Fictícia km 12, Maracanaú/CE (endereço fictício)",
    "entreposto-barlavento": "Av. Imaginária, 900, Recife/PE (endereço fictício)",
    "transportadora-mandacaru": "Rua Fictícia, 40, Fortaleza/CE (endereço fictício)",
    "rodoviario-ventania": "Av. Fictícia, 1200, Recife/PE (endereço fictício)",
    "despachos-farol": "Rua Fictícia, 77, sala 3, Fortaleza/CE (endereço fictício)",
    "lagoa-azul-assessoria": "Rua Imaginária, 15, Recife/PE (endereço fictício)",
}

_OBSERVACOES = {
    "armador": ["Charges are payable in the invoice currency.", ""],
    "agente_exterior": ["Please remit within the agreed terms.", ""],
    "terminal": ["Serviços prestados conforme tabela vigente.", ""],
    "armazem": ["Período de armazenagem contado da data de entrada, inclusive.", ""],
    "despachante": [
        "Os valores de reembolso correspondem a despesas pagas por conta e ordem do cliente, "
        "conforme comprovantes arquivados. Os honorários seguem a tabela contratada. "
        "Eventuais diferenças de câmbio serão regularizadas no demonstrativo seguinte. "
        "Documento fictício, gerado apenas para testes.",
    ],
}
_HONORARIOS = {"HONORARIO_DESPACHO", "EMISSAO_LI"}
_CITACOES: dict[str, list[tuple[TipoReferencia, float]]] = {
    "armador": [("bl_master", 1.0), ("conteiner", 1.0), ("ref_cliente", 0.3)],
    "agente_exterior": [
        ("bl_master", 0.8),
        ("bl_house", 0.5),
        ("ref_agente", 1.0),
        ("conteiner", 0.7),
        ("ref_cliente", 0.5),
    ],
    "terminal": [("bl_master", 1.0), ("conteiner", 1.0), ("ref_cliente", 0.5)],
    "armazem": [("bl_house", 1.0), ("bl_master", 0.7), ("conteiner", 1.0), ("ref_cliente", 0.6)],
    "despachante": [
        ("bl_master", 1.0),
        ("bl_house", 0.6),
        ("conteiner", 0.6),
        ("ref_cliente", 1.0),
    ],
}
_ROTULOS = {
    "bl_master": "B/L",
    "bl_house": "HBL",
    "conteiner": "Ctr",
    "ref_cliente": "Ref.",
    "ref_agente": "Agent ref.",
}
_TIPO_DOCUMENTO: dict[str, TipoDocumento] = {
    "armador": "fatura",
    "agente_exterior": "nota_debito",
    "terminal": "fatura",
    "armazem": "nota_debito",
    "despachante": "fatura",
}


class _Rascunho:
    """Uma fatura ainda sem número: fornecedor, moeda e os processos que ela cobre."""

    def __init__(
        self, fornecedor: Fornecedor, moeda: str, itens: list[tuple[Processo, list[Provisao]]]
    ):
        self.fornecedor = fornecedor
        self.moeda = moeda
        self.itens = itens


def _conteineres(proc: Processo) -> list[str]:
    return [r.valor for r in proc.referencias if r.tipo == "conteiner"]


def _primeiro_conteiner(proc: Processo) -> str | None:
    conteineres = _conteineres(proc)
    return conteineres[0] if conteineres else None


def _bl(proc: Processo) -> str | None:
    for tipo in ("bl_master", "bl_house"):
        for r in proc.referencias:
            if r.tipo == tipo:
                return r.valor
    return None


def _quantidade(catalogo: Catalogo, codigo: str, proc: Processo) -> int:
    unidade = catalogo.get(codigo).unidade
    if unidade == "por_conteiner":
        return max(len(_conteineres(proc)), 1)
    if unidade == "por_bl":
        return max(sum(r.tipo == "bl_house" for r in proc.referencias), 1)
    return 1  # por_processo, percentual e por_dia (os dias não ficam guardados na provisão)


def _valor_da_linha(rng: random.Random, valor: Decimal) -> Decimal:
    """85% igual à provisão, 10% arredondado para inteiro, 5% com diferença de centavos."""
    sorteio = rng.random()
    if sorteio < PCT_LINHAS_INTEIRAS:
        return max(valor.quantize(Decimal(1), ROUND_HALF_EVEN), Decimal(1)).quantize(_CENTAVO)
    if sorteio < PCT_LINHAS_INTEIRAS + PCT_LINHAS_CENTAVOS:
        delta = Decimal(rng.randint(1, 20)) / 100 * rng.choice((-1, 1))
        return max(valor + delta, _CENTAVO)
    return valor


def _linha(
    rng: random.Random,
    prov: Provisao,
    proc: Processo,
    forn: Fornecedor,
    catalogo: Catalogo,
    com_referencias: bool,
    taxa_cambio: Decimal | None = None,
    moeda_fatura: str | None = None,
) -> LinhaSintetica:
    codigo = prov.codigo_custo
    descricao = rng.choice(forn.nomes_taxa[codigo])
    conteineres = _conteineres(proc)
    if conteineres and rng.random() < 0.25:
        descricao += f" - {rng.choice(conteineres)}"

    valor_origem = _valor_da_linha(rng, prov.valor)
    valor = valor_origem
    if taxa_cambio is not None:  # nacional: cobra em BRL o que é previsto em moeda estrangeira
        valor = (valor_origem * taxa_cambio).quantize(_CENTAVO, ROUND_HALF_EVEN)
    quantidade = _quantidade(catalogo, codigo, proc)
    referencias: list[Referencia] = []
    if com_referencias:  # fatura de vários processos, ou estilo com contêiner por linha
        bl = _bl(proc)
        if bl:
            referencias.append(Referencia(tipo="bl_master", valor=bl))
        if conteineres:
            referencias.append(Referencia(tipo="conteiner", valor=rng.choice(conteineres)))

    periodo: tuple[date, date] | None = None
    base_cif: Decimal | None = None
    percentual: Decimal | None = None
    secao: Literal["reembolso", "honorario"] | None = None
    if codigo == "ARMAZENAGEM":
        entrada = proc.eta + timedelta(days=rng.randint(0, 3))
        periodo = (entrada, entrada + timedelta(days=10))
        base_cif = (valor / Decimal("0.0035")).quantize(_CENTAVO)
        percentual = Decimal("0.35")
    if forn.tipo == "despachante":
        secao = "honorario" if codigo in _HONORARIOS else "reembolso"

    return LinhaSintetica(
        descricao=descricao,
        quantidade=Decimal(quantidade),
        valor_unit=(valor / quantidade).quantize(_CENTAVO, ROUND_HALF_EVEN),
        valor=valor,
        moeda=moeda_fatura or prov.moeda,
        codigo_custo=codigo,
        processo_id=proc.id,
        provisao_id=prov.id,
        referencias=referencias,
        moeda_origem=prov.moeda if taxa_cambio is not None else None,
        valor_origem=valor_origem if taxa_cambio is not None else None,
        taxa_cambio=taxa_cambio,
        codigo_fornecedor=f"SV-{catalogo.codigos().index(codigo) + 1:03d}",
        secao=secao,
        periodo=periodo,
        base_cif=base_cif,
        percentual=percentual,
    )


def _citacoes(
    rng: random.Random, forn: Fornecedor, proc: Processo
) -> tuple[list[Referencia], str | None, str | None]:
    """O que este tipo de fornecedor costuma citar do processo."""
    refs: list[Referencia] = []
    for tipo, prob in _CITACOES[forn.tipo]:
        citar = rng.random() < prob
        if citar:
            refs += [r for r in proc.referencias if r.tipo == tipo]
    cita_navio = forn.tipo in ("armador", "terminal") or (
        forn.tipo == "agente_exterior" and rng.random() < 0.5
    )
    return refs, (proc.navio if cita_navio else None), (proc.viagem if cita_navio else None)


def _agrupar(rng: random.Random, mundo: Mundo) -> list[_Rascunho]:
    por_forn = {f.id: f for f in mundo.fornecedores}
    por_proc = {p.id: p for p in mundo.processos}
    grupos: dict[tuple[str, str], dict[uuid.UUID, list[Provisao]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for prov in mundo.provisoes:
        if por_forn[prov.fornecedor_id].tipo == "transportadora":
            continue  # CT-e na CF-34
        # fornecedor nacional fatura sempre em BRL (converte o previsto em moeda estrangeira)
        moeda_fatura = "BRL" if por_forn[prov.fornecedor_id].pais == "BR" else prov.moeda
        grupos[(prov.fornecedor_id, moeda_fatura)][prov.processo_id].append(prov)

    rascunhos: list[_Rascunho] = []
    ordem_proc = {p.id: i for i, p in enumerate(mundo.processos)}
    for forn in mundo.fornecedores:
        for moeda in sorted({m for (f, m) in grupos if f == forn.id}):
            porproc = grupos[(forn.id, moeda)]
            itens = [
                (por_proc[pid], provs)
                for pid, provs in sorted(porproc.items(), key=lambda kv: ordem_proc[kv[0]])
            ]
            juntar = 0
            if forn.tipo in ("armador", "agente_exterior"):
                # k juntadas -> k/(n-k) das faturas cobrem 2 processos (~15%)
                juntar = round(
                    len(itens)
                    * PCT_FATURAS_COM_DOIS_PROCESSOS
                    / (1 + PCT_FATURAS_COM_DOIS_PROCESSOS)
                )
            indices = list(range(len(itens)))
            rng.shuffle(indices)
            usados = set(indices[: 2 * juntar])
            for a, b in zip(indices[: 2 * juntar : 2], indices[1 : 2 * juntar : 2], strict=True):
                rascunhos.append(_Rascunho(forn, moeda, [itens[a], itens[b]]))
            rascunhos += [
                _Rascunho(forn, moeda, [itens[i]]) for i in range(len(itens)) if i not in usados
            ]
    return rascunhos


def gerar_documentos_limpos(
    rng: random.Random, mundo: Mundo, catalogo: Catalogo, ptax: TabelaPTAX | None = None
) -> list[DocumentoSintetico]:
    """Faturas sem erro (uma por processo, fornecedor e moeda) e um extrato por armador.

    Fornecedor nacional com provisão em moeda estrangeira (o NVOCC) fatura em BRL pela PTAX de
    venda da emissão, com a linha informativa "Taxa de câmbio aplicada". Sem cotação para a
    data, a emissão é limitada à última cotação da tabela (`ptax`, padrão `data/seed42/ptax.csv`).
    """
    tabela_ptax = ptax
    por_forn = {f.id: f for f in mundo.fornecedores}
    ordem_forn = {f.id: i for i, f in enumerate(mundo.fornecedores)}
    rascunhos = _agrupar(rng, mundo)

    # emissão e numeração: o número cresce com a data de emissão, com saltos, por fornecedor
    emitidos: list[tuple[_Rascunho, date]] = []
    for r in rascunhos:
        base = min(p.eta for p, _ in r.itens)
        emissao_sorteada = base + timedelta(days=rng.randint(-5, 20))
        for moeda in {p.moeda for _, provs in r.itens for p in provs if p.moeda != r.moeda}:
            tabela_ptax = tabela_ptax or cambio.carregar_ptax_padrao()
            ultima = cambio.ultima_data(tabela_ptax, moeda)
            if ultima is None:
                raise ValueError(f"sem PTAX de {moeda}: rode infra/scripts/baixar_ptax.py")
            emissao_sorteada = min(emissao_sorteada, ultima)  # nada de cotação inventada
        emitidos.append((r, emissao_sorteada))
    emitidos.sort(key=lambda x: (ordem_forn[x[0].fornecedor.id], x[1], x[0].itens[0][0].codigo))

    contador: dict[str, int] = {}
    documentos: list[DocumentoSintetico] = []
    for r, emissao in emitidos:
        forn = r.fornecedor
        atual = contador.get(forn.id)
        contador[forn.id] = rng.randint(1200, 4800) if atual is None else atual + rng.randint(1, 35)
        numero = NUMEROS[forn.id].format(n=contador[forn.id])

        varios = len(r.itens) > 1
        linhas: list[LinhaSintetica] = []
        cotacoes: dict[str, Cotacao] = {}
        for proc, provs in r.itens:
            for prov in provs:
                taxa = None
                if prov.moeda != r.moeda:
                    assert tabela_ptax is not None
                    cot = cambio.cotacao(tabela_ptax, prov.moeda, emissao)
                    if cot is None:
                        raise ValueError(f"sem PTAX de {prov.moeda} perto de {emissao}")
                    cotacoes[prov.moeda] = cot
                    taxa = cot.venda
                linhas.append(
                    _linha(
                        rng,
                        prov,
                        proc,
                        forn,
                        catalogo,
                        com_referencias=varios or forn.tipo == "agente_exterior",
                        taxa_cambio=taxa,
                        moeda_fatura=r.moeda,
                    )
                )
        for moeda, cot in sorted(cotacoes.items()):  # uma linha informativa por moeda convertida
            linhas.append(
                LinhaSintetica(
                    descricao=(
                        f"Taxa de câmbio aplicada: {num_pt(cot.venda, 4)} "
                        f"(PTAX venda {moeda} de {data_pt(cot.data)})"
                    ),
                    valor_unit=Decimal(0),
                    valor=Decimal(0),
                    moeda=r.moeda,
                    codigo_custo="OUTROS",
                    processo_id=r.itens[0][0].id,
                    moeda_origem=moeda,
                    taxa_cambio=cot.venda,
                    informativa=True,
                )
            )
        doc_refs: list[Referencia] = []
        navio = viagem = None
        if not varios:
            doc_refs, navio, viagem = _citacoes(rng, forn, r.itens[0][0])
        doc_id = uuid.UUID(int=rng.getrandbits(128), version=4)
        documentos.append(
            DocumentoSintetico(
                id=doc_id,
                tipo=_TIPO_DOCUMENTO[forn.tipo],
                fornecedor_id=forn.id,
                emitente=_emitente(forn),
                processo_id=None if varios else r.itens[0][0].id,
                numero=numero,
                emissao=emissao,
                vencimento=emissao + timedelta(days=rng.choice((15, 30))),
                moeda=r.moeda,
                linhas=linhas,
                total=sum((linha.valor for linha in linhas), Decimal(0)),
                estilo_id=forn.estilo_id,
                referencias=doc_refs,
                navio=navio,
                viagem=viagem,
                observacoes=rng.choice(_OBSERVACOES[forn.tipo]),
                arquivo=f"documentos/{doc_id}.pdf",
            )
        )
    documentos += _extratos(rng, mundo, documentos, por_forn)
    return documentos


def _emitente(forn: Fornecedor) -> Emitente:
    return Emitente(
        nome=forn.nome,
        endereco=ENDERECOS[forn.id],
        cnpj=forn.cnpj_ficticio,
        email=f"faturamento@{forn.dominio_email}",
    )


def linha_para_extrato(
    linha: LinhaSintetica, numero_fatura: str, por_proc: dict[uuid.UUID, Processo]
) -> LinhaSintetica:
    """Cópia da linha de uma fatura para o extrato, com fatura, BL e contêiner do processo."""
    proc = por_proc[linha.processo_id] if linha.processo_id else None
    return linha.model_copy(
        update={
            "fatura_no": numero_fatura,
            "bl": _bl(proc) if proc else None,
            "container": _primeiro_conteiner(proc) if proc else None,
        }
    )


def _extratos(
    rng: random.Random,
    mundo: Mundo,
    documentos: list[DocumentoSintetico],
    por_forn: dict[str, Fornecedor],
) -> list[DocumentoSintetico]:
    """Um extrato (estilo 6) por armador, juntando 4 a 8 processos já faturados em sua moeda."""
    por_proc = {p.id: p for p in mundo.processos}
    extratos: list[DocumentoSintetico] = []
    for forn in mundo.fornecedores:
        if forn.tipo != "armador" or forn.pais == "BR":
            continue  # extrato em inglês: só armadores estrangeiros
        meus = [
            d for d in documentos if d.fornecedor_id == forn.id and d.moeda == forn.moeda_padrao
        ]
        if not meus:
            continue
        alvo = rng.randint(*PROCESSOS_POR_EXTRATO)
        escolhidos: list[DocumentoSintetico] = []
        processos: set[uuid.UUID] = set()
        for d in rng.sample(meus, len(meus)):
            ps = {linha.processo_id for linha in d.linhas if linha.processo_id}
            if len(processos | ps) > PROCESSOS_POR_EXTRATO[1]:
                continue
            escolhidos.append(d)
            processos |= ps
            if len(processos) >= alvo:
                break
        escolhidos.sort(key=lambda d: (d.emissao, d.numero))
        linhas = [
            linha_para_extrato(linha, d.numero, por_proc)
            for d in escolhidos
            for linha in d.linhas
            if not linha.informativa
        ]
        emissao = max(d.emissao for d in escolhidos) + timedelta(days=rng.randint(1, 5))
        doc_id = uuid.UUID(int=rng.getrandbits(128), version=4)
        extratos.append(
            DocumentoSintetico(
                id=doc_id,
                tipo="extrato",
                fornecedor_id=forn.id,
                emitente=_emitente(por_forn[forn.id]),
                processo_id=None,
                numero=f"STM-{forn.id[:3].upper()}-{emissao:%Y%m}",
                emissao=emissao,
                vencimento=None,
                moeda=forn.moeda_padrao,
                linhas=linhas,
                total=sum((linha.valor for linha in linhas), Decimal(0)),
                estilo_id=ESTILO_EXTRATO,
                observacoes="Statement of open items.",
                arquivo=f"documentos/{doc_id}.pdf",
            )
        )
    return extratos


# ---------------------------------------------------------------- renderização


def _primeira(refs: list[Referencia], tipo: str) -> str | None:
    return next((r.valor for r in refs if r.tipo == tipo), None)


def _texto_cambio(linha: LinhaSintetica) -> str | None:
    """Texto "USD 1.800,00 x taxa 5,6120 = R$ 10.101,60" das linhas convertidas."""
    if linha.informativa or linha.moeda_origem is None:
        return None
    assert linha.valor_origem is not None and linha.taxa_cambio is not None
    return (
        f"{linha.moeda_origem} {num_pt(linha.valor_origem)} × taxa "  # noqa: RUF001
        f"{num_pt(linha.taxa_cambio, 4)} = R$ {num_pt(linha.valor)}"
    )


def contexto_do_documento(doc: DocumentoSintetico) -> ContextoRender:
    """Tudo que os templates precisam, só a partir do documento."""
    return ContextoRender(
        doc=DocInfo(
            numero=doc.numero,
            emissao=doc.emissao,
            vencimento=doc.vencimento,
            moeda=doc.moeda,
            total=doc.total,
            observacoes=doc.observacoes,
        ),
        fornecedor=FornecedorInfo(
            nome=doc.emitente.nome,
            endereco=doc.emitente.endereco,
            cnpj=doc.emitente.cnpj,
            email=doc.emitente.email,
        ),
        tomador=TOMADOR_PADRAO,
        processo_refs=ProcessoRefs(
            bl_master=_primeira(doc.referencias, "bl_master"),
            bl_house=[r.valor for r in doc.referencias if r.tipo == "bl_house"],
            conteineres=[r.valor for r in doc.referencias if r.tipo == "conteiner"],
            navio=doc.navio,
            viagem=doc.viagem,
            ref_cliente=_primeira(doc.referencias, "ref_cliente"),
            ref_agente=_primeira(doc.referencias, "ref_agente"),
        ),
        linhas=[
            LinhaRender(
                descricao=linha.descricao,
                qtd=linha.quantidade,
                valor_unit=linha.valor_unit,
                valor=linha.valor,
                moeda=linha.moeda,
                codigo=linha.codigo_fornecedor,
                refs_linha=[f"{_ROTULOS[r.tipo]} {r.valor}" for r in linha.referencias],
                secao=linha.secao,
                periodo=linha.periodo,
                base_cif=linha.base_cif,
                percentual=linha.percentual,
                fatura_no=linha.fatura_no,
                bl=linha.bl,
                container=linha.container,
                cambio=_texto_cambio(linha),
            )
            for linha in doc.linhas
        ],
    )


class WeasyPrintIndisponivelError(RuntimeError):
    """O WeasyPrint não carregou (normalmente faltam as bibliotecas do sistema, ex. Pango)."""


def _escrever_pdf(html: str, destino: Path) -> None:
    """HTML → PDF com WeasyPrint. O `/ID` vem do próprio HTML, para o PDF ser reproduzível."""
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as erro:
        raise WeasyPrintIndisponivelError(str(erro)) from erro

    destino.parent.mkdir(parents=True, exist_ok=True)
    identificador = hashlib.sha256(html.encode("utf-8")).digest()[:16]
    HTML(string=html).write_pdf(destino, pdf_identifier=identificador)


def sha256_de(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def renderizar(doc: DocumentoSintetico, saida_dir: str | Path) -> Path:
    """Renderiza o documento com o template do seu `estilo_id` e grava o PDF.

    Devolve o caminho (`saida_dir / doc.arquivo`); o SHA-256 sai de `sha256_de(caminho)`.
    """
    if doc.arquivo is None:
        raise ValueError(f"documento {doc.numero} sem `arquivo`")
    destino = Path(saida_dir) / doc.arquivo
    if doc.duplicata_identica:  # reenvio idêntico: mesmo conteúdo, nome de arquivo diferente
        original = Path(saida_dir) / f"documentos/{doc.duplicata_de}.pdf"
        if not original.exists():
            raise FileNotFoundError(f"{original} não existe: renderize o original antes da cópia")
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, destino)
        return destino
    _escrever_pdf(renderizar_html(doc.estilo_id, contexto_do_documento(doc)), destino)
    return destino
