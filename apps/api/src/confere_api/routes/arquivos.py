"""ROUTE: serve arquivos do storage local por URL assinada (HMAC da CF-11).

Só existe para `STORAGE_BACKEND=local` (dev, testes e plano B offline). No Supabase a URL
assinada aponta direto para o Storage.
"""

import mimetypes
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from confere_api.deps import get_storage
from confere_api.erros import AcessoNegado, NaoEncontrado
from confere_api.settings import get_settings
from confere_api.storage import ROTA_LOCAL, Storage, segredo_local, verify_local_signature

router = APIRouter(prefix=ROTA_LOCAL, tags=["arquivos"])


@router.get("/{caminho:path}")
def arquivo_local(
    caminho: str,
    exp: Annotated[int, Query()],
    sig: Annotated[str, Query()],
    storage: Annotated[Storage, Depends(get_storage)],
) -> Response:
    settings = get_settings()
    if settings.storage_backend != "local":
        raise NaoEncontrado
    if not verify_local_signature(caminho, exp, sig, secret=segredo_local(settings)):
        raise AcessoNegado("Link do arquivo inválido ou expirado.")
    try:
        conteudo = storage.get(caminho)
    except FileNotFoundError as erro:
        raise NaoEncontrado from erro
    tipo, _ = mimetypes.guess_type(caminho)
    return Response(conteudo, media_type=tipo or "application/octet-stream")
