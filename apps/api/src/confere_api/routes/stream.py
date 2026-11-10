"""ROUTE: SSE com os eventos do pipeline da empresa (CF-108).

Autenticação pelo cookie de sessão (o EventSource não manda headers customizados). Cada consulta
abre e fecha a sua própria sessão de banco: a conexão não fica presa durante a espera.
"""

import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

import anyio
from fastapi import APIRouter, Header, Query, Request
from sse_starlette import EventSourceResponse, ServerSentEvent
from starlette.concurrency import run_in_threadpool

from confere_api.controllers.evento import EventoController
from confere_api.db.session import SessionLocal, get_engine
from confere_api.deps import TenantDep
from confere_api.tenant import Tenant

router = APIRouter(tags=["stream"])

INTERVALO_S = 0.25
PING_S = 15
RECONEXAO_MS = 2000


def _novos(tenant: Tenant, ultimo: int | None) -> tuple[int, list[dict[str, Any]]]:
    """(último id visto, eventos depois dele). Com `ultimo=None`, só devolve o id atual."""
    with SessionLocal(bind=get_engine()) as db:
        controller = EventoController(db, tenant)
        if ultimo is None:
            return controller.ultimo_id(), []
        eventos = controller.depois_de(ultimo)
        carga: list[dict[str, Any]] = [
            {
                "id": e.id,
                "documento_id": str(e.documento_id) if e.documento_id else None,
                "etapa": e.etapa,
                "status": e.status,
                "mensagem": e.mensagem,
                "dados": e.dados_json,
                "criado_em": e.criado_em.isoformat(),
            }
            for e in eventos
        ]
        return (int(carga[-1]["id"]) if carga else ultimo), carga


def _ping() -> ServerSentEvent:
    return ServerSentEvent(data="", event="ping")


@router.get("/stream")
async def stream(
    request: Request,
    tenant: TenantDep,
    desde: Annotated[int | None, Query(ge=0)] = None,
    last_event_id: Annotated[int | None, Header(ge=0)] = None,
) -> EventSourceResponse:
    """Eventos do pipeline: `id > desde` (ou `Last-Event-ID`); sem nenhum, só os novos."""
    inicio = desde if desde is not None else last_event_id

    async def eventos() -> AsyncIterator[ServerSentEvent]:
        # 1ª mensagem: manda o `retry` (o navegador reconecta em 2 s).
        yield ServerSentEvent(data="conectado", event="ping", retry=RECONEXAO_MS)
        if inicio is None:
            ultimo, _ = await run_in_threadpool(_novos, tenant, None)
        else:
            ultimo = inicio
        while not await request.is_disconnected():
            ultimo, carga = await run_in_threadpool(_novos, tenant, ultimo)
            for evento in carga:
                yield ServerSentEvent(
                    data=json.dumps(
                        {k: v for k, v in evento.items() if k != "id"}, ensure_ascii=False
                    ),
                    event="pipeline",
                    id=str(evento["id"]),
                )
            await anyio.sleep(INTERVALO_S)

    return EventSourceResponse(eventos(), ping=PING_S, ping_message_factory=_ping)
