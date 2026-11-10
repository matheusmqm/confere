"""ROUTE: documentos. Só HTTP; a lógica está em `controllers/documento.py`."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, UploadFile

from confere_api.controllers.documento import DetalheDocumento, DocumentoController
from confere_api.deps import DbDep, TenantDep, get_storage
from confere_api.erros import ArquivoGrande
from confere_api.schemas.comuns import FornecedorRef, ProcessoRef
from confere_api.schemas.documentos import (
    ArquivoSaida,
    CasamentoSaida,
    DecisaoPipeline,
    DocumentoDetalhe,
    EventoSaida,
    ExcecaoDoDocumento,
    ItemUpload,
    LinhaSaida,
    PaginaDocumentos,
    ProvisaoRef,
    UploadSaida,
    resumo_de_linha,
)
from confere_api.storage import Storage

router = APIRouter(prefix="/documentos", tags=["documentos"])
URL_VALIDADE_S = 300
MAX_ARQUIVOS = 50
MAX_BYTES = 15 * 1024 * 1024


def _montar_detalhe(d: DetalheDocumento) -> DocumentoDetalhe:
    doc = d.documento
    linhas = [
        LinhaSaida(
            id=item.linha.id,
            ordem=item.linha.ordem,
            descricao=item.linha.descricao,
            qtd=item.linha.qtd,
            valor_unit=item.linha.valor_unit,
            valor=item.linha.valor,
            moeda=item.linha.moeda,
            valor_brl=item.linha.valor_brl,
            processo=ProcessoRef(id=item.processo.id, codigo=item.processo.codigo)
            if item.processo
            else None,
            codigo_custo=item.linha.codigo_custo,
            conf_extracao=item.linha.conf_extracao,
            conf_processo=item.linha.conf_processo,
            conf_codigo=item.linha.conf_codigo,
            metodo_codigo=item.linha.metodo_codigo,
            estado=item.linha.estado,
            bbox=item.linha.bbox_json,
            casamento=CasamentoSaida(
                provisao=ProvisaoRef(
                    id=item.provisao.id,
                    codigo_custo=item.provisao.codigo_custo,
                    valor=item.provisao.valor,
                    moeda=item.provisao.moeda,
                ),
                diferenca=item.casamento.diferenca,
                diferenca_brl=item.casamento.diferenca_brl,
                ptax=item.casamento.ptax,
                ptax_data=item.casamento.ptax_data,
            )
            if item.casamento and item.provisao
            else None,
        )
        for item in d.linhas
    ]
    excecoes = [
        ExcecaoDoDocumento(
            id=e.id,
            tipo=e.tipo,
            severidade=e.severidade,
            linha_id=e.linha_id,
            valor_brl_em_risco=e.valor_brl_em_risco,
            explicacao=e.explicacao,
            explicacao_origem=e.explicacao_origem,
            acao_sugerida=e.acao_sugerida,
            status=e.status,
            dados=e.dados_json,
            criado_em=e.criado_em,
            resolvida_em=e.resolvida_em,
        )
        for e in d.excecoes
    ]
    eventos = [
        EventoSaida(
            id=e.id,
            etapa=e.etapa,
            status=e.status,
            mensagem=e.mensagem,
            dados=e.dados_json,
            criado_em=e.criado_em,
        )
        for e in d.eventos
    ]
    decidido = next((e for e in reversed(d.eventos) if e.etapa == "decidido"), None)
    motivos = (decidido.dados_json or {}).get("motivos") if decidido else None
    if not motivos:  # sem motivos gravados pela decisão: lista os tipos das exceções abertas
        motivos = sorted({e.tipo for e in d.excecoes if e.status == "aberta"})
    return DocumentoDetalhe(
        id=doc.id,
        nome_original=doc.nome_original,
        tipo=doc.tipo,
        tipo_arquivo=doc.tipo_arquivo,
        remetente=doc.remetente,
        fornecedor=FornecedorRef(id=d.fornecedor.id, nome=d.fornecedor.nome)
        if d.fornecedor
        else None,
        numero=doc.numero,
        emissao=doc.emissao,
        vencimento=doc.vencimento,
        moeda=doc.moeda,
        total=doc.total,
        status=doc.status,
        confianca=doc.confianca,
        em_lote_demo=doc.em_lote_demo,
        criado_em=doc.criado_em,
        avisos=list(doc.avisos or []),
        linhas=linhas,
        excecoes=excecoes,
        eventos=eventos,
        decisao=DecisaoPipeline(score=doc.score_decisao, tau=doc.tau, motivos=list(motivos)),
    )


@router.post("", response_model=UploadSaida, status_code=202)
def enviar_documentos(
    db: DbDep,
    tenant: TenantDep,
    storage: Annotated[Storage, Depends(get_storage)],
    arquivos: list[UploadFile],
    remetente: Annotated[str | None, Form()] = None,
) -> UploadSaida:
    """Recebe até 50 arquivos de 15 MB. Um arquivo ruim não derruba os outros."""
    if len(arquivos) > MAX_ARQUIVOS:
        raise ArquivoGrande(f"Envie no máximo {MAX_ARQUIVOS} arquivos por vez.")
    controller = DocumentoController(db, tenant)
    itens: list[ItemUpload] = []
    for arquivo in arquivos:
        nome = arquivo.filename or "arquivo"
        conteudo = arquivo.file.read(MAX_BYTES + 1)
        if len(conteudo) > MAX_BYTES:
            raise ArquivoGrande(f"'{nome}' passa do limite de 15 MB.")
        try:
            recebido = controller.receber(storage, nome, conteudo, remetente)
            db.commit()
            itens.append(
                ItemUpload(
                    id=recebido.documento.id,
                    nome=nome,
                    status=recebido.documento.status,
                    aviso=recebido.aviso,
                )
            )
        except Exception as erro:
            db.rollback()
            itens.append(
                ItemUpload(
                    id=None, nome=nome, status="erro", aviso=f"Falha ao receber: {erro}"[:200]
                )
            )
    return UploadSaida(documentos=itens)


@router.get("", response_model=PaginaDocumentos)
def listar_documentos(
    db: DbDep,
    tenant: TenantDep,
    status: str | None = None,
    fornecedor_id: uuid.UUID | None = None,
    processo_id: uuid.UUID | None = None,
    em_lote_demo: bool | None = None,
    limite: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: str | None = None,
) -> PaginaDocumentos:
    linhas, proximo = DocumentoController(db, tenant).listar(
        status=status,
        fornecedor_id=fornecedor_id,
        processo_id=processo_id,
        em_lote_demo=em_lote_demo,
        limite=limite,
        cursor=cursor,
    )
    return PaginaDocumentos(
        itens=[resumo_de_linha(linha) for linha in linhas], proximo_cursor=proximo
    )


@router.get("/{documento_id}", response_model=DocumentoDetalhe)
def obter_documento(documento_id: uuid.UUID, db: DbDep, tenant: TenantDep) -> DocumentoDetalhe:
    return _montar_detalhe(DocumentoController(db, tenant).detalhe(documento_id))


@router.get("/{documento_id}/arquivo", response_model=ArquivoSaida)
def obter_arquivo(
    documento_id: uuid.UUID,
    db: DbDep,
    tenant: TenantDep,
    storage: Annotated[Storage, Depends(get_storage)],
) -> ArquivoSaida:
    """URL assinada (300 s) do arquivo. No backend local aponta para `/arquivos-locais/...`."""
    caminho, tipo_arquivo = DocumentoController(db, tenant).caminho_do_arquivo(documento_id)
    return ArquivoSaida(url=storage.signed_url(caminho, URL_VALIDADE_S), tipo_arquivo=tipo_arquivo)
