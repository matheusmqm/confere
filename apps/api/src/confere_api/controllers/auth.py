"""CONTROLLER: login de demo e dados do usuário logado."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from confere_api.controllers.base import RepositorioBase
from confere_api.erros import ErroNegocio, NaoEncontrado
from confere_api.models.empresa import Empresa, Usuario
from confere_api.tenant import Tenant

EMAIL_USUARIO_DEMO = "demo@confere.example"


class DemoIndisponivel(ErroNegocio):
    codigo = "demo_indisponivel"
    status_http = 503
    mensagem_padrao = "A empresa de demonstração ainda não foi carregada. Rode o seed da demo."


def tenant_demo(db: Session) -> Tenant:
    """Tenant do usuário demo. Sem filtro de empresa: é a porta de entrada, antes do tenant."""
    usuario = db.scalars(select(Usuario).where(Usuario.email == EMAIL_USUARIO_DEMO)).first()
    if usuario is None:
        raise DemoIndisponivel
    return Tenant(usuario.empresa_id, usuario.id, usuario.papel)


class AuthController(RepositorioBase):
    def quem_sou_eu(self) -> tuple[Usuario, Empresa]:
        if self.tenant.usuario_id is None:
            raise NaoEncontrado("Usuário não identificado.")
        usuario = self.obter(Usuario, self.tenant.usuario_id)
        empresa = self.db.get(Empresa, self.tenant.empresa_id)  # a empresa É o tenant
        if empresa is None:
            raise NaoEncontrado
        return usuario, empresa
