"""Ruído de "foto de celular" sobre PDFs sintéticos (CF-37).

`aplicar_ruido` rasteriza o PDF (PyMuPDF, 110 a 140 dpi) e degrada cada página com Pillow:
rotação de -4° a +4° (fundo cinza-claro), perspectiva leve (cantos até 3%), desfoque gaussiano
(raio 0,6 a 1,2), brilho e contraste ±10%, sombra lateral em gradiente e JPEG de qualidade 45
a 65. Em 1/3 dos casos o resultado é um JPG único (só a 1ª página, como uma foto enviada pelo
WhatsApp); nos demais, um PDF só de imagem, sem camada de texto.

`aplicar_ruido_ao_lote` escolhe ~15% dos PDFs do manifest (fora os de mais de uma página e os
DACTEs) e atualiza `manifest.json` e `documentos.json`. Ao menos um documento do lote sai como
JPG e fica marcado `foto_torta: true`: é a "foto torta" que o lote de demonstração (CF-114) usa.
É idempotente: reverte o ruído anterior antes de sortear de novo.
"""

import hashlib
import io
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pymupdf
from PIL import Image, ImageEnhance, ImageFilter

DPI = (110, 140)
ANGULO_MAX = 4.0
DESLOCAMENTO_MAX = 0.03
BLUR = (0.6, 1.2)
AJUSTE_MAX = 0.10
SOMBRA_LARGURA = (0.20, 0.45)
SOMBRA_INTENSIDADE = (0.12, 0.30)
QUALIDADE_JPEG = (45, 65)
FUNDO = (228, 228, 226)
PCT_FOTO = 1 / 3
PCT_SELECIONADOS = 0.15

Formato = Literal["jpg", "pdf"]


@dataclass(frozen=True)
class Parametros:
    dpi: int
    angulo: float
    deslocamentos: tuple[float, ...]  # 8 valores em fração da largura/altura, 2 por canto
    blur: float
    brilho: float
    contraste: float
    lado: Literal["esq", "dir"]
    sombra_largura: float
    sombra_intensidade: float
    qualidade: int


def sortear_parametros(rng: random.Random) -> Parametros:
    return Parametros(
        dpi=rng.randint(*DPI),
        angulo=rng.uniform(-ANGULO_MAX, ANGULO_MAX),
        deslocamentos=tuple(rng.uniform(-DESLOCAMENTO_MAX, DESLOCAMENTO_MAX) for _ in range(8)),
        blur=rng.uniform(*BLUR),
        brilho=1 + rng.uniform(-AJUSTE_MAX, AJUSTE_MAX),
        contraste=1 + rng.uniform(-AJUSTE_MAX, AJUSTE_MAX),
        lado=rng.choice(("esq", "dir")),
        sombra_largura=rng.uniform(*SOMBRA_LARGURA),
        sombra_intensidade=rng.uniform(*SOMBRA_INTENSIDADE),
        qualidade=rng.randint(*QUALIDADE_JPEG),
    )


def sortear_formato(rng: random.Random) -> Formato:
    return "jpg" if rng.random() < PCT_FOTO else "pdf"


def rasterizar(pdf: Path, dpi: int) -> list[Image.Image]:
    paginas: list[Image.Image] = []
    with pymupdf.open(pdf) as doc:
        for pagina in doc:
            pix = pagina.get_pixmap(dpi=dpi, alpha=False)
            paginas.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    return paginas


def degradar(img: Image.Image, p: Parametros) -> Image.Image:
    """Rotação, perspectiva, desfoque, brilho/contraste e sombra lateral (sem o JPEG)."""
    img = img.rotate(p.angulo, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=FUNDO)
    w, h = img.size
    cantos = [(0, 0), (0, h), (w, h), (w, 0)]  # NO, SO, SE, NE da região de origem
    quad: list[float] = []
    for i, (x, y) in enumerate(cantos):
        quad += [x + p.deslocamentos[2 * i] * w, y + p.deslocamentos[2 * i + 1] * h]
    img = img.transform(
        (w, h),
        Image.Transform.QUAD,
        data=tuple(quad),
        resample=Image.Resampling.BICUBIC,
        fillcolor=FUNDO,
    )
    img = img.filter(ImageFilter.GaussianBlur(radius=p.blur))
    img = ImageEnhance.Brightness(img).enhance(p.brilho)
    img = ImageEnhance.Contrast(img).enhance(p.contraste)

    colunas = np.arange(w, dtype=np.float32)
    distancia = colunas if p.lado == "esq" else (w - 1) - colunas
    forca = np.clip(1 - distancia / (p.sombra_largura * w), 0, 1) ** 1.5
    fator = (1 - p.sombra_intensidade * forca)[None, :, None]
    sombreada = np.asarray(img, dtype=np.float32) * fator
    return Image.fromarray(np.clip(sombreada, 0, 255).astype(np.uint8), "RGB")


def _jpeg(img: Image.Image, p: Parametros) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=p.qualidade, dpi=(p.dpi, p.dpi))
    return buf.getvalue()


def aplicar_ruido(
    pdf_in: str | Path,
    saida: str | Path,
    rng: random.Random,
    *,
    formato: Formato | None = None,
) -> Path:
    """Gera a versão "foto de celular" de `pdf_in` em `saida` (pasta) e devolve o caminho.

    O nome é `<nome do pdf>_ruido.jpg` (1ª página apenas) ou `<nome>_ruido.pdf` (PDF só de
    imagem). Sem `formato`, 1/3 dos casos vira JPG, sorteado com o `rng`.
    """
    pdf_in = Path(pdf_in)
    pasta = Path(saida)
    pasta.mkdir(parents=True, exist_ok=True)
    escolhido = formato or sortear_formato(rng)
    params = sortear_parametros(rng)

    paginas = [degradar(img, params) for img in rasterizar(pdf_in, params.dpi)]
    if escolhido == "jpg":
        destino = pasta / f"{pdf_in.stem}_ruido.jpg"
        destino.write_bytes(_jpeg(paginas[0], params))
        return destino

    destino = pasta / f"{pdf_in.stem}_ruido.pdf"
    with pymupdf.open() as saida_pdf:
        for img in paginas:
            largura_pt, altura_pt = (img.width * 72 / params.dpi, img.height * 72 / params.dpi)
            pagina = saida_pdf.new_page(width=largura_pt, height=altura_pt)
            pagina.insert_image(pagina.rect, stream=_jpeg(img, params))
        saida_pdf.set_metadata({})
        saida_pdf.save(destino, deflate=True, no_new_id=True)
    return destino


# --------------------------------------------------------------------- lote


def _sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _n_paginas(pdf: Path) -> int:
    with pymupdf.open(pdf) as doc:
        return int(doc.page_count)


def _gravar_json(caminho: Path, dados: Any) -> None:
    texto = json.dumps(dados, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    caminho.write_text(texto, encoding="utf-8", newline="\n")


def _reverter(saida_dir: Path, pdfs: list[dict[str, Any]]) -> None:
    """Desfaz um ruído anterior: volta ao PDF limpo e apaga o arquivo com ruído."""
    for item in pdfs:
        if not item.get("ruido"):
            continue
        (saida_dir / item["arquivo"]).unlink(missing_ok=True)
        item["arquivo"] = item.pop("arquivo_original")
        item["sha256"] = item.pop("sha256_original")
        for chave in ("ruido", "foto_torta", "formato_ruido"):
            item.pop(chave, None)


def aplicar_ruido_ao_lote(
    rng: random.Random, saida_dir: str | Path, pct: float = PCT_SELECIONADOS
) -> list[str]:
    """Aplica ruído a ~`pct` dos PDFs do manifest; devolve os `arquivo` com ruído.

    Atualiza `manifest.json` (`ruido: true`, novo `arquivo` e `sha256`, mais `arquivo_original`
    e `sha256_original`) e, se existir, `documentos.json`.
    """
    pasta = Path(saida_dir)
    caminho_manifest = pasta / "manifest.json"
    manifest: dict[str, Any] = json.loads(caminho_manifest.read_text(encoding="utf-8"))
    pdfs: list[dict[str, Any]] = manifest.get("pdfs", [])
    _reverter(pasta, pdfs)

    elegiveis = [
        item
        for item in sorted(pdfs, key=lambda i: str(i["arquivo"]))
        if str(item["arquivo"]).endswith(".pdf") and _n_paginas(pasta / item["arquivo"]) == 1
    ]
    escolhidos: list[dict[str, Any]] = []
    if elegiveis:
        quantos = max(1, round(pct * len(pdfs)))
        escolhidos = rng.sample(elegiveis, min(quantos, len(elegiveis)))

    formatos: list[Formato] = [sortear_formato(rng) for _ in escolhidos]
    if escolhidos and "jpg" not in formatos:
        formatos[0] = "jpg"  # garante a "foto torta"

    for item, formato in zip(escolhidos, formatos, strict=True):
        original = pasta / item["arquivo"]
        novo = aplicar_ruido(original, pasta / "documentos", rng, formato=formato)
        item.update(
            ruido=True,
            arquivo_original=item["arquivo"],
            sha256_original=item["sha256"],
            arquivo=novo.relative_to(pasta).as_posix(),
            sha256=_sha256(novo),
            formato_ruido=formato,
            foto_torta=formato == "jpg",
        )

    caminho_docs = pasta / "documentos.json"
    if caminho_docs.exists():
        docs: list[dict[str, Any]] = json.loads(caminho_docs.read_text(encoding="utf-8"))
        por_id = {item["id"]: item for item in pdfs}
        for doc in docs:
            entrada = por_id.get(doc["id"])
            if entrada is None:
                continue
            doc["arquivo"], doc["sha256"] = entrada["arquivo"], entrada["sha256"]
            doc["ruido"] = bool(entrada.get("ruido"))
            doc["arquivo_original"] = entrada.get("arquivo_original")
        _gravar_json(caminho_docs, docs)

    manifest["pdfs"] = pdfs
    _gravar_json(caminho_manifest, manifest)
    return [str(item["arquivo"]) for item in escolhidos]
