"""ROUTE: reset e lote da demo. Registrada só com `DEMO_MODE=true`; senão o caminho dá 404."""

import time
from typing import Annotated

from fastapi import APIRouter, Depends

from confere_api.controllers.demo import DemoController
from confere_api.deps import DbDep, TenantDep, get_storage
from confere_api.erros import NaoImplementado
from confere_api.storage import Storage

router = APIRouter(prefix="/demo", tags=["demo"])


@router.post("/reset")
def resetar_demo(
    db: DbDep,
    tenant: TenantDep,
    storage: Annotated[Storage, Depends(get_storage)],
    limpar_arquivos: bool = False,
) -> dict[str, object]:
    """Apaga os dados transacionais da empresa demo. Os arquivos ficam (reuso por sha256)."""
    inicio = time.perf_counter()
    DemoController(db, tenant).resetar(storage, limpar_arquivos=limpar_arquivos)
    db.commit()
    return {"ok": True, "duracao_ms": round((time.perf_counter() - inicio) * 1000)}


@router.post("/lote", status_code=202)
def enviar_lote_demo() -> dict[str, object]:
    """Envia os 40 arquivos de `data/seed42/demo_lote.json` pelo caminho do upload.

    Depende da função de serviço do `POST /documentos` (CF-105) e do arquivo `demo_lote.json`
    (comando `lote-demo` do synth), que ainda não existem. Ver `docs/pendencias.md`.
    """
    raise NaoImplementado(
        "O lote de demo depende do upload de documentos (CF-105) e do demo_lote.json."
    )
