"""Separação de um PDF com vários documentos em documentos-filhos (CF-46).

`separar` recebe os cortes (intervalos de páginas, 1-indexados e inclusivos, como saem do
classificador) e devolve um sub-PDF por corte, com tipo, intervalo e sha256 próprio.

TODO(CF-107): ligar ao worker (`confere_api/worker/etapas.py`, ainda inexistente). Quando a
classificação tiver mais de um corte (`deve_separar`), o worker deve: criar um documento-filho
por corte com `documento_pai_id`, enfileirar um job para cada filho e deixar o pai com status
`separado`; filhos `bl` e `aviso_chegada` não seguem o pipeline de cobrança (`arquivado`, ver
`status_inicial`). A coluna nullable `documento_pai_id` exige a tabela `documento`, que ainda não
existe nas migrações; crie a migração Alembic junto com ela.
"""

import hashlib
from itertools import pairwise
from typing import Literal

import pymupdf
from pydantic import BaseModel, Field

from confere_core.domain import ClassificacaoDocumento, CortePagina, TipoDocumento
from confere_core.ingest.render import DocumentoCorrompido, DocumentoProtegido

STATUS_PAI_SEPARADO = "separado"
STATUS_ARQUIVADO = "arquivado"
TIPOS_FORA_DO_PIPELINE_DE_COBRANCA: frozenset[TipoDocumento] = frozenset({"bl", "aviso_chegada"})


class CorteInvalido(ValueError):  # noqa: N818  (nome de domínio)
    """Os cortes não cabem no PDF, se sobrepõem ou estão vazios."""


class DocumentoFilho(BaseModel):
    conteudo: bytes = Field(repr=False)
    inicio: int
    fim: int
    tipo: TipoDocumento
    sha256: str


def deve_separar(classificacao: ClassificacaoDocumento) -> bool:
    """Mais de um corte → o arquivo contém mais de um documento."""
    return len(classificacao.paginas) > 1


def segue_pipeline_de_cobranca(tipo: TipoDocumento) -> bool:
    """BL e aviso de chegada são arquivados: não passam pela conferência de cobrança."""
    return tipo not in TIPOS_FORA_DO_PIPELINE_DE_COBRANCA


def status_inicial(tipo: TipoDocumento) -> Literal["recebido", "arquivado"]:
    return "recebido" if segue_pipeline_de_cobranca(tipo) else "arquivado"


def _validar(cortes: list[CortePagina], total: int) -> list[CortePagina]:
    if not cortes:
        raise CorteInvalido("nenhum corte informado")
    ordenados = sorted(cortes, key=lambda c: (c.inicio, c.fim))
    for c in ordenados:
        if c.fim > total:
            raise CorteInvalido(f"corte {c.inicio}-{c.fim} passa da última página ({total})")
    for a, b in pairwise(ordenados):
        if b.inicio <= a.fim:
            raise CorteInvalido(f"cortes {a.inicio}-{a.fim} e {b.inicio}-{b.fim} se sobrepõem")
    return ordenados


def separar(conteudo_pdf: bytes, cortes: list[CortePagina]) -> list[DocumentoFilho]:
    """Um sub-PDF por corte (na ordem das páginas), com o sha256 de cada um."""
    try:
        origem = pymupdf.open(stream=conteudo_pdf, filetype="pdf")
    except Exception as erro:
        raise DocumentoCorrompido(f"PDF não abre: {erro}") from erro
    with origem:
        if origem.needs_pass:
            raise DocumentoProtegido("PDF protegido por senha")
        filhos: list[DocumentoFilho] = []
        for corte in _validar(cortes, origem.page_count):
            with pymupdf.open() as destino:
                destino.insert_pdf(origem, from_page=corte.inicio - 1, to_page=corte.fim - 1)
                destino.set_metadata({})
                dados = bytes(destino.tobytes(garbage=3, deflate=True, no_new_id=True))
            filhos.append(
                DocumentoFilho(
                    conteudo=dados,
                    inicio=corte.inicio,
                    fim=corte.fim,
                    tipo=corte.tipo,
                    sha256=hashlib.sha256(dados).hexdigest(),
                )
            )
        return filhos
