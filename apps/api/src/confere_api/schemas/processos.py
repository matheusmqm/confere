"""SCHEMAS: processos, previsto x cobrado e provisões."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from confere_api.schemas.comuns import Dinheiro, FornecedorRef

Moeda = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
EstadoItem = Literal["ok", "acima", "abaixo", "sem_fatura", "sem_provisao"]


class ProcessoResumo(BaseModel):
    id: uuid.UUID
    codigo: str
    cliente: str
    origem: str
    destino: str
    navio: str | None
    viagem: str | None
    eta: date | None
    status: str
    n_documentos: int
    total_previsto_brl: Dinheiro
    total_cobrado_brl: Dinheiro
    n_excecoes_abertas: int
    cotacao_incompleta: bool


class ItemPrevistoCobrado(BaseModel):
    fornecedor: FornecedorRef
    codigo_custo: str
    previsto_moeda: str | None
    previsto_valor: Dinheiro | None
    previsto_brl: Dinheiro | None
    cobrado_moeda: str | None
    cobrado_valor: Dinheiro | None
    cobrado_brl: Dinheiro | None
    diferenca_brl: Dinheiro | None
    estado: EstadoItem
    documento_ids: list[uuid.UUID]
    linha_ids: list[uuid.UUID]


class TotaisProcesso(BaseModel):
    previsto_brl: Dinheiro
    cobrado_brl: Dinheiro
    diferenca_brl: Dinheiro
    saldo_a_repassar_brl: Dinheiro
    cotacao_incompleta: bool


class ProcessoDetalhe(BaseModel):
    id: uuid.UUID
    codigo: str
    cliente: str
    modal: str
    origem: str
    destino: str
    navio: str | None
    viagem: str | None
    etd: date | None
    eta: date | None
    status: str
    conteineres: list[str]
    bls: list[str]
    referencias_cliente: list[str]
    itens: list[ItemPrevistoCobrado]
    totais: TotaisProcesso


class ProvisaoEntrada(BaseModel):
    fornecedor_id: uuid.UUID
    codigo_custo: Annotated[str, StringConstraints(min_length=1, max_length=40)]
    moeda: Moeda
    valor: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)]


class ProvisaoEdicao(BaseModel):
    valor: Annotated[Decimal, Field(gt=0, max_digits=14, decimal_places=2)] | None = None
    moeda: Moeda | None = None
    codigo_custo: Annotated[str, StringConstraints(min_length=1, max_length=40)] | None = None
    status: Literal["aberta", "cancelada"] | None = None


class ProvisaoSaida(BaseModel):
    id: uuid.UUID
    processo_id: uuid.UUID
    fornecedor: FornecedorRef
    codigo_custo: str
    moeda: str
    valor: Dinheiro
    status: str
    documentos_reprocessados: int = 0
