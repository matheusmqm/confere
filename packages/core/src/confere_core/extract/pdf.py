"""Extração de faturas em PDF/imagem com Gemini (CF-50) e dupla extração condicional (CF-52).

`extrair_pdf` manda ao LLM as imagens de todas as páginas (até 6) e o texto extraído, recebe
`FaturaExtraidaLLM`, converte (`para_dominio`), refina as caixas (bbox) com as coordenadas reais
da camada de texto e atribui a confiança inicial de cada linha. `extrair_com_verificacao` só
chama o LLM uma segunda vez (prompt alternativo) se a validação da primeira extração falhar.

Nada aqui decide aprovação: o texto do documento é dado e a saída é presa a um schema.
"""

import re
from decimal import Decimal

from pydantic import BaseModel
from rapidfuzz import fuzz

from confere_core.domain import BBox, CabecalhoExtraido, FaturaExtraida, LinhaExtraida
from confere_core.extract.validacoes import ContextoValidacao, ResultadoValidacao, validar
from confere_core.ingest.render import BlocoTexto, PaginaRenderizada
from confere_core.llm.client import LLMClient
from confere_core.llm.schema_gemini import FaturaExtraidaLLM

PROMPT_ID = "extrair_fatura"
PROMPT_ALT_ID = "extrair_fatura_alt"
PROMPT_VERSAO = 1
MAX_PAGINAS = 6
LIMIAR_DESCRICAO = 80  # partial_ratio mínimo entre a descrição e o texto da linha
CONFIANCA_ACHADO = 1.0
CONFIANCA_SEM_TEXTO = 0.8
CONFIANCA_NAO_ACHADO = 0.6
CONFIANCA_DIVERGENTE = 0.3
_CENTAVO = Decimal("0.01")


# ----------------------------------------------------------------------- entrada


def montar_entrada(
    paginas: list[PaginaRenderizada], dica_fornecedor: str | None
) -> tuple[str, list[bytes], list[PaginaRenderizada], list[str]]:
    """(texto, PNGs, páginas enviadas, avisos). Acima de 6 páginas, só as 6 primeiras vão."""
    enviadas = paginas[:MAX_PAGINAS]
    avisos: list[str] = []
    if len(paginas) > MAX_PAGINAS:
        avisos.append(
            f"paginas_alem_do_limite: {len(paginas) - MAX_PAGINAS} página(s) não enviadas ao LLM"
        )
    partes = [f"Documento com {len(paginas)} página(s); enviadas: {len(enviadas)}."]
    if dica_fornecedor:
        partes.append(f"Dica do fornecedor (pode estar errada): {dica_fornecedor}")
    for p in enviadas:
        if p.tem_texto:
            partes.append(
                f"TEXTO EXTRAÍDO DA PÁGINA {p.numero}:\n<<<INICIO>>>\n{p.texto.strip()}\n<<<FIM>>>"
            )
    return "\n\n".join(partes), [p.png for p in enviadas], enviadas, avisos


# ------------------------------------------------------------- valor no texto da página


def variantes_do_valor(valor: Decimal) -> list[str]:
    """Formas impressas do valor: 1.495,20 e 1,495.20, com e sem separador de milhar."""
    absoluto = abs(valor).quantize(_CENTAVO)
    inteiro, decimais = f"{absoluto:.2f}".split(".")
    com_milhar = f"{int(inteiro):,}"
    formas = [
        com_milhar.replace(",", ".") + "," + decimais,
        com_milhar + "." + decimais,
        inteiro + "," + decimais,
        inteiro + "." + decimais,
    ]
    return list(dict.fromkeys(formas))


def achar_valor(texto: str, valor: Decimal) -> bool:
    """O valor aparece no texto como número inteiro (sem ser pedaço de outro número)?"""
    return any(
        re.search(rf"(?<![\d.,]){re.escape(v)}(?!\d)", texto) for v in variantes_do_valor(valor)
    )


# ------------------------------------------------------------------ refino de bbox


def _normalizar(caixa: tuple[float, float, float, float], pagina: PaginaRenderizada) -> BBox:
    def lim(x: float) -> float:
        return min(max(x, 0.0), 1.0)

    x0, y0, x1, y1 = caixa
    return BBox(
        pagina=pagina.numero,
        x0=lim(x0 / pagina.largura_pt),
        y0=lim(y0 / pagina.altura_pt),
        x1=lim(x1 / pagina.largura_pt),
        y1=lim(y1 / pagina.altura_pt),
    )


def _linha_de_blocos(candidato: BlocoTexto, blocos: list[BlocoTexto]) -> list[BlocoTexto]:
    """Blocos que estão na mesma faixa vertical (a mesma linha da tabela) do candidato."""
    _, y0, _, y1 = candidato.bbox
    centro = (y0 + y1) / 2
    folga = 0.3 * (y1 - y0)
    mesma = [b for b in blocos if b.bbox[1] - folga <= centro <= b.bbox[3] + folga]
    return sorted(mesma, key=lambda b: b.bbox[0])


def _refinar_bbox(
    linha: LinhaExtraida, paginas: list[PaginaRenderizada], usados: set[tuple[int, int]]
) -> BBox | None:
    """Bbox real da linha: bloco que contém o valor e cuja linha de tabela contém a descrição."""
    alvo_pagina = linha.bbox.pagina if linha.bbox else None
    melhor: tuple[float, float, PaginaRenderizada, list[BlocoTexto], int] | None = None
    for pagina in paginas:
        if alvo_pagina is not None and pagina.numero != alvo_pagina:
            continue
        for i, bloco in enumerate(pagina.blocos):
            if (pagina.numero, i) in usados or not achar_valor(bloco.texto, linha.valor):
                continue
            faixa = _linha_de_blocos(bloco, pagina.blocos)
            nota = fuzz.partial_ratio(
                linha.descricao.lower(), " ".join(b.texto for b in faixa).lower()
            )
            if nota < LIMIAR_DESCRICAO:
                continue
            distancia = 0.0
            if linha.bbox is not None:  # desempate: o mais perto do que o LLM apontou
                centro_llm = (linha.bbox.y0 + linha.bbox.y1) / 2
                centro_real = (bloco.bbox[1] + bloco.bbox[3]) / 2 / pagina.altura_pt
                distancia = abs(centro_llm - centro_real)
            if melhor is None or (nota, -distancia) > (melhor[0], -melhor[1]):
                melhor = (nota, distancia, pagina, faixa, i)
    if melhor is None:
        return None
    _, _, pagina, faixa, i = melhor
    usados.add((pagina.numero, i))
    return _normalizar(
        (
            min(b.bbox[0] for b in faixa),
            min(b.bbox[1] for b in faixa),
            max(b.bbox[2] for b in faixa),
            max(b.bbox[3] for b in faixa),
        ),
        pagina,
    )


def refinar_e_pontuar(fatura: FaturaExtraida, paginas: list[PaginaRenderizada]) -> FaturaExtraida:
    """Substitui bbox pela real (quando há texto) e fixa a confiança inicial de cada linha."""
    usados: set[tuple[int, int]] = set()
    linhas: list[LinhaExtraida] = []
    refinadas = 0
    for ln in fatura.linhas:
        consideradas = (
            [p for p in paginas if p.numero == ln.bbox.pagina] if ln.bbox else []
        ) or paginas
        com_texto = [p for p in consideradas if p.tem_texto]
        if not com_texto:
            linhas.append(ln.model_copy(update={"confianca": CONFIANCA_SEM_TEXTO}))
            continue
        achou = any(achar_valor(p.texto, ln.valor) for p in com_texto)
        bbox = _refinar_bbox(ln, paginas, usados) if achou else None
        if bbox is not None:
            refinadas += 1
        linhas.append(
            ln.model_copy(
                update={
                    "bbox": bbox or ln.bbox,
                    "confianca": CONFIANCA_ACHADO if achou else CONFIANCA_NAO_ACHADO,
                }
            )
        )
    avisos = list(fatura.avisos)
    if any(p.tem_texto for p in paginas):
        avisos.append(f"bbox_refinadas: {refinadas} de {len(linhas)} linha(s)")
    return fatura.model_copy(update={"linhas": linhas, "avisos": avisos})


# ------------------------------------------------------------------------ extração


def _extrair(
    prompt_id: str,
    paginas: list[PaginaRenderizada],
    llm: LLMClient,
    dica_fornecedor: str | None,
    chave_cache: str | None,
) -> FaturaExtraida:
    texto, imagens, enviadas, avisos = montar_entrada(paginas, dica_fornecedor)
    resposta = llm.gerar_estruturado(
        etapa="extrair",
        prompt_id=prompt_id,
        prompt_versao=PROMPT_VERSAO,
        texto=texto,
        imagens=imagens,
        schema=FaturaExtraidaLLM,
        chave_cache=chave_cache,
    )
    fatura = resposta.dados.para_dominio()
    fatura = refinar_e_pontuar(fatura, enviadas)
    return fatura.model_copy(update={"avisos": [*avisos, *fatura.avisos]})


def extrair_pdf(
    paginas: list[PaginaRenderizada],
    llm: LLMClient,
    dica_fornecedor: str | None = None,
    chave_cache: str | None = None,
) -> FaturaExtraida:
    """PDF/imagem renderizado → `FaturaExtraida` (origem `llm`), com `extrair_fatura_v1`."""
    if not paginas:
        raise ValueError("sem páginas para extrair")
    return _extrair(PROMPT_ID, paginas, llm, dica_fornecedor, chave_cache)


# ------------------------------------------------------------ dupla extração (CF-52)


class ExtracaoVerificada(BaseModel):
    fatura: FaturaExtraida
    validacao: ResultadoValidacao
    segunda_chamada: bool  # True se a primeira falhou e o prompt alternativo foi usado


def _soma_ok(v: ResultadoValidacao) -> bool:
    return not any(f.codigo == "soma_linhas" for f in v.falhas)


def _parear_linhas(base: list[LinhaExtraida], outra: list[LinhaExtraida]) -> dict[int, int]:
    """Índices (base → outra): por ordem quando o valor bate, depois por valor, depois por ordem."""
    pares: dict[int, int] = {}
    usadas: set[int] = set()
    for i, ln in enumerate(base):
        if i < len(outra) and outra[i].valor == ln.valor:
            pares[i] = i
            usadas.add(i)
    for i, ln in enumerate(base):
        if i in pares:
            continue
        for j, o in enumerate(outra):
            if j not in usadas and o.valor == ln.valor and o.moeda == ln.moeda:
                pares[i] = j
                usadas.add(j)
                break
    for i in range(len(base)):
        if i not in pares and i < len(outra) and i not in usadas:
            pares[i] = i
            usadas.add(i)
    return pares


def _combinar(
    base: FaturaExtraida, outra: FaturaExtraida, preferida: FaturaExtraida
) -> FaturaExtraida:
    """Campo a campo: igual nas duas mantém; divergente usa a `preferida` e cai para 0,3."""
    avisos: list[str] = []
    confianca_campos = dict(base.confianca_campos)

    cab_update: dict[str, object] = {}
    for campo in ("numero_documento", "data_emissao", "data_vencimento", "moeda", "total"):
        a, b = getattr(base.cabecalho, campo), getattr(outra.cabecalho, campo)
        if a != b:
            cab_update[campo] = getattr(preferida.cabecalho, campo)
            confianca_campos[campo] = CONFIANCA_DIVERGENTE
            avisos.append(f"campo_divergente: {campo} ({a} x {b})")
    cabecalho: CabecalhoExtraido = base.cabecalho.model_copy(update=cab_update)

    if len(base.linhas) != len(outra.linhas):
        avisos.append(f"numero_de_linhas_diverge: {len(base.linhas)} x {len(outra.linhas)}")
    pares = _parear_linhas(base.linhas, outra.linhas)
    linhas: list[LinhaExtraida] = []
    for i, ln in enumerate(base.linhas):
        if i not in pares:
            avisos.append(f"linha_sem_par: ordem {ln.ordem}")
            linhas.append(ln.model_copy(update={"confianca": CONFIANCA_DIVERGENTE}))
            continue
        o = outra.linhas[pares[i]]
        campos = [c for c in ("valor", "moeda", "quantidade", "valor_unitario")
                  if getattr(ln, c) != getattr(o, c)]  # fmt: skip
        if not campos:
            linhas.append(ln)
            continue
        origem = ln if preferida is base else o
        atualizacao: dict[str, object] = {c: getattr(origem, c) for c in campos}
        atualizacao["confianca"] = CONFIANCA_DIVERGENTE
        avisos.append(
            f"divergencia_linha: ordem {ln.ordem} ({', '.join(campos)}: "
            + ", ".join(f"{getattr(ln, c)} x {getattr(o, c)}" for c in campos)
            + ")"
        )
        linhas.append(ln.model_copy(update=atualizacao))
    return base.model_copy(
        update={
            "cabecalho": cabecalho,
            "linhas": linhas,
            "avisos": [*base.avisos, *avisos],
            "confianca_campos": confianca_campos,
        }
    )


def extrair_com_verificacao(
    paginas: list[PaginaRenderizada],
    llm: LLMClient,
    dica_fornecedor: str | None = None,
    chave_cache: str | None = None,
    contexto: ContextoValidacao | None = None,
) -> ExtracaoVerificada:
    """Extrai; se a validação falhar (grave ou não), extrai de novo com o prompt alternativo e
    combina as duas. Sem falha na primeira, não há segunda chamada."""
    ctx = contexto or ContextoValidacao.padrao()
    primeira = extrair_pdf(paginas, llm, dica_fornecedor, chave_cache)
    v1 = validar(primeira, ctx)
    if not v1.falhas:
        return ExtracaoVerificada(fatura=v1.fatura, validacao=v1, segunda_chamada=False)

    chave_alt = f"{chave_cache}:alt" if chave_cache is not None else None
    segunda = _extrair(PROMPT_ALT_ID, paginas, llm, dica_fornecedor, chave_alt)
    v2 = validar(segunda, ctx)

    usar_segunda_como_base = not v2.falhas  # a segunda passou e a primeira não
    (base, v_base), (outra, v_outra) = (
        ((v2.fatura, v2), (v1.fatura, v1))
        if usar_segunda_como_base
        else ((v1.fatura, v1), (v2.fatura, v2))
    )
    # valor de campo divergente: o da extração que passa na soma; se nenhuma passa, a primeira
    if _soma_ok(v_base):
        preferida = base
    elif _soma_ok(v_outra):
        preferida = outra
    else:
        preferida = v1.fatura
    combinada = _combinar(base, outra, preferida)
    marcas = ["segunda_extracao: executada"]
    if usar_segunda_como_base:
        marcas.append("segunda_extracao: usada_como_base")
    combinada = combinada.model_copy(update={"avisos": [*combinada.avisos, *marcas]})
    final = validar(combinada, ctx)
    return ExtracaoVerificada(fatura=final.fatura, validacao=final, segunda_chamada=True)
