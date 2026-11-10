"""SCHEMAS comuns: tipos numéricos serializados sem perder precisão.

No JSON, dinheiro e taxas saem como **string decimal** (`"1495.20"`), para o front não passar por
`float`. Datas saem em ISO 8601 (padrão do Pydantic).
"""

import uuid
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Annotated

from pydantic import BaseModel, PlainSerializer


def _dinheiro(valor: Decimal) -> str:
    return format(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN), "f")


def _decimal_texto(valor: Decimal) -> str:
    return format(valor, "f")


Dinheiro = Annotated[Decimal, PlainSerializer(_dinheiro, return_type=str, when_used="json")]
"""Valor em moeda, 2 casas (ROUND_HALF_EVEN só na saída)."""

DecimalTexto = Annotated[
    Decimal, PlainSerializer(_decimal_texto, return_type=str, when_used="json")
]
"""Taxa de câmbio, quantidade e valor unitário: todas as casas, como texto."""

Confianca = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]
"""Confiança/score de 0 a 1 (não é dinheiro: sai como número JSON)."""


class FornecedorRef(BaseModel):
    id: uuid.UUID
    nome: str


class ProcessoRef(BaseModel):
    id: uuid.UUID
    codigo: str
