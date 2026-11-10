"""Custos típicos fictícios por código de custo (config/custos_tipicos.yaml)."""

from decimal import Decimal
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from confere_core.costcode.catalogo import Catalogo, Unidade
from confere_synth.modelos import TipoFornecedor

CAMINHO_PADRAO = Path(__file__).resolve().parents[4] / "config" / "custos_tipicos.yaml"


class CustoTipico(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    tipo_fornecedor: tuple[TipoFornecedor, ...] = Field(min_length=1)
    moeda: str = Field(pattern=r"^[A-Z]{3}$")
    base: Decimal = Field(gt=0)  # valor unitário, ou percentual quando há `percentual_de`
    unidade: Unidade
    ruido_rel: float = Field(ge=0, le=1)
    prob: float = Field(ge=0, le=1)
    percentual_de: str | None = None  # "cif" ou outro código de custo
    minimo: Decimal | None = Field(default=None, gt=0)
    dias: tuple[int, int] | None = None  # só para por_dia sem percentual

    @model_validator(mode="after")
    def _coerencia(self) -> Self:
        if self.unidade == "percentual" and self.percentual_de is None:
            raise ValueError("unidade percentual exige percentual_de")
        sem_dias = self.dias is None or not 1 <= self.dias[0] <= self.dias[1]
        if self.unidade == "por_dia" and self.percentual_de is None and sem_dias:
            raise ValueError("por_dia sem percentual exige dias: [min, max] com 1 <= min <= max")
        if self.minimo is not None and self.percentual_de is None:
            raise ValueError("minimo só vale com percentual_de")
        return self


class CustosTipicos(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    versao: int
    cambio_referencia: dict[str, Decimal]  # BRL por unidade de moeda; só para bases percentuais
    cif_por_conteiner_brl: tuple[Decimal, Decimal]
    codigos: dict[str, CustoTipico]

    @classmethod
    def carregar(cls, path: str | Path, catalogo: Catalogo) -> Self:
        with open(path, encoding="utf-8") as arquivo:
            custos = cls.model_validate(yaml.safe_load(arquivo))
        custos.validar(catalogo)
        return custos

    def validar(self, catalogo: Catalogo) -> None:
        """Confere a configuração contra o catálogo; erra listando todos os problemas."""
        problemas: list[str] = []
        esperados = set(catalogo.codigos())
        atuais = set(self.codigos)
        if atuais - esperados:
            problemas.append(f"códigos fora do catálogo: {sorted(atuais - esperados)}")
        if esperados - atuais:
            problemas.append(f"códigos do catálogo sem custo típico: {sorted(esperados - atuais)}")
        if "BRL" not in self.cambio_referencia:
            problemas.append("cambio_referencia deve incluir BRL")
        if self.cif_por_conteiner_brl[0] > self.cif_por_conteiner_brl[1]:
            problemas.append("cif_por_conteiner_brl deve ser [min, max]")
        for codigo, custo in self.codigos.items():
            if codigo not in esperados:
                continue
            if custo.unidade != catalogo.get(codigo).unidade:
                problemas.append(
                    f"{codigo}: unidade {custo.unidade} difere do catálogo "
                    f"({catalogo.get(codigo).unidade})"
                )
            if custo.moeda not in self.cambio_referencia:
                problemas.append(f"{codigo}: moeda {custo.moeda} sem cambio_referencia")
            ref = custo.percentual_de
            if ref is not None and ref != "cif" and ref not in esperados:
                problemas.append(f"{codigo}: percentual_de aponta para código inexistente: {ref}")
            if ref is not None and ref != "cif" and self.codigos.get(ref, custo).percentual_de:
                problemas.append(f"{codigo}: percentual_de não pode apontar para outro percentual")
            base = self.codigos.get(ref) if ref not in (None, "cif") else None
            if base is not None and base.prob < 1.0:
                problemas.append(f"{codigo}: código-base {ref} precisa de prob 1.0")
        if problemas:
            raise ValueError("custos_tipicos.yaml inválido: " + "; ".join(problemas))
