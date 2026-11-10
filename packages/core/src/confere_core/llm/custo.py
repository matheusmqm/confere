"""Custo estimado das chamadas ao LLM, a partir de `config/llm_precos.yaml`."""

from decimal import Decimal
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field

CAMINHO_PADRAO = Path(__file__).resolve().parents[5] / "config" / "llm_precos.yaml"
_MICRO = Decimal("0.000001")
_MILHAO = Decimal(1_000_000)


class ModeloSemPrecoError(KeyError):
    """O modelo não está na tabela e não há preço `padrao`."""


class PrecoModelo(BaseModel):
    model_config = ConfigDict(frozen=True)

    entrada_usd_por_milhao: Decimal = Field(ge=0)
    saida_usd_por_milhao: Decimal = Field(ge=0)


class TabelaPrecos(BaseModel):
    model_config = ConfigDict(frozen=True)

    moeda: str = "USD"
    modelos: dict[str, PrecoModelo]
    padrao: PrecoModelo | None = None

    @classmethod
    def carregar(cls, path: str | Path = CAMINHO_PADRAO) -> Self:
        with open(path, encoding="utf-8") as arquivo:
            return cls.model_validate(yaml.safe_load(arquivo))

    def preco(self, modelo: str) -> PrecoModelo:
        if modelo in self.modelos:
            return self.modelos[modelo]
        if self.padrao is not None:
            return self.padrao
        raise ModeloSemPrecoError(modelo)


def calcular_custo_usd(
    precos: TabelaPrecos, modelo: str, tokens_in: int, tokens_out: int
) -> Decimal:
    """(tokens_in x preço de entrada + tokens_out x preço de saída) / 1 milhão, em USD."""
    p = precos.preco(modelo)
    total = (tokens_in * p.entrada_usd_por_milhao + tokens_out * p.saida_usd_por_milhao) / _MILHAO
    return total.quantize(_MICRO)
