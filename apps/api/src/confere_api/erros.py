"""Exceções de negócio. Os controllers levantam estas; `main.py` as traduz para HTTP."""


class ErroNegocio(Exception):  # noqa: N818
    codigo = "erro_negocio"
    status_http = 400
    mensagem_padrao = "Não foi possível concluir a operação."

    def __init__(self, mensagem: str | None = None) -> None:
        self.mensagem = mensagem or self.mensagem_padrao
        super().__init__(self.mensagem)


class NaoEncontrado(ErroNegocio):
    """404 também para recurso de outra empresa: não vazamos a existência."""

    codigo = "nao_encontrado"
    status_http = 404
    mensagem_padrao = "Registro não encontrado."


class NaoAutenticado(ErroNegocio):
    codigo = "nao_autenticado"
    status_http = 401
    mensagem_padrao = "Faça login para continuar."


class AcessoNegado(ErroNegocio):
    codigo = "acesso_negado"
    status_http = 403
    mensagem_padrao = "Você não tem acesso a este recurso."


class NaoImplementado(ErroNegocio):
    codigo = "nao_implementado"
    status_http = 501
    mensagem_padrao = "Funcionalidade ainda não disponível."


class Conflito(ErroNegocio):
    codigo = "conflito"
    status_http = 409
    mensagem_padrao = "A operação conflita com o estado atual do registro."


class ArquivoGrande(ErroNegocio):
    codigo = "arquivo_grande"
    status_http = 413
    mensagem_padrao = "Arquivo acima do limite permitido."
