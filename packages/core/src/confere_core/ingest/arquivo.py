"""Inspeção do arquivo recebido (CF-42): tipo por assinatura (nunca pelo nome), sha256 e problemas.

Funções puras, sem dependência da API. O PDF é aberto só para checar senha e integridade; nenhum
JavaScript do PDF é executado.
"""

import hashlib
from typing import Literal

import pymupdf
from pydantic import BaseModel

TipoArquivo = Literal["pdf", "png", "jpg", "xml"]
Problema = Literal["tipo_nao_suportado", "muito_grande", "vazio", "pdf_protegido", "pdf_corrompido"]

LIMITE_BYTES = 15 * 1024 * 1024
LIMITE_PAGINAS = 50
_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"
_BOM_UTF8 = b"\xef\xbb\xbf"


class ArquivoInspecionado(BaseModel):
    nome: str
    tipo: TipoArquivo | None
    tamanho: int
    sha256: str
    problema: Problema | None = None


def _parece_xml(conteudo: bytes) -> bool:
    inicio = conteudo.removeprefix(_BOM_UTF8).lstrip()
    if not inicio.startswith(b"<"):
        return False
    if not inicio.startswith(b"<?xml") and not (len(inicio) > 1 and chr(inicio[1]).isalpha()):
        return False
    try:
        conteudo.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def detectar_tipo(conteudo: bytes) -> TipoArquivo | None:
    """Tipo pela assinatura do conteúdo, ignorando nome e extensão."""
    if b"%PDF-" in conteudo[:1024]:
        return "pdf"
    if conteudo.startswith(_PNG):
        return "png"
    if conteudo.startswith(_JPEG):
        return "jpg"
    if _parece_xml(conteudo):
        return "xml"
    return None


def sha256_hex(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _problema_do_pdf(conteudo: bytes) -> Problema | None:
    try:
        documento = pymupdf.open(stream=conteudo, filetype="pdf")
    except Exception:
        return "pdf_corrompido"
    try:
        if documento.needs_pass:
            return "pdf_protegido"
        if documento.page_count > LIMITE_PAGINAS:
            return "muito_grande"
        return None
    except Exception:
        return "pdf_corrompido"
    finally:
        documento.close()


def inspecionar(
    nome: str, conteudo: bytes, limite_bytes: int = LIMITE_BYTES
) -> ArquivoInspecionado:
    tipo = detectar_tipo(conteudo)
    problema: Problema | None = None
    if not conteudo:
        problema = "vazio"
    elif len(conteudo) > limite_bytes:
        problema = "muito_grande"
    elif tipo is None:
        problema = "tipo_nao_suportado"
    elif tipo == "pdf":
        problema = _problema_do_pdf(conteudo)
    return ArquivoInspecionado(
        nome=nome,
        tipo=tipo,
        tamanho=len(conteudo),
        sha256=sha256_hex(conteudo),
        problema=problema,
    )


def caminho_storage(empresa_id: object, sha256: str, tipo: TipoArquivo) -> str:
    """Caminho lógico no storage: `<empresa_id>/<sha256>.<ext>` (o prefixo é do backend)."""
    return f"{empresa_id}/{sha256}.{tipo}"
