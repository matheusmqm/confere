"""Render de páginas (PNG), texto e blocos com PyMuPDF (CF-44).

PDF: cada página vira PNG (`dpi`), texto simples e os blocos de texto por linha, com bbox em
pontos PDF (1/72"). Imagem PNG/JPG: uma única "página" sem texto, reescalada para no máximo
2000 px no maior lado. `escala_bbox` converte pontos ↔ pixels (o front desenha caixas na escala
do PDF).

Erros: `DocumentoProtegido` (PDF que pede senha) e `DocumentoCorrompido` (não abre, sem páginas
ou página que não renderiza). Nota: o módulo `fitz` do PyMuPDF é o mesmo `pymupdf`; usamos o
nome atual.
"""

from collections import defaultdict
from typing import Literal

import pymupdf
from pydantic import BaseModel, Field

BBox = tuple[float, float, float, float]
LADO_MAX_IMAGEM_PX = 2000
DPI_PADRAO = 150


class DocumentoProtegido(Exception):  # noqa: N818  (nome definido pela tarefa)
    """O PDF exige senha para abrir."""


class DocumentoCorrompido(Exception):  # noqa: N818  (nome definido pela tarefa)
    """O arquivo não abre, não tem páginas ou uma página não renderiza."""


class BlocoTexto(BaseModel):
    texto: str
    bbox: BBox  # [x0, y0, x1, y1] em pontos PDF


class PaginaRenderizada(BaseModel):
    numero: int = Field(ge=1)  # 1-indexado
    png: bytes = Field(repr=False)
    largura_px: int
    altura_px: int
    largura_pt: float
    altura_pt: float
    texto: str
    tem_texto: bool
    blocos: list[BlocoTexto]


def escala_bbox(bbox_pt: BBox, pagina: PaginaRenderizada) -> BBox:
    """Pontos PDF → pixels da imagem renderizada."""
    sx = pagina.largura_px / pagina.largura_pt
    sy = pagina.altura_px / pagina.altura_pt
    x0, y0, x1, y1 = bbox_pt
    return (x0 * sx, y0 * sy, x1 * sx, y1 * sy)


def escala_bbox_inversa(bbox_px: BBox, pagina: PaginaRenderizada) -> BBox:
    """Pixels da imagem renderizada → pontos PDF."""
    sx = pagina.largura_pt / pagina.largura_px
    sy = pagina.altura_pt / pagina.altura_px
    x0, y0, x1, y1 = bbox_px
    return (x0 * sx, y0 * sy, x1 * sx, y1 * sy)


def _blocos_por_linha(pagina: pymupdf.Page) -> list[BlocoTexto]:
    """Palavras (`get_text("words")`) agrupadas por linha, na ordem de leitura."""
    linhas: dict[tuple[int, int], list[tuple[float, float, float, float, str, int]]] = defaultdict(
        list
    )
    for x0, y0, x1, y1, palavra, bloco, linha, n in pagina.get_text("words"):
        linhas[(bloco, linha)].append((x0, y0, x1, y1, palavra, n))
    blocos: list[BlocoTexto] = []
    for chave in sorted(linhas):
        palavras = sorted(linhas[chave], key=lambda p: p[5])
        blocos.append(
            BlocoTexto(
                texto=" ".join(p[4] for p in palavras),
                bbox=(
                    min(p[0] for p in palavras),
                    min(p[1] for p in palavras),
                    max(p[2] for p in palavras),
                    max(p[3] for p in palavras),
                ),
            )
        )
    return blocos


def _renderizar_pdf(conteudo: bytes, dpi: int, max_paginas: int | None) -> list[PaginaRenderizada]:
    try:
        doc = pymupdf.open(stream=conteudo, filetype="pdf")
    except Exception as erro:  # FileDataError, EmptyFileError...
        raise DocumentoCorrompido(f"PDF não abre: {erro}") from erro
    with doc:
        if doc.needs_pass:
            raise DocumentoProtegido("PDF protegido por senha")
        if doc.page_count == 0:
            raise DocumentoCorrompido("PDF sem páginas")
        total = doc.page_count if max_paginas is None else min(doc.page_count, max_paginas)
        paginas: list[PaginaRenderizada] = []
        for i in range(total):
            try:
                pagina = doc[i]
                pix = pagina.get_pixmap(dpi=dpi, alpha=False)
                texto = pagina.get_text("text")
                blocos = _blocos_por_linha(pagina)
                paginas.append(
                    PaginaRenderizada(
                        numero=i + 1,
                        png=pix.tobytes("png"),
                        largura_px=pix.width,
                        altura_px=pix.height,
                        largura_pt=float(pagina.rect.width),
                        altura_pt=float(pagina.rect.height),
                        texto=texto,
                        tem_texto=bool(texto.strip()),
                        blocos=blocos,
                    )
                )
            except Exception as erro:
                raise DocumentoCorrompido(f"página {i + 1} não renderiza: {erro}") from erro
        return paginas


def _renderizar_imagem(conteudo: bytes, dpi: int) -> list[PaginaRenderizada]:
    try:
        pix = pymupdf.Pixmap(conteudo)
        if pix.alpha:
            pix = pymupdf.Pixmap(pix, 0)  # tira o canal alfa
        if pix.colorspace is None or pix.colorspace.n != 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        maior = max(pix.width, pix.height)
        if maior > LADO_MAX_IMAGEM_PX:
            fator = LADO_MAX_IMAGEM_PX / maior
            pix = pymupdf.Pixmap(
                pix, max(1, round(pix.width * fator)), max(1, round(pix.height * fator))
            )
        png = pix.tobytes("png")
    except Exception as erro:
        raise DocumentoCorrompido(f"imagem não abre: {erro}") from erro
    return [
        PaginaRenderizada(
            numero=1,
            png=png,
            largura_px=pix.width,
            altura_px=pix.height,
            largura_pt=pix.width * 72 / dpi,  # a imagem não tem tamanho físico: assume `dpi`
            altura_pt=pix.height * 72 / dpi,
            texto="",
            tem_texto=False,
            blocos=[],
        )
    ]


def renderizar(
    conteudo: bytes,
    tipo: Literal["pdf", "png", "jpg"],
    dpi: int = DPI_PADRAO,
    max_paginas: int | None = None,
) -> list[PaginaRenderizada]:
    """Páginas renderizadas de um PDF, ou a única "página" de uma imagem."""
    if tipo == "pdf":
        return _renderizar_pdf(conteudo, dpi, max_paginas)
    return _renderizar_imagem(conteudo, dpi)


def contar_paginas(conteudo: bytes, tipo: Literal["pdf", "png", "jpg"]) -> int:
    """Número de páginas sem renderizar (imagem = 1). Mesmos erros de `renderizar`."""
    if tipo != "pdf":
        _renderizar_imagem(conteudo, DPI_PADRAO)  # só para validar que a imagem abre
        return 1
    try:
        doc = pymupdf.open(stream=conteudo, filetype="pdf")
    except Exception as erro:
        raise DocumentoCorrompido(f"PDF não abre: {erro}") from erro
    with doc:
        if doc.needs_pass:
            raise DocumentoProtegido("PDF protegido por senha")
        if doc.page_count == 0:
            raise DocumentoCorrompido("PDF sem páginas")
        return int(doc.page_count)
