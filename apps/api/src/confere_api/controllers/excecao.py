"""CONTROLLER: exceções (fila de revisão) e decisões humanas (CF-111)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Row, Select, func

from confere_api.controllers.base import RepositorioBase
from confere_api.controllers.evento import EventoController
from confere_api.erros import Conflito, ErroNegocio, NaoAutenticado, NaoEncontrado, NaoImplementado
from confere_api.models.documento import Documento, Linha
from confere_api.models.excecao import Decisao, Excecao
from confere_api.models.fornecedor import Fornecedor
from confere_api.models.processo import Processo
from confere_api.models.provisao import Provisao

SEVERIDADES_QUE_BLOQUEIAM_APROVACAO = ("revisar", "bloquear")


class DecisaoInvalida(ErroNegocio):
    codigo = "decisao_invalida"
    status_http = 422
    mensagem_padrao = "Decisão inválida para esta exceção."


@dataclass
class ListaExcecoes:
    itens: list[Row[Any]]
    facetas: dict[str, int]


class ExcecaoController(RepositorioBase):
    def _consulta_itens(self) -> Select[Any]:
        """Exceção + `(Documento, fornecedor_nome, processo_codigo, Linha)`."""
        processo_da_excecao = func.coalesce(Linha.processo_id, Provisao.processo_id)
        return (
            self._q(Excecao)
            .add_columns(Documento, Fornecedor.nome, Processo.codigo, Linha)
            .join(Documento, Documento.id == Excecao.documento_id)
            .outerjoin(Fornecedor, Fornecedor.id == Documento.fornecedor_id)
            .outerjoin(Linha, Linha.id == Excecao.linha_id)
            .outerjoin(Provisao, Provisao.id == Excecao.provisao_id)
            .outerjoin(Processo, Processo.id == processo_da_excecao)
        )

    def listar(
        self,
        *,
        tipo: str | None = None,
        status: str | None = "aberta",
        fornecedor_id: uuid.UUID | None = None,
        ordenar: str = "risco",
        limite: int = 200,
    ) -> ListaExcecoes:
        consulta = self._consulta_itens()
        contagem = (
            self._q(Excecao)
            .with_only_columns(Excecao.tipo, func.count())
            .select_from(Excecao)
            .join(Documento, Documento.id == Excecao.documento_id)
            .group_by(Excecao.tipo)
        )
        if status:
            consulta = consulta.where(Excecao.status == status)
            contagem = contagem.where(Excecao.status == status)
        if fornecedor_id:
            consulta = consulta.where(Documento.fornecedor_id == fornecedor_id)
            contagem = contagem.where(Documento.fornecedor_id == fornecedor_id)
        if tipo:  # as facetas ignoram o filtro de tipo (são os chips para escolher o tipo)
            consulta = consulta.where(Excecao.tipo == tipo)
        if ordenar == "recentes":
            consulta = consulta.order_by(Excecao.criado_em.desc())
        else:
            consulta = consulta.order_by(Excecao.valor_brl_em_risco.desc(), Excecao.criado_em)
        itens = list(self.db.execute(consulta.limit(limite)))
        facetas = {tipo_: n for tipo_, n in self.db.execute(contagem)}
        return ListaExcecoes(itens, facetas)

    def item(self, excecao_id: uuid.UUID) -> Row[Any]:
        linha = self.db.execute(self._consulta_itens().where(Excecao.id == excecao_id)).first()
        if linha is None:
            raise NaoEncontrado
        return linha

    def decidir(
        self,
        excecao_id: uuid.UUID,
        acao: str,
        *,
        comentario: str | None = None,
        processo_id: uuid.UUID | None = None,
        codigo_custo: str | None = None,
        linha_id: uuid.UUID | None = None,
    ) -> Documento:
        """Registra a decisão humana, resolve a exceção e atualiza o documento. Devolve-o."""
        if acao in ("corrigir_codigo", "corrigir_processo"):
            tarefa = "CF-93" if acao == "corrigir_codigo" else "CF-94"
            raise NaoImplementado(f"A ação {acao!r} depende da {tarefa}, ainda não disponível.")
        if self.tenant.usuario_id is None:
            raise NaoAutenticado("Identifique o usuário para registrar a decisão.")
        excecao = self.obter(Excecao, excecao_id)
        if excecao.status != "aberta":
            raise Conflito("Esta exceção já foi resolvida.")
        documento = self.obter(Documento, excecao.documento_id)

        dados: dict[str, Any] = {}
        if acao == "repassar":
            alvo = linha_id or excecao.linha_id
            if alvo is None:
                raise DecisaoInvalida("Repassar exige uma linha (informe `linha_id`).")
            dados["linha_id"] = str(self.obter(Linha, alvo).id)  # entra no saldo da CF-110
            dados["repassar"] = True
        if acao == "contestar":
            dados["contestado"] = True
        for nome, valor in (("processo_id", processo_id), ("codigo_custo", codigo_custo)):
            if valor is not None:
                dados[nome] = str(valor)

        self.adicionar(
            Decisao(
                excecao_id=excecao.id,
                documento_id=documento.id,
                usuario_id=self.tenant.usuario_id,
                acao=acao,
                comentario=comentario,
                dados_json=dados or None,
            )
        )
        excecao.status = "resolvida"
        excecao.resolvida_em = datetime.now(UTC)
        if acao == "contestar":
            excecao.dados_json = {**(excecao.dados_json or {}), "contestado": True}
            documento.status = "em_revisao"
        elif acao == "bloquear":
            documento.status = "bloqueado"
        elif acao == "aprovar":
            self.db.flush()
            if self._restantes(documento.id) == 0:
                documento.status = "aprovado_manual"

        EventoController(self.db, self.tenant).registrar(
            "decidido",
            "ok",
            f"Decisão humana: {acao}.",
            documento_id=documento.id,
            dados={"acao": acao, "excecao_id": str(excecao.id), "status_final": documento.status},
        )
        self.db.flush()
        return documento

    def _restantes(self, documento_id: uuid.UUID) -> int:
        """Exceções abertas de severidade ≥ revisar que ainda sobram no documento."""
        return int(
            self.db.scalar(
                self._q(Excecao)
                .with_only_columns(func.count())
                .where(
                    Excecao.documento_id == documento_id,
                    Excecao.status == "aberta",
                    Excecao.severidade.in_(SEVERIDADES_QUE_BLOQUEIAM_APROVACAO),
                )
            )
            or 0
        )
