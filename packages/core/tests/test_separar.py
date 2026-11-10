"""separar: sub-PDFs por corte, hashes, validação dos cortes e regras de status."""

import hashlib

import pymupdf
import pytest

from confere_core.domain import ClassificacaoDocumento, CortePagina
from confere_core.ingest.render import DocumentoCorrompido, DocumentoProtegido
from confere_core.ingest.separar import (
    CorteInvalido,
    deve_separar,
    segue_pipeline_de_cobranca,
    separar,
    status_inicial,
)


def pdf(n: int) -> bytes:
    with pymupdf.open() as doc:
        for i in range(1, n + 1):
            doc.new_page(width=595, height=842).insert_text((50, 100), f"PAGINA-{i}", fontsize=14)
        return bytes(doc.tobytes())


def textos(conteudo: bytes) -> list[str]:
    with pymupdf.open(stream=conteudo, filetype="pdf") as doc:
        return [p.get_text().strip() for p in doc]


def corte(inicio: int, fim: int, tipo: str = "fatura") -> CortePagina:
    return CortePagina(inicio=inicio, fim=fim, tipo=tipo)


def test_fatura_mais_bl_em_dois_filhos() -> None:
    filhos = separar(pdf(3), [corte(1, 2), corte(3, 3, "bl")])
    assert [(f.inicio, f.fim, f.tipo) for f in filhos] == [(1, 2, "fatura"), (3, 3, "bl")]
    assert textos(filhos[0].conteudo) == ["PAGINA-1", "PAGINA-2"]
    assert textos(filhos[1].conteudo) == ["PAGINA-3"]


def test_cada_filho_tem_o_sha256_do_proprio_conteudo() -> None:
    filhos = separar(pdf(4), [corte(1, 1), corte(2, 4, "extrato")])
    for f in filhos:
        assert f.sha256 == hashlib.sha256(f.conteudo).hexdigest()
    assert filhos[0].sha256 != filhos[1].sha256


def test_tres_cortes_cobrindo_o_arquivo() -> None:
    filhos = separar(pdf(5), [corte(1, 2), corte(3, 3, "bl"), corte(4, 5, "nota_debito")])
    assert [textos(f.conteudo) for f in filhos] == [
        ["PAGINA-1", "PAGINA-2"], ["PAGINA-3"], ["PAGINA-4", "PAGINA-5"],
    ]  # fmt: skip


def test_cortes_fora_de_ordem_saem_na_ordem_das_paginas() -> None:
    filhos = separar(pdf(3), [corte(3, 3, "bl"), corte(1, 2)])
    assert [f.inicio for f in filhos] == [1, 3]


def test_corte_unico_do_arquivo_inteiro_e_um_corte_parcial() -> None:
    (inteiro,) = separar(pdf(3), [corte(1, 3)])
    assert textos(inteiro.conteudo) == ["PAGINA-1", "PAGINA-2", "PAGINA-3"]
    (so_a_do_meio,) = separar(pdf(3), [corte(2, 2, "aviso_chegada")])
    assert textos(so_a_do_meio.conteudo) == ["PAGINA-2"] and so_a_do_meio.tipo == "aviso_chegada"


def test_separar_e_reproduzivel() -> None:
    cortes = [corte(1, 2), corte(3, 3, "bl")]
    a, b = separar(pdf(3), cortes), separar(pdf(3), cortes)
    assert [f.sha256 for f in a] == [f.sha256 for f in b]


def test_conteudo_fica_fora_do_repr() -> None:
    (f,) = separar(pdf(1), [corte(1, 1)])
    assert "conteudo=" not in repr(f) and "sha256=" in repr(f)


@pytest.mark.parametrize(
    ("cortes", "mensagem"),
    [
        ([], "nenhum corte"),
        ([corte(1, 4)], "passa da última página"),
        ([corte(4, 4)], "passa da última página"),
        ([corte(1, 2), corte(2, 3)], "se sobrepõem"),
        ([corte(1, 3), corte(2, 2)], "se sobrepõem"),
    ],
)
def test_cortes_invalidos(cortes: list[CortePagina], mensagem: str) -> None:
    with pytest.raises(CorteInvalido, match=mensagem):
        separar(pdf(3), cortes)


def test_buraco_entre_cortes_e_permitido() -> None:
    filhos = separar(pdf(4), [corte(1, 1), corte(4, 4, "bl")])  # páginas 2-3 ficam de fora
    assert [textos(f.conteudo) for f in filhos] == [["PAGINA-1"], ["PAGINA-4"]]


def test_pdf_corrompido_e_protegido() -> None:
    with pytest.raises(DocumentoCorrompido):
        separar(b"lixo", [corte(1, 1)])
    with pymupdf.open() as doc:
        doc.new_page()
        protegido = bytes(
            doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="a", owner_pw="b")
        )
    with pytest.raises(DocumentoProtegido):
        separar(protegido, [corte(1, 1)])


# ------------------------------------------------------------- regras de status


def test_so_separa_com_mais_de_um_corte() -> None:
    um = ClassificacaoDocumento(tipo="fatura", confianca=1, metodo="llm", paginas=[corte(1, 3)])
    dois = ClassificacaoDocumento(
        tipo="fatura", confianca=1, metodo="llm", paginas=[corte(1, 2), corte(3, 3, "bl")]
    )
    sem = ClassificacaoDocumento(tipo="cte", confianca=1, metodo="regra")
    assert (deve_separar(um), deve_separar(dois), deve_separar(sem)) == (False, True, False)


@pytest.mark.parametrize(
    ("tipo", "segue", "status"),
    [
        ("fatura", True, "recebido"), ("nota_debito", True, "recebido"),
        ("extrato", True, "recebido"), ("cte", True, "recebido"), ("outro", True, "recebido"),
        ("bl", False, "arquivado"), ("aviso_chegada", False, "arquivado"),
    ],
)  # fmt: skip
def test_bl_e_aviso_de_chegada_sao_arquivados(tipo: str, segue: bool, status: str) -> None:
    assert segue_pipeline_de_cobranca(tipo) is segue  # type: ignore[arg-type]
    assert status_inicial(tipo) == status  # type: ignore[arg-type]
