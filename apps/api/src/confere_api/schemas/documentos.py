"""SCHEMAS: respostas das rotas de documentos (alimentam o OpenAPI e o cliente tipado do front)."""

import uuid
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel

from confere_api.schemas.comuns import (
    Confianca,
    DecimalTexto,
    Dinheiro,
    FornecedorRef,
    ProcessoRef,
)


class DocumentoResumo(BaseModel):
    id: uuid.UUID
    nome_original: str
    tipo: str
    fornecedor: FornecedorRef | None
    numero: str | None
    total: Dinheiro | None
    moeda: str | None
    status: str
    valor_brl_em_risco: Dinheiro
    n_excecoes: int
    processos: list[str]
    criado_em: datetime


class PaginaDocumentos(BaseModel):
    itens: list[DocumentoResumo]
    proximo_cursor: str | None


class ProvisaoRef(BaseModel):
    id: uuid.UUID
    codigo_custo: str
    valor: Dinheiro
    moeda: str


class CasamentoSaida(BaseModel):
    provisao: ProvisaoRef
    diferenca: Dinheiro
    diferenca_brl: Dinheiro
    ptax: DecimalTexto | None
    ptax_data: date | None


class LinhaSaida(BaseModel):
    id: uuid.UUID
    ordem: int
    descricao: str
    qtd: DecimalTexto | None
    valor_unit: DecimalTexto | None
    valor: Dinheiro
    moeda: str
    valor_brl: Dinheiro | None
    processo: ProcessoRef | None
    codigo_custo: str | None
    conf_extracao: Confianca | None
    conf_processo: Confianca | None
    conf_codigo: Confianca | None
    metodo_codigo: str | None
    estado: str
    bbox: dict[str, Any] | None
    casamento: CasamentoSaida | None


class ExcecaoDoDocumento(BaseModel):
    id: uuid.UUID
    tipo: str
    severidade: str
    linha_id: uuid.UUID | None
    valor_brl_em_risco: Dinheiro
    explicacao: str | None
    explicacao_origem: str | None
    acao_sugerida: str | None
    status: str
    dados: dict[str, Any] | None
    criado_em: datetime
    resolvida_em: datetime | None


class EventoSaida(BaseModel):
    id: int
    etapa: str
    status: str
    mensagem: str
    dados: dict[str, Any] | None
    criado_em: datetime


class DecisaoPipeline(BaseModel):
    score: Confianca | None
    tau: Confianca | None
    motivos: list[str]


class DocumentoDetalhe(BaseModel):
    id: uuid.UUID
    nome_original: str
    tipo: str
    tipo_arquivo: str | None
    remetente: str | None
    fornecedor: FornecedorRef | None
    numero: str | None
    emissao: date | None
    vencimento: date | None
    moeda: str | None
    total: Dinheiro | None
    status: str
    confianca: Confianca | None
    em_lote_demo: bool
    criado_em: datetime
    avisos: list[Any]
    linhas: list[LinhaSaida]
    excecoes: list[ExcecaoDoDocumento]
    eventos: list[EventoSaida]
    decisao: DecisaoPipeline


class ItemUpload(BaseModel):
    id: uuid.UUID | None
    nome: str
    status: str
    aviso: str | None


class UploadSaida(BaseModel):
    documentos: list[ItemUpload]


class ArquivoSaida(BaseModel):
    url: str
    tipo_arquivo: str | None


def resumo_de_linha(linha: Sequence[Any]) -> DocumentoResumo:
    """Resumo a partir de `(Documento, fornecedor_id, fornecedor_nome, n, risco, codigos)`."""
    doc, fornecedor_id, fornecedor_nome, n_excecoes, risco, codigos = linha
    return DocumentoResumo(
        id=doc.id,
        nome_original=doc.nome_original,
        tipo=doc.tipo,
        fornecedor=FornecedorRef(id=fornecedor_id, nome=fornecedor_nome) if fornecedor_id else None,
        numero=doc.numero,
        total=doc.total,
        moeda=doc.moeda,
        status=doc.status,
        valor_brl_em_risco=risco or 0,
        n_excecoes=n_excecoes or 0,
        processos=sorted(codigos or []),
        criado_em=doc.criado_em,
    )
