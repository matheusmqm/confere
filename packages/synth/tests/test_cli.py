"""CLI `faturas`: PDFs, mundo.json, documentos.json e manifest.json."""

import json
from pathlib import Path

import pymupdf
import pytest

from confere_synth import cli, faturas
from confere_synth.modelos import DocumentoSintetico, Mundo


def _pdf_falso(html: str, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(b"%PDF-falso\n" + html.encode("utf-8"))


@pytest.fixture
def com_pdf_falso(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(faturas, "_escrever_pdf", _pdf_falso)


def test_gera_pdfs_e_arquivos_de_apoio(tmp_path: Path, com_pdf_falso: None) -> None:
    assert cli.main(["faturas", "--seed", "42", "--saida", str(tmp_path)]) == 0

    docs = [
        DocumentoSintetico.model_validate(d)
        for d in json.loads((tmp_path / "documentos.json").read_text(encoding="utf-8"))
    ]
    pdfs = sorted((tmp_path / "documentos").glob("*.pdf"))
    assert len(docs) == len(pdfs) > 150
    assert {p.name for p in pdfs} == {f"{d.id}.pdf" for d in docs}
    assert all(d.sha256 and d.arquivo for d in docs)
    assert (
        Mundo.model_validate_json((tmp_path / "mundo.json").read_text(encoding="utf-8")).seed == 42
    )


def test_manifest_tem_hash_de_cada_pdf(tmp_path: Path, com_pdf_falso: None) -> None:
    cli.main(["faturas", "--saida", str(tmp_path)])  # seed padrão 42
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["seed"] == 42
    assert manifest["documentos"]["total"] == len(manifest["pdfs"])
    assert sum(manifest["documentos"]["por_tipo"].values()) == len(manifest["pdfs"])
    assert manifest["documentos"]["por_tipo"]["extrato"] == 3
    for item in manifest["pdfs"]:
        assert faturas.sha256_de(tmp_path / item["arquivo"]) == item["sha256"]
    assert [i["arquivo"] for i in manifest["pdfs"]] == sorted(
        i["arquivo"] for i in manifest["pdfs"]
    )
    assert list(manifest) == sorted(manifest)  # chaves ordenadas


def test_preserva_chaves_de_outras_etapas_e_e_idempotente(
    tmp_path: Path, com_pdf_falso: None
) -> None:
    (tmp_path / "manifest.json").write_text('{"outra_etapa": {"x": 1}}', encoding="utf-8")
    cli.main(["faturas", "--seed", "42", "--saida", str(tmp_path)])
    primeiro = (tmp_path / "manifest.json").read_bytes()
    assert json.loads(primeiro)["outra_etapa"] == {"x": 1}
    cli.main(["faturas", "--seed", "42", "--saida", str(tmp_path)])
    assert (tmp_path / "manifest.json").read_bytes() == primeiro


def test_seeds_diferentes_geram_documentos_diferentes(tmp_path: Path, com_pdf_falso: None) -> None:
    cli.main(["faturas", "--seed", "1", "--saida", str(tmp_path / "a")])
    cli.main(["faturas", "--seed", "2", "--saida", str(tmp_path / "b")])
    a = json.loads((tmp_path / "a" / "manifest.json").read_text(encoding="utf-8"))
    b = json.loads((tmp_path / "b" / "manifest.json").read_text(encoding="utf-8"))
    assert a["documentos"]["sha256"] != b["documentos"]["sha256"]


def test_sem_weasyprint_falha_claro_e_nao_grava_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def indisponivel(html: str, destino: Path) -> None:
        raise faturas.WeasyPrintIndisponivelError("cannot load library 'libgobject-2.0-0'")

    monkeypatch.setattr(faturas, "_escrever_pdf", indisponivel)
    assert cli.main(["faturas", "--saida", str(tmp_path)]) == 1
    erro = capsys.readouterr().err
    assert "WeasyPrint indisponível" in erro and "docs/setup.md" in erro
    assert list(tmp_path.iterdir()) == []


def test_comando_desconhecido() -> None:
    with pytest.raises(SystemExit):
        cli.main(["nada"])


# ------------------------------------------------------------------- ctes


def test_ctes_gera_xml_dacte_e_manifest(tmp_path: Path) -> None:
    assert cli.main(["ctes", "--seed", "42", "--saida", str(tmp_path)]) == 0
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))

    xmls, dactes = manifest["xmls"], manifest["dactes"]
    assert len(xmls) == len(dactes) == 21
    assert manifest["documentos"]["por_tipo"] == {"cte": 21}
    ids = {x["id"] for x in xmls}
    for x in xmls:
        assert faturas.sha256_de(tmp_path / x["arquivo"]) == x["sha256"]
        assert x["arquivo"].endswith(".xml") and len(x["chave_acesso"]) == 44
    for d in dactes:  # o DACTE é só para exibir: fica fora do lote
        assert d["tipo"] == "dacte" and d["origem_xml"] in ids and d["incluir_no_lote"] is False
        assert d["arquivo"].endswith("_dacte.pdf")
        assert faturas.sha256_de(tmp_path / d["arquivo"]) == d["sha256"]

    docs = json.loads((tmp_path / "documentos.json").read_text(encoding="utf-8"))
    assert {d["tipo"] for d in docs} == {"cte"} and all(d["formato"] == "xml" for d in docs)
    assert all(d["sha256"] and d["chave_acesso"] for d in docs)


def test_ctes_e_idempotente_e_preserva_outras_chaves(tmp_path: Path) -> None:
    (tmp_path / "manifest.json").write_text('{"outra_etapa": 1}', encoding="utf-8")
    cli.main(["ctes", "--saida", str(tmp_path)])
    primeiro = (tmp_path / "manifest.json").read_bytes()
    assert json.loads(primeiro)["outra_etapa"] == 1
    cli.main(["ctes", "--saida", str(tmp_path)])
    assert (tmp_path / "manifest.json").read_bytes() == primeiro


def test_faturas_e_ctes_se_mesclam_em_qualquer_ordem(tmp_path: Path, com_pdf_falso: None) -> None:
    def tipos() -> dict[str, int]:
        manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
        return dict(manifest["documentos"]["por_tipo"])

    cli.main(["faturas", "--saida", str(tmp_path)])
    so_faturas = tipos()
    assert "cte" not in so_faturas
    cli.main(["ctes", "--saida", str(tmp_path)])
    assert tipos() == {**so_faturas, "cte": 21}
    cli.main(["faturas", "--saida", str(tmp_path)])  # refazer as faturas não apaga os CT-e
    assert tipos() == {**so_faturas, "cte": 21}
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["pdfs"]) == sum(so_faturas.values()) and len(manifest["xmls"]) == 21


# ------------------------------------------------------------------ ruido


def _lote_pequeno(raiz: Path) -> None:
    pdfs = []
    for i in range(8):
        arquivo = f"documentos/d{i}.pdf"
        (raiz / "documentos").mkdir(parents=True, exist_ok=True)
        with pymupdf.open() as doc:
            doc.new_page(width=595, height=842).insert_text((60, 80), f"Fatura {i}", fontsize=14)
            doc.save(raiz / arquivo)
        pdfs.append(
            {"arquivo": arquivo, "sha256": faturas.sha256_de(raiz / arquivo), "id": f"i{i}"}
        )
    (raiz / "manifest.json").write_text(json.dumps({"pdfs": pdfs}), encoding="utf-8")


def test_ruido_aplica_e_marca_no_manifest(tmp_path: Path) -> None:
    _lote_pequeno(tmp_path)
    assert cli.main(["ruido", "--seed", "42", "--saida", str(tmp_path)]) == 0
    pdfs = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["pdfs"]
    com_ruido = [p for p in pdfs if p.get("ruido")]
    assert len(com_ruido) == 1 and com_ruido[0]["foto_torta"] is True  # 15% de 8 → 1, e é a foto
    assert faturas.sha256_de(tmp_path / com_ruido[0]["arquivo"]) == com_ruido[0]["sha256"]


def test_ruido_sem_manifest_falha_claro(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["ruido", "--saida", str(tmp_path)]) == 1
    assert "rode `faturas` antes" in capsys.readouterr().err
