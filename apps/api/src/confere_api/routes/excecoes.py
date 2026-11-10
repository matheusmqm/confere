"""ROUTE: exceções e decisões humanas. Só HTTP; a lógica está em `controllers/excecao.py`."""

import uuid
from collections.abc import Sequence
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query

from confere_api.controllers.documento import DocumentoController
from confere_api.controllers.excecao import ExcecaoController
from confere_api.deps import DbDep, TenantDep
from confere_api.schemas.documentos import resumo_de_linha
from confere_api.schemas.excecoes import (
    DecisaoEntrada,
    DecisaoSaida,
    DocumentoDaExcecao,
    ExcecaoItem,
    FornecedorNome,
    LinhaDaExcecao,
    ListaExcecoesSaida,
    ProcessoCodigo,
)

router = APIRouter(prefix="/excecoes", tags=["excecoes"])


def _item(linha: Sequence[Any]) -> ExcecaoItem:
    excecao, documento, fornecedor_nome, processo_codigo, ln = linha
    return ExcecaoItem(
        id=excecao.id,
        tipo=excecao.tipo,
        severidade=excecao.severidade,
        status=excecao.status,
        documento=DocumentoDaExcecao(
            id=documento.id, numero=documento.numero, nome=documento.nome_original
        ),
        fornecedor=FornecedorNome(id=documento.fornecedor_id, nome=fornecedor_nome)
        if fornecedor_nome and documento.fornecedor_id
        else None,
        processo=ProcessoCodigo(codigo=processo_codigo) if processo_codigo else None,
        linha=LinhaDaExcecao(id=ln.id, descricao=ln.descricao, valor=ln.valor, moeda=ln.moeda)
        if ln
        else None,
        valor_brl_em_risco=excecao.valor_brl_em_risco,
        explicacao=excecao.explicacao,
        acao_sugerida=excecao.acao_sugerida,
        criado_em=excecao.criado_em,
    )


@router.get("", response_model=ListaExcecoesSaida)
def listar_excecoes(
    db: DbDep,
    tenant: TenantDep,
    tipo: str | None = None,
    status: str | None = "aberta",
    fornecedor_id: uuid.UUID | None = None,
    ordenar: Literal["risco", "recentes"] = "risco",
    limite: Annotated[int, Query(ge=1, le=500)] = 200,
) -> ListaExcecoesSaida:
    lista = ExcecaoController(db, tenant).listar(
        tipo=tipo, status=status, fornecedor_id=fornecedor_id, ordenar=ordenar, limite=limite
    )
    return ListaExcecoesSaida(itens=[_item(i) for i in lista.itens], facetas=lista.facetas)


@router.post("/{excecao_id}/decisao", response_model=DecisaoSaida)
def decidir_excecao(
    excecao_id: uuid.UUID, corpo: DecisaoEntrada, db: DbDep, tenant: TenantDep
) -> DecisaoSaida:
    controller = ExcecaoController(db, tenant)
    documento = controller.decidir(
        excecao_id,
        corpo.acao,
        comentario=corpo.comentario,
        processo_id=corpo.processo_id,
        codigo_custo=corpo.codigo_custo,
        linha_id=corpo.linha_id,
    )
    db.commit()
    return DecisaoSaida(
        excecao=_item(controller.item(excecao_id)),
        documento=resumo_de_linha(DocumentoController(db, tenant).resumo(documento.id)),
    )
