"""Ruído de foto de celular: parâmetros, formatos de saída e aplicação ao lote."""

import hashlib
import json
import random
from pathlib import Path
from typing import Any

import pymupdf
import pytest
from PIL import Image
from PIL.JpegImagePlugin import JpegImageFile

from confere_synth import ruido
from confere_synth.ruido import (
    aplicar_ruido,
    aplicar_ruido_ao_lote,
    degradar,
    rasterizar,
    sortear_formato,
    sortear_parametros,
)


def criar_pdf(caminho: Path, paginas: int = 1, rotulo: str = "Documento") -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as doc:
        for n in range(paginas):
            pagina = doc.new_page(width=595, height=842)
            for i in range(25):
                pagina.insert_text(
                    (50, 60 + i * 24), f"{rotulo} p{n} linha {i} THC DEST 1.234,56", fontsize=11
                )
        doc.save(caminho)
    return caminho


def sha(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


# ---------------------------------------------------------------- parâmetros


def test_parametros_dentro_dos_intervalos() -> None:
    for semente in range(300):
        p = sortear_parametros(random.Random(semente))
        assert 110 <= p.dpi <= 140
        assert -4.0 <= p.angulo <= 4.0
        assert len(p.deslocamentos) == 8 and all(abs(d) <= 0.03 for d in p.deslocamentos)
        assert 0.6 <= p.blur <= 1.2
        assert 0.9 <= p.brilho <= 1.1 and 0.9 <= p.contraste <= 1.1
        assert 45 <= p.qualidade <= 65
        assert p.lado in ("esq", "dir") and 0.2 <= p.sombra_largura <= 0.45


def test_um_terco_vira_foto() -> None:
    rng = random.Random(0)
    formatos = [sortear_formato(rng) for _ in range(900)]
    assert 0.28 < formatos.count("jpg") / len(formatos) < 0.38


def test_rasterizar_respeita_o_dpi(tmp_path: Path) -> None:
    pdf = criar_pdf(tmp_path / "a.pdf", paginas=2)
    paginas = rasterizar(pdf, 120)
    assert len(paginas) == 2
    assert (
        abs(paginas[0].width - 595 * 120 / 72) <= 1 and abs(paginas[0].height - 842 * 120 / 72) <= 1
    )


def test_degradar_muda_a_imagem_sem_perder_o_formato(tmp_path: Path) -> None:
    original = rasterizar(criar_pdf(tmp_path / "a.pdf"), 120)[0]
    p = sortear_parametros(random.Random(4))
    saida = degradar(original, p)
    assert saida.mode == "RGB"
    assert saida.width >= original.width and saida.height >= original.height  # rotação expande
    assert saida.tobytes() != original.tobytes()
    assert degradar(original, p).tobytes() == saida.tobytes()  # determinístico


# ------------------------------------------------------------- aplicar_ruido


def test_foto_jpg_so_da_primeira_pagina(tmp_path: Path) -> None:
    pdf = criar_pdf(tmp_path / "doc.pdf", paginas=2)
    jpg = aplicar_ruido(pdf, tmp_path / "out", random.Random(3), formato="jpg")
    assert jpg.name == "doc_ruido.jpg"
    with Image.open(jpg) as im:
        assert isinstance(im, JpegImageFile) and im.width > 800
        assert 10 <= im.quantization[0][0] <= 19  # qualidade 45 a 65


def test_pdf_so_de_imagem_sem_camada_de_texto(tmp_path: Path) -> None:
    pdf = criar_pdf(tmp_path / "doc.pdf", paginas=2)
    assert "linha" in pymupdf.open(pdf)[0].get_text()
    saida = aplicar_ruido(pdf, tmp_path / "out", random.Random(3), formato="pdf")
    assert saida.name == "doc_ruido.pdf"
    with pymupdf.open(saida) as doc:
        assert doc.page_count == 2
        for pagina in doc:
            assert pagina.get_text().strip() == ""
            assert len(pagina.get_images()) == 1


@pytest.mark.parametrize("formato", ["jpg", "pdf"])
def test_reproduzivel_e_sensivel_ao_rng(tmp_path: Path, formato: Any) -> None:
    pdf = criar_pdf(tmp_path / "doc.pdf")
    a = aplicar_ruido(pdf, tmp_path / "a", random.Random(3), formato=formato)
    b = aplicar_ruido(pdf, tmp_path / "b", random.Random(3), formato=formato)
    c = aplicar_ruido(pdf, tmp_path / "c", random.Random(4), formato=formato)
    assert a.read_bytes() == b.read_bytes() != c.read_bytes()


def test_sem_formato_o_rng_decide(tmp_path: Path) -> None:
    pdf = criar_pdf(tmp_path / "doc.pdf")
    sufixos: set[str] = set()
    for semente in range(40):  # para assim que os dois formatos aparecem
        sufixos.add(aplicar_ruido(pdf, tmp_path / f"o{semente}", random.Random(semente)).suffix)
        if len(sufixos) == 2:
            break
    assert sufixos == {".jpg", ".pdf"}


# --------------------------------------------------------------------- lote


def montar_lote(raiz: Path, n: int = 20, extratos_de_2_paginas: int = 2) -> list[dict[str, Any]]:
    pdfs: list[dict[str, Any]] = []
    docs: list[dict[str, Any]] = []
    for i in range(n):
        longo = i < extratos_de_2_paginas
        arquivo = f"documentos/doc{i:03d}.pdf"
        criar_pdf(raiz / arquivo, paginas=2 if longo else 1, rotulo=f"Doc{i}")
        item = {
            "arquivo": arquivo, "sha256": sha(raiz / arquivo), "id": f"id{i:03d}",
            "tipo": "extrato" if longo else "fatura", "fornecedor_id": "f", "numero": str(i),
        }  # fmt: skip
        pdfs.append(item)
        docs.append({"id": item["id"], "arquivo": arquivo, "sha256": item["sha256"], "tipo": "x"})
    (raiz / "manifest.json").write_text(json.dumps({"seed": 42, "pdfs": pdfs}), encoding="utf-8")
    (raiz / "documentos.json").write_text(json.dumps(docs), encoding="utf-8")
    return pdfs


def manifest(raiz: Path) -> dict[str, Any]:
    return dict(json.loads((raiz / "manifest.json").read_text(encoding="utf-8")))


def test_lote_seleciona_15_por_cento_fora_dos_de_duas_paginas(tmp_path: Path) -> None:
    original = montar_lote(tmp_path)
    escolhidos = aplicar_ruido_ao_lote(random.Random(1), tmp_path)
    pdfs = manifest(tmp_path)["pdfs"]
    com_ruido = [p for p in pdfs if p.get("ruido")]
    assert len(escolhidos) == len(com_ruido) == round(0.15 * len(original)) == 3
    assert all(p["tipo"] != "extrato" for p in com_ruido)  # os de 2 páginas ficam de fora


def test_lote_atualiza_manifest_e_preserva_o_resto(tmp_path: Path) -> None:
    original = montar_lote(tmp_path)
    aplicar_ruido_ao_lote(random.Random(1), tmp_path)
    pdfs = manifest(tmp_path)["pdfs"]
    for antes, depois in zip(original, pdfs, strict=True):
        if not depois.get("ruido"):
            assert depois == antes
            continue
        assert (
            depois["arquivo_original"] == antes["arquivo"] and depois["arquivo"] != antes["arquivo"]
        )
        assert depois["sha256_original"] == antes["sha256"]
        assert sha(tmp_path / depois["arquivo"]) == depois["sha256"] != antes["sha256"]
        assert (tmp_path / antes["arquivo"]).exists()  # o PDF limpo continua lá
        assert depois["formato_ruido"] in ("jpg", "pdf")
        assert depois["foto_torta"] == (depois["formato_ruido"] == "jpg")
        assert depois["arquivo"].endswith(".jpg" if depois["foto_torta"] else ".pdf")


def test_lote_garante_ao_menos_uma_foto_torta(tmp_path: Path) -> None:
    for semente in range(5):
        pasta = tmp_path / f"s{semente}"
        montar_lote(pasta, n=14)
        aplicar_ruido_ao_lote(random.Random(semente), pasta)
        assert any(p.get("foto_torta") for p in manifest(pasta)["pdfs"]), semente


def test_lote_atualiza_documentos_json(tmp_path: Path) -> None:
    montar_lote(tmp_path)
    aplicar_ruido_ao_lote(random.Random(1), tmp_path)
    por_id = {p["id"]: p for p in manifest(tmp_path)["pdfs"]}
    docs = json.loads((tmp_path / "documentos.json").read_text(encoding="utf-8"))
    assert sum(d["ruido"] for d in docs) == 3
    for d in docs:
        assert (d["arquivo"], d["sha256"]) == (
            por_id[d["id"]]["arquivo"],
            por_id[d["id"]]["sha256"],
        )
        assert d["ruido"] == bool(por_id[d["id"]].get("ruido"))


def test_lote_e_idempotente(tmp_path: Path) -> None:
    montar_lote(tmp_path)
    aplicar_ruido_ao_lote(random.Random(1), tmp_path)
    primeiro = (tmp_path / "manifest.json").read_bytes()
    arquivos = sorted(p.name for p in (tmp_path / "documentos").iterdir())
    aplicar_ruido_ao_lote(random.Random(1), tmp_path)  # reverte e sorteia de novo
    assert (tmp_path / "manifest.json").read_bytes() == primeiro
    assert sorted(p.name for p in (tmp_path / "documentos").iterdir()) == arquivos


def test_trocar_o_rng_troca_a_selecao_sem_sobras(tmp_path: Path) -> None:
    montar_lote(tmp_path)
    a = aplicar_ruido_ao_lote(random.Random(1), tmp_path)
    b = aplicar_ruido_ao_lote(random.Random(2), tmp_path)
    assert a != b
    ruidosos = [p["arquivo"] for p in manifest(tmp_path)["pdfs"] if p.get("ruido")]
    em_disco = [
        f"documentos/{p.name}" for p in (tmp_path / "documentos").iterdir() if "_ruido" in p.name
    ]
    assert sorted(ruidosos) == sorted(em_disco)  # nada do sorteio anterior ficou para trás


def test_lote_pequeno_ainda_tem_um_com_ruido(tmp_path: Path) -> None:
    montar_lote(tmp_path, n=4, extratos_de_2_paginas=0)
    assert len(aplicar_ruido_ao_lote(random.Random(1), tmp_path)) == 1


def test_lote_so_com_documentos_de_duas_paginas(tmp_path: Path) -> None:
    montar_lote(tmp_path, n=3, extratos_de_2_paginas=3)
    assert aplicar_ruido_ao_lote(random.Random(1), tmp_path) == []
    assert not any(p.get("ruido") for p in manifest(tmp_path)["pdfs"])


def test_parametros_publicos_do_modulo() -> None:
    assert ruido.PCT_SELECIONADOS == 0.15 and ruido.QUALIDADE_JPEG == (45, 65)
    assert ruido.DPI == (110, 140)
