"""PDFs compostos (fatura + BL): seleção, montagem, cortes esperados e CLI."""

import hashlib
import json
import random
import re
import uuid
from pathlib import Path

import pymupdf
import pytest

from confere_core.costcode.catalogo import Catalogo
from confere_core.domain import CortePagina
from confere_core.ingest.separar import separar
from confere_synth import cli, compostos, faturas
from confere_synth.modelos import DocumentoSintetico, Mundo
from confere_synth.mundo import gerar_mundo

YAML = Path(__file__).resolve().parents[3] / "config" / "codigos_custo.yaml"


def pdf_falso(html: str, destino: Path) -> None:
    """Escreve um PDF real: o BL tem 1 página; faturas e extratos, 2. O texto traz o <title>."""
    achado = re.search(r"<title>([^<]*)</title>", html)
    titulo = achado.group(1) if achado else "sem-titulo"
    paginas = 1 if "BILL OF LADING" in html else 2
    destino.parent.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as doc:
        for n in range(paginas):
            doc.new_page(width=595, height=842).insert_text(
                (50, 100), f"DOC {titulo} pag{n + 1}", fontsize=12
            )
        doc.save(destino)


@pytest.fixture
def com_pdf_falso(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(faturas, "_escrever_pdf", pdf_falso)


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    return Catalogo.carregar(YAML)


@pytest.fixture(scope="module")
def mundo(catalogo: Catalogo) -> Mundo:
    return gerar_mundo(42, catalogo)


@pytest.fixture(scope="module")
def docs(mundo: Mundo, catalogo: Catalogo) -> list[DocumentoSintetico]:
    return faturas.gerar_documentos_limpos(random.Random("42:faturas"), mundo, catalogo)


def textos(origem: Path | bytes) -> list[str]:
    doc = (
        pymupdf.open(origem)
        if isinstance(origem, Path)
        else pymupdf.open(stream=origem, filetype="pdf")
    )
    with doc:
        return [doc[i].get_text().strip() for i in range(doc.page_count)]


# --------------------------------------------------------------------- seleção


def test_tres_planos_de_processos_e_armadores_distintos(
    mundo: Mundo, docs: list[DocumentoSintetico]
) -> None:
    planos = compostos.gerar_compostos(random.Random(1), mundo, docs)
    assert len(planos) == 3
    assert len({p.fatura.processo_id for p in planos}) == 3
    assert len({p.fatura.fornecedor_id for p in planos}) == 3  # um por armador
    forn = {f.id: f for f in mundo.fornecedores}
    assert all(
        forn[p.fatura.fornecedor_id].tipo == "armador" and p.fatura.tipo == "fatura" for p in planos
    )
    assert len({p.id for p in planos}) == 3


def test_bl_usa_os_dados_do_processo(mundo: Mundo, docs: list[DocumentoSintetico]) -> None:
    proc = {p.id: p for p in mundo.processos}
    for plano in compostos.gerar_compostos(random.Random(1), mundo, docs):
        p = proc[plano.fatura.processo_id or uuid.UUID(int=0)]
        master = next(r.valor for r in p.referencias if r.tipo == "bl_master")
        assert plano.numero_bl == master and re.fullmatch(r"[A-Z]{3}X\d{9}", master)
        esperados = [r.valor for r in p.referencias if r.tipo == "conteiner"]
        assert [c.numero for c in plano.bl.conteineres] == esperados
        assert (plano.bl.navio, plano.bl.viagem) == (p.navio, p.viagem)
        assert (plano.bl.porto_embarque, plano.bl.porto_descarga) == (p.origem, p.destino)


def test_bl_html(mundo: Mundo, docs: list[DocumentoSintetico]) -> None:
    plano = compostos.gerar_compostos(random.Random(1), mundo, docs)[0]
    html = compostos.renderizar_bl_html(plano)
    assert "BILL OF LADING" in html and plano.numero_bl in html
    assert all(c.numero in html and c.lacre in html for c in plano.bl.conteineres)
    assert "SINTÉTICO — dados fictícios" in html and "fictitious" in html.lower()
    assert not re.search(r"(src|href)\s*=|https?://|url\(", html)


def test_determinismo(mundo: Mundo, docs: list[DocumentoSintetico]) -> None:
    a = compostos.gerar_compostos(random.Random(1), mundo, docs)
    assert a == compostos.gerar_compostos(random.Random(1), mundo, docs)
    assert a != compostos.gerar_compostos(random.Random(2), mundo, docs)


def test_menos_candidatos_que_n(mundo: Mundo, docs: list[DocumentoSintetico]) -> None:
    so_um = [d for d in docs if d.fornecedor_id == "atlantida-ocean-lines" and d.tipo == "fatura"]
    assert len(compostos.gerar_compostos(random.Random(1), mundo, so_um[:1])) == 1
    assert compostos.gerar_compostos(random.Random(1), mundo, []) == []


# ------------------------------------------------------------------ montagem


def avulsa(saida: Path, doc: DocumentoSintetico) -> None:
    pdf_falso(f"<title>{doc.numero}</title>", saida / (doc.arquivo or ""))


def test_composto_fatura_mais_bl(
    tmp_path: Path, com_pdf_falso: None, mundo: Mundo, docs: list[DocumentoSintetico]
) -> None:
    plano = compostos.gerar_compostos(random.Random(1), mundo, docs)[0]
    avulsa(tmp_path, plano.fatura)
    entrada = compostos.gravar_composto(plano, tmp_path)

    arquivo = tmp_path / entrada["arquivo"]
    assert entrada["arquivo"] == f"documentos/{plano.id}.pdf" and arquivo.exists()
    assert len(textos(arquivo)) == 3  # fatura (2 páginas) + BL (1)
    assert entrada["cortes_esperados"] == [
        {"inicio": 1, "fim": 2, "tipo": "fatura"},
        {"inicio": 3, "fim": 3, "tipo": "bl"},
    ]
    assert entrada["tipo"] == "composto" and entrada["numero_bl"] == plano.numero_bl
    assert entrada["substitui_arquivo"] == plano.fatura.arquivo
    assert entrada["documento_id"] == str(plano.fatura.id)
    assert entrada["sha256"] == hashlib.sha256(arquivo.read_bytes()).hexdigest()


def test_cortes_esperados_separam_o_composto_de_volta(
    tmp_path: Path, com_pdf_falso: None, mundo: Mundo, docs: list[DocumentoSintetico]
) -> None:
    plano = compostos.gerar_compostos(random.Random(1), mundo, docs)[1]
    avulsa(tmp_path, plano.fatura)
    entrada = compostos.gravar_composto(plano, tmp_path)
    cortes = [CortePagina.model_validate(c) for c in entrada["cortes_esperados"]]
    fatura_filho, bl_filho = separar((tmp_path / entrada["arquivo"]).read_bytes(), cortes)
    assert (fatura_filho.tipo, bl_filho.tipo) == ("fatura", "bl")
    assert all(plano.fatura.numero in t for t in textos(fatura_filho.conteudo))
    assert all(plano.numero_bl in t for t in textos(bl_filho.conteudo))


def test_sem_a_fatura_avulsa_falha_claro(
    tmp_path: Path, com_pdf_falso: None, mundo: Mundo, docs: list[DocumentoSintetico]
) -> None:
    plano = compostos.gerar_compostos(random.Random(1), mundo, docs)[0]
    with pytest.raises(FileNotFoundError, match="rode `faturas` antes"):
        compostos.gravar_composto(plano, tmp_path)


# ----------------------------------------------------------------------- CLI


def test_cli_gera_tres_compostos_e_e_idempotente(tmp_path: Path, com_pdf_falso: None) -> None:
    assert cli.main(["faturas", "--saida", str(tmp_path)]) == 0
    assert cli.main(["compostos", "--seed", "42", "--saida", str(tmp_path)]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    comps = manifest["compostos"]
    assert len(comps) == 3 and len({c["fornecedor_id"] for c in comps}) == 3
    avulsas = {p["arquivo"] for p in manifest["pdfs"]}
    for c in comps:
        assert (tmp_path / c["arquivo"]).exists() and c["substitui_arquivo"] in avulsas
        assert [x["tipo"] for x in c["cortes_esperados"]] == ["fatura", "bl"]
        assert c["cortes_esperados"][1]["inicio"] == c["cortes_esperados"][0]["fim"] + 1

    primeiro = (tmp_path / "manifest.json").read_bytes()
    arquivos = sorted(p.name for p in (tmp_path / "documentos").iterdir())
    assert cli.main(["compostos", "--seed", "42", "--saida", str(tmp_path)]) == 0
    assert (tmp_path / "manifest.json").read_bytes() == primeiro
    assert sorted(p.name for p in (tmp_path / "documentos").iterdir()) == arquivos


def test_cli_refazer_faturas_nao_apaga_a_chave_compostos(
    tmp_path: Path, com_pdf_falso: None
) -> None:
    cli.main(["faturas", "--saida", str(tmp_path)])
    cli.main(["compostos", "--saida", str(tmp_path)])
    cli.main(["faturas", "--saida", str(tmp_path)])
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["compostos"]) == 3


def test_cli_sem_manifest_e_sem_faturas(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], com_pdf_falso: None
) -> None:
    assert cli.main(["compostos", "--saida", str(tmp_path)]) == 1
    assert "rode `faturas` antes" in capsys.readouterr().err
    (tmp_path / "manifest.json").write_text("{}", encoding="utf-8")  # sem os PDFs avulsos
    assert cli.main(["compostos", "--saida", str(tmp_path)]) == 1
    assert "rode `faturas` antes" in capsys.readouterr().err
