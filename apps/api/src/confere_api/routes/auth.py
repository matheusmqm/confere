"""ROUTE: login de demo (sem WorkOS). Sessão em cookie assinado (`sessao.py`)."""

from fastapi import APIRouter, Response

from confere_api.controllers.auth import AuthController, tenant_demo
from confere_api.deps import DbDep, TenantDep
from confere_api.erros import NaoEncontrado
from confere_api.schemas.auth import EmpresaSaida, EuSaida, UsuarioSaida
from confere_api.sessao import COOKIE_SESSAO, VALIDADE_S, criar_cookie
from confere_api.settings import get_settings
from confere_api.tenant import Tenant

router = APIRouter(prefix="/auth", tags=["auth"])


def _eu(db: DbDep, tenant: Tenant) -> EuSaida:
    usuario, empresa = AuthController(db, tenant).quem_sou_eu()
    return EuSaida(
        usuario=UsuarioSaida.model_validate(usuario), empresa=EmpresaSaida.model_validate(empresa)
    )


@router.post("/demo", response_model=EuSaida)
def entrar_na_demo(db: DbDep, resposta: Response) -> EuSaida:
    """Cria a sessão do usuário demo. Só existe com `DEMO_MODE=true` ou `ENV=local`."""
    settings = get_settings()
    if not (settings.demo_mode or settings.env == "local"):
        raise NaoEncontrado
    tenant = tenant_demo(db)
    resposta.set_cookie(
        COOKIE_SESSAO,
        criar_cookie(tenant, settings),
        max_age=VALIDADE_S,
        httponly=True,
        secure=settings.env == "demo",
        samesite="lax",
        path="/",
    )
    return _eu(db, tenant)


@router.get("/eu", response_model=EuSaida)
def quem_sou_eu(db: DbDep, tenant: TenantDep) -> EuSaida:
    return _eu(db, tenant)


@router.post("/sair", status_code=204)
def sair(resposta: Response) -> None:
    resposta.delete_cookie(COOKIE_SESSAO, path="/")
