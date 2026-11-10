"""Dependências FastAPI: sessão, tenant e storage.

Identidade (`get_tenant`): vem do cookie de sessão assinado do login de demo (`sessao.py`).
Sem cookie válido, em `ENV in {local, test}` vale o header `X-Empresa-Id` (e, opcionalmente,
`X-Usuario-Id` e `X-Papel`), só para desenvolvimento e testes. **Em `ENV=demo` esses headers são
ignorados**: sem cookie válido a resposta é 401 `{"erro": "nao_autenticado"}`.
"""

import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from confere_api.db.session import get_db
from confere_api.erros import NaoAutenticado
from confere_api.sessao import COOKIE_SESSAO, ler_cookie
from confere_api.settings import get_settings
from confere_api.storage import get_storage
from confere_api.tenant import Tenant

PAPEIS_VALIDOS = {"ap", "operacional", "gestor"}

__all__ = ["DbDep", "Tenant", "TenantDep", "get_db", "get_storage", "get_tenant"]


def _uuid_ou_none(texto: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(texto) if texto else None
    except ValueError:
        return None


def get_tenant(
    request: Request,
    x_empresa_id: Annotated[str | None, Header()] = None,
    x_usuario_id: Annotated[str | None, Header()] = None,
    x_papel: Annotated[str | None, Header()] = None,
) -> Tenant:
    tenant = ler_cookie(request.cookies.get(COOKIE_SESSAO))
    if tenant is not None:
        return tenant
    if get_settings().env in {"local", "test"}:
        empresa_id = _uuid_ou_none(x_empresa_id)
        if empresa_id is not None:
            papel = x_papel if x_papel in PAPEIS_VALIDOS else "gestor"
            return Tenant(empresa_id, _uuid_ou_none(x_usuario_id), papel)
    raise NaoAutenticado


DbDep = Annotated[Session, Depends(get_db)]
TenantDep = Annotated[Tenant, Depends(get_tenant)]
