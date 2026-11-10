"""E1: ingestão e classificação de documentos."""

from typing import Literal

from confere_core.domain import ClassificacaoDocumento
from confere_core.ingest.classificar_pdf import PAGINAS_COMO_TEXTO, classificar_pdf
from confere_core.ingest.classificar_xml import classificar_xml
from confere_core.ingest.render import contar_paginas, renderizar
from confere_core.llm.client import LLMClient

TipoArquivo = Literal["pdf", "png", "jpg", "xml"]


def classificar(
    conteudo: bytes,
    tipo_arquivo: TipoArquivo,
    llm: LLMClient,
    remetente: str | None = None,
) -> ClassificacaoDocumento:
    """XML → regra por namespace (CF-43); PDF e imagem → classificador com LLM (CF-45).

    Para PDF só as primeiras páginas são renderizadas; o total de páginas vem de uma contagem
    barata, usada para validar os cortes devolvidos pelo LLM.
    """
    if tipo_arquivo == "xml":
        return classificar_xml(conteudo)
    if tipo_arquivo in ("pdf", "png", "jpg"):
        total = contar_paginas(conteudo, tipo_arquivo)
        paginas = renderizar(conteudo, tipo_arquivo, max_paginas=PAGINAS_COMO_TEXTO)
        return classificar_pdf(paginas, llm, remetente, total_paginas=total)
    raise ValueError(f"tipo de arquivo não suportado: {tipo_arquivo!r}")
