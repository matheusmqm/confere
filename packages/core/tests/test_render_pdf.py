"""ingest.render: páginas, texto, blocos, imagens, erros e escala de bbox."""

import pymupdf
import pytest

from confere_core.ingest.render import (
    BlocoTexto,
    DocumentoCorrompido,
    DocumentoProtegido,
    PaginaRenderizada,
    escala_bbox,
    escala_bbox_inversa,
    renderizar,
)

PNG = b"\x89PNG\r\n\x1a\n"


def pdf_com_texto(paginas: int = 2) -> bytes:
    with pymupdf.open() as doc:
        for n in range(paginas):
            p = doc.new_page(width=595, height=842)
            p.insert_text((50, 100), f"THC DEST 1.234,56 pagina {n + 1}", fontsize=12)
            p.insert_text((50, 130), "ARMAZENAGEM R$ 950,00", fontsize=12)
        return bytes(doc.tobytes())


def pdf_so_imagem() -> bytes:
    with pymupdf.open() as doc:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 100), False)
        pix.clear_with(120)
        p = doc.new_page(width=300, height=200)
        p.insert_image(p.rect, stream=pix.tobytes("png"))
        return bytes(doc.tobytes())


def imagem(
    formato: str, largura: int, altura: int, *, gray: bool = False, alpha: bool = False
) -> bytes:
    cs = pymupdf.csGRAY if gray else pymupdf.csRGB
    pix = pymupdf.Pixmap(cs, pymupdf.IRect(0, 0, largura, altura), alpha)
    pix.clear_with(90 if gray else 200)
    return bytes(pix.tobytes(formato))


# ---------------------------------------------------------------------- PDF


def test_paginas_numeradas_com_png_e_dimensoes() -> None:
    paginas = renderizar(pdf_com_texto(2), "pdf", dpi=150)
    assert [p.numero for p in paginas] == [1, 2]
    p = paginas[0]
    assert p.png.startswith(PNG)
    assert (p.largura_pt, p.altura_pt) == (595.0, 842.0)
    assert abs(p.largura_px - 595 * 150 / 72) <= 1 and abs(p.altura_px - 842 * 150 / 72) <= 1
    pix = pymupdf.Pixmap(p.png)
    assert (pix.width, pix.height) == (p.largura_px, p.altura_px)


def test_dpi_muda_so_os_pixels() -> None:
    p72 = renderizar(pdf_com_texto(1), "pdf", dpi=72)[0]
    p144 = renderizar(pdf_com_texto(1), "pdf", dpi=144)[0]
    assert (p72.largura_pt, p144.largura_pt) == (595.0, 595.0)
    assert abs(p144.largura_px - 2 * p72.largura_px) <= 1


def test_texto_e_blocos_por_linha() -> None:
    p = renderizar(pdf_com_texto(2), "pdf")[1]
    assert p.tem_texto and "pagina 2" in p.texto and "ARMAZENAGEM" in p.texto
    assert [b.texto for b in p.blocos] == ["THC DEST 1.234,56 pagina 2", "ARMAZENAGEM R$ 950,00"]
    primeiro, segundo = p.blocos
    assert isinstance(primeiro, BlocoTexto) and len(primeiro.bbox) == 4
    x0, y0, x1, y1 = primeiro.bbox
    assert 0 <= x0 < x1 <= 595 and 0 <= y0 < y1 <= 842
    assert segundo.bbox[1] > primeiro.bbox[1]  # ordem de leitura: de cima para baixo


def test_max_paginas() -> None:
    assert [p.numero for p in renderizar(pdf_com_texto(5), "pdf", max_paginas=2)] == [1, 2]
    assert len(renderizar(pdf_com_texto(2), "pdf", max_paginas=10)) == 2


def test_pdf_so_de_imagem_nao_tem_texto() -> None:
    p = renderizar(pdf_so_imagem(), "pdf")[0]
    assert not p.tem_texto and p.texto.strip() == "" and p.blocos == []


def test_png_fica_fora_do_repr() -> None:
    p = renderizar(pdf_com_texto(1), "pdf")[0]
    assert "png=" not in repr(p) and "THC DEST" in repr(p)


def test_pdf_protegido_por_senha() -> None:
    with pymupdf.open() as doc:
        doc.new_page()
        protegido = bytes(
            doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="abc", owner_pw="xyz")
        )
    with pytest.raises(DocumentoProtegido):
        renderizar(protegido, "pdf")


def test_pdf_so_com_senha_de_dono_abre() -> None:
    with pymupdf.open() as doc:
        doc.new_page()
        so_dono = bytes(
            doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="", owner_pw="xyz")
        )
    assert len(renderizar(so_dono, "pdf")) == 1


@pytest.mark.parametrize("conteudo", [b"", b"nao e pdf", b"%PDF-1.7 lixo", b"\x00" * 64])
def test_pdf_corrompido(conteudo: bytes) -> None:
    with pytest.raises(DocumentoCorrompido):
        renderizar(conteudo, "pdf")


def test_pdf_truncado_ao_meio() -> None:
    bom = pdf_com_texto(1)
    with pytest.raises(DocumentoCorrompido):
        renderizar(bom[: len(bom) // 3], "pdf")


# ------------------------------------------------------------------- imagens


@pytest.mark.parametrize("formato", ["png", "jpg"])
def test_imagem_pequena_vira_uma_pagina_sem_texto(formato: str) -> None:
    (p,) = renderizar(imagem(formato, 800, 600), formato, dpi=100)  # type: ignore[arg-type]
    assert (p.numero, p.largura_px, p.altura_px) == (1, 800, 600)
    assert p.png.startswith(PNG) and not p.tem_texto and p.texto == "" and p.blocos == []
    assert (p.largura_pt, p.altura_pt) == (800 * 72 / 100, 600 * 72 / 100)


@pytest.mark.parametrize(("largura", "altura"), [(3000, 1500), (1500, 3000), (2001, 2001)])
def test_imagem_grande_e_reescalada_para_2000px(largura: int, altura: int) -> None:
    (p,) = renderizar(imagem("png", largura, altura), "png")
    assert max(p.largura_px, p.altura_px) == 2000
    assert abs(p.largura_px / p.altura_px - largura / altura) < 0.01
    pix = pymupdf.Pixmap(p.png)
    assert (pix.width, pix.height) == (p.largura_px, p.altura_px)


def test_imagem_em_tons_de_cinza_e_com_alfa_viram_rgb() -> None:
    for conteudo in (imagem("png", 100, 50, gray=True), imagem("png", 100, 50, alpha=True)):
        (p,) = renderizar(conteudo, "png")
        pix = pymupdf.Pixmap(p.png)
        assert pix.n == 3 and not pix.alpha


@pytest.mark.parametrize("conteudo", [b"", b"nao e imagem", b"\x89PNG\r\n\x1a\nlixo"])
def test_imagem_corrompida(conteudo: bytes) -> None:
    with pytest.raises(DocumentoCorrompido):
        renderizar(conteudo, "png")


# -------------------------------------------------------------------- escala


def pagina(px: tuple[int, int], pt: tuple[float, float]) -> PaginaRenderizada:
    return PaginaRenderizada(
        numero=1, png=b"", largura_px=px[0], altura_px=px[1],
        largura_pt=pt[0], altura_pt=pt[1], texto="", tem_texto=False, blocos=[],
    )  # fmt: skip


def test_escala_bbox_valores() -> None:
    p = pagina((1240, 1754), (595, 842))
    x0, y0, x1, y1 = escala_bbox((59.5, 84.2, 595.0, 842.0), p)
    assert (round(x0, 3), round(y0, 3)) == (124.0, 175.4)
    assert (round(x1, 3), round(y1, 3)) == (1240.0, 1754.0)


def test_escala_bbox_ida_e_volta() -> None:
    p = renderizar(pdf_com_texto(1), "pdf", dpi=200)[0]
    for bloco in p.blocos:
        volta = escala_bbox_inversa(escala_bbox(bloco.bbox, p), p)
        assert volta == pytest.approx(bloco.bbox)


def test_bbox_em_px_cai_sobre_o_texto_desenhado() -> None:
    p = renderizar(pdf_com_texto(1), "pdf", dpi=150)[0]
    x0, y0, x1, y1 = escala_bbox(p.blocos[0].bbox, p)
    assert 0 <= x0 < x1 <= p.largura_px and 0 <= y0 < y1 <= p.altura_px
    # a caixa em px tem a mesma proporção da caixa em pontos
    b = p.blocos[0].bbox
    assert (x1 - x0) / (y1 - y0) == pytest.approx((b[2] - b[0]) / (b[3] - b[1]), rel=0.01)
