"""ROUTE: processos e provisões. Só HTTP; a lógica está nos controllers."""

import uuid

from fastapi import APIRouter

from confere_api.controllers.processo import ProcessoController
from confere_api.controllers.provisao import ProvisaoComFornecedor, ProvisaoController
from confere_api.deps import DbDep, TenantDep
from confere_api.schemas.comuns import FornecedorRef
from confere_api.schemas.processos import (
    ItemPrevistoCobrado,
    ProcessoDetalhe,
    ProcessoResumo,
    ProvisaoEdicao,
    ProvisaoEntrada,
    ProvisaoSaida,
    TotaisProcesso,
)

router = APIRouter(tags=["processos"])


def _provisao_saida(r: ProvisaoComFornecedor) -> ProvisaoSaida:
    p = r.provisao
    return ProvisaoSaida(
        id=p.id,
        processo_id=p.processo_id,
        fornecedor=FornecedorRef(id=r.fornecedor.id, nome=r.fornecedor.nome),
        codigo_custo=p.codigo_custo,
        moeda=p.moeda,
        valor=p.valor,
        status=p.status,
        documentos_reprocessados=r.documentos_reprocessados,
    )


@router.get("/processos", response_model=list[ProcessoResumo])
def listar_processos(
    db: DbDep, tenant: TenantDep, busca: str | None = None, status: str | None = None
) -> list[ProcessoResumo]:
    return [
        ProcessoResumo(
            id=r.processo.id,
            codigo=r.processo.codigo,
            cliente=r.processo.cliente,
            origem=r.processo.origem,
            destino=r.processo.destino,
            navio=r.processo.navio,
            viagem=r.processo.viagem,
            eta=r.processo.eta,
            status=r.processo.status,
            n_documentos=r.n_documentos,
            total_previsto_brl=r.previsto_brl,
            total_cobrado_brl=r.cobrado_brl,
            n_excecoes_abertas=r.n_excecoes_abertas,
            cotacao_incompleta=r.cotacao_incompleta,
        )
        for r in ProcessoController(db, tenant).listar(busca, status)
    ]


@router.get("/processos/{processo_id}", response_model=ProcessoDetalhe)
def obter_processo(processo_id: uuid.UUID, db: DbDep, tenant: TenantDep) -> ProcessoDetalhe:
    d = ProcessoController(db, tenant).detalhe(processo_id)
    p = d.processo

    def valores(*tipos: str) -> list[str]:
        return [r.valor for r in d.referencias if r.tipo in tipos]

    return ProcessoDetalhe(
        id=p.id,
        codigo=p.codigo,
        cliente=p.cliente,
        modal=p.modal,
        origem=p.origem,
        destino=p.destino,
        navio=p.navio,
        viagem=p.viagem,
        etd=p.etd,
        eta=p.eta,
        status=p.status,
        conteineres=valores("conteiner"),
        bls=valores("bl_master", "bl_house"),
        referencias_cliente=valores("ref_cliente"),
        itens=[
            ItemPrevistoCobrado(
                fornecedor=FornecedorRef(id=i.fornecedor_id, nome=i.fornecedor_nome),
                codigo_custo=i.codigo_custo,
                previsto_moeda=i.previsto_moeda,
                previsto_valor=i.previsto_valor,
                previsto_brl=i.previsto_brl,
                cobrado_moeda=i.cobrado_moeda,
                cobrado_valor=i.cobrado_valor,
                cobrado_brl=i.cobrado_brl,
                diferenca_brl=i.diferenca_brl,
                estado=i.estado,
                documento_ids=i.documento_ids,
                linha_ids=i.linha_ids,
            )
            for i in d.itens
        ],
        totais=TotaisProcesso(
            previsto_brl=d.previsto_brl,
            cobrado_brl=d.cobrado_brl,
            diferenca_brl=d.diferenca_brl,
            saldo_a_repassar_brl=d.saldo_a_repassar_brl,
            cotacao_incompleta=d.cotacao_incompleta,
        ),
    )


@router.post("/processos/{processo_id}/provisoes", response_model=ProvisaoSaida, status_code=201)
def criar_provisao(
    processo_id: uuid.UUID, corpo: ProvisaoEntrada, db: DbDep, tenant: TenantDep
) -> ProvisaoSaida:
    resultado = ProvisaoController(db, tenant).criar(
        processo_id,
        fornecedor_id=corpo.fornecedor_id,
        codigo_custo=corpo.codigo_custo,
        moeda=corpo.moeda,
        valor=corpo.valor,
    )
    db.commit()
    return _provisao_saida(resultado)


@router.patch("/provisoes/{provisao_id}", response_model=ProvisaoSaida)
def editar_provisao(
    provisao_id: uuid.UUID, corpo: ProvisaoEdicao, db: DbDep, tenant: TenantDep
) -> ProvisaoSaida:
    resultado = ProvisaoController(db, tenant).editar(
        provisao_id,
        valor=corpo.valor,
        moeda=corpo.moeda,
        codigo_custo=corpo.codigo_custo,
        status=corpo.status,
    )
    db.commit()
    return _provisao_saida(resultado)
