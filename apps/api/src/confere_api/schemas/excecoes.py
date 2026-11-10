"""SCHEMAS: exceções e decisões humanas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from confere_api.schemas.comuns import Dinheiro
from confere_api.schemas.documentos import DocumentoResumo

AcaoDecisao = Literal[
    "aprovar", "contestar", "corrigir_processo", "corrigir_codigo", "repassar", "bloquear"
]


class DocumentoDaExcecao(BaseModel):
    id: uuid.UUID
    numero: str | None
    nome: str


class FornecedorNome(BaseModel):
    id: uuid.UUID
    nome: str


class ProcessoCodigo(BaseModel):
    codigo: str


class LinhaDaExcecao(BaseModel):
    id: uuid.UUID
    descricao: str
    valor: Dinheiro
    moeda: str


class ExcecaoItem(BaseModel):
    id: uuid.UUID
    tipo: str
    severidade: str
    status: str
    documento: DocumentoDaExcecao
    fornecedor: FornecedorNome | None
    processo: ProcessoCodigo | None
    linha: LinhaDaExcecao | None
    valor_brl_em_risco: Dinheiro
    explicacao: str | None
    acao_sugerida: str | None
    criado_em: datetime


class ListaExcecoesSaida(BaseModel):
    itens: list[ExcecaoItem]
    facetas: dict[str, int]  # contagem por tipo, para os chips da UI


class DecisaoEntrada(BaseModel):
    acao: AcaoDecisao
    comentario: str | None = None
    processo_id: uuid.UUID | None = None
    codigo_custo: str | None = None
    linha_id: uuid.UUID | None = None


class DecisaoSaida(BaseModel):
    excecao: ExcecaoItem
    documento: DocumentoResumo
