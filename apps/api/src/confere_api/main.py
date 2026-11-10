"""App FastAPI do Confere: registra os routers e traduz erros para JSON em pt-BR."""

from importlib.metadata import PackageNotFoundError, version

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from confere_api.db.session import get_engine
from confere_api.erros import ErroNegocio
from confere_api.routes import (
    arquivos,
    auth,
    demo,
    documentos,
    excecoes,
    painel,
    processos,
    stream,
)
from confere_api.settings import get_settings

log = structlog.get_logger()
ORIGENS_LOCAIS = ["http://localhost:3000", "http://127.0.0.1:3000"]
REGEX_VERCEL = r"https://.*\.vercel\.app"


def _versao() -> str:
    try:
        return version("confere-api")
    except PackageNotFoundError:
        return "0.0.0"


def _erro(status: int, codigo: str, mensagem: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"erro": codigo, "mensagem": mensagem})


def criar_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Confere API", version=_versao())
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[*ORIGENS_LOCAIS, settings.next_public_api_url],
        allow_origin_regex=REGEX_VERCEL,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ErroNegocio)
    async def _negocio(_: Request, erro: ErroNegocio) -> JSONResponse:
        return _erro(erro.status_http, erro.codigo, erro.mensagem)

    @app.exception_handler(RequestValidationError)
    async def _validacao(_: Request, erro: RequestValidationError) -> JSONResponse:
        campos = ", ".join(".".join(str(p) for p in e["loc"][1:]) or "corpo" for e in erro.errors())
        return _erro(422, "requisicao_invalida", f"Dados inválidos na requisição: {campos}.")

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, erro: StarletteHTTPException) -> JSONResponse:
        mensagens = {404: "Recurso não encontrado.", 405: "Método não permitido."}
        return _erro(
            erro.status_code,
            "nao_encontrado" if erro.status_code == 404 else "erro_http",
            mensagens.get(erro.status_code, "Não foi possível atender a requisição."),
        )

    @app.exception_handler(Exception)
    async def _inesperado(request: Request, erro: Exception) -> JSONResponse:
        log.error("erro_inesperado", caminho=request.url.path, erro=repr(erro), exc_info=erro)
        return _erro(500, "erro_interno", "Erro inesperado. Tente novamente em instantes.")

    @app.get("/health", tags=["sistema"])
    def health() -> dict[str, object]:
        try:
            with get_engine().connect() as conexao:
                conexao.execute(text("select 1"))
            banco = True
        except Exception:
            banco = False
        return {"status": "ok", "versao": _versao(), "db": banco}

    for router in (
        auth.router,
        documentos.router,
        processos.router,
        excecoes.router,
        painel.router,
        stream.router,
        arquivos.router,
    ):
        app.include_router(router)
    if settings.demo_mode:  # fora da demo, /demo/* nem existe (404)
        app.include_router(demo.router)
    return app


app = criar_app()
