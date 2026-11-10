"""Sessão assinada do login de demo (CF-117): cookie `confere_sessao` com `itsdangerous`.

O cookie guarda `{usuario_id, empresa_id, papel}`, assinado com `SESSION_SECRET` e válido por 12 h.

Same-site: o front (Vercel) chama a API por um rewrite do Next.js (`/api/*` → API), então o
navegador vê um só domínio e o cookie pode ser `SameSite=Lax` (mais seguro). Só use
`SameSite=None; Secure` se o front falar direto com a API em outro domínio.
"""

import uuid

from itsdangerous import BadSignature, URLSafeTimedSerializer

from confere_api.settings import SEGREDO_SESSAO_PADRAO, Settings, get_settings
from confere_api.tenant import Tenant

COOKIE_SESSAO = "confere_sessao"
VALIDADE_S = 12 * 3600
_SAL = "confere-sessao-v1"


def _serializador(settings: Settings) -> URLSafeTimedSerializer:
    segredo = settings.session_secret.get_secret_value() or SEGREDO_SESSAO_PADRAO
    return URLSafeTimedSerializer(segredo, salt=_SAL)


def criar_cookie(tenant: Tenant, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    conteudo = {
        "usuario_id": str(tenant.usuario_id),
        "empresa_id": str(tenant.empresa_id),
        "papel": tenant.papel,
    }
    return _serializador(settings).dumps(conteudo)


def ler_cookie(valor: str | None, settings: Settings | None = None) -> Tenant | None:
    """Tenant da sessão, ou None se o cookie faltar, estiver adulterado ou tiver expirado."""
    if not valor:
        return None
    settings = settings or get_settings()
    try:
        dados = _serializador(settings).loads(valor, max_age=VALIDADE_S)
        return Tenant(
            empresa_id=uuid.UUID(dados["empresa_id"]),
            usuario_id=uuid.UUID(dados["usuario_id"]),
            papel=str(dados["papel"]),
        )
    except (BadSignature, KeyError, ValueError, TypeError):
        return None
