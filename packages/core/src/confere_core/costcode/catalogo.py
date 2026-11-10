"""Catálogo de códigos de custo (config/codigos_custo.yaml) com validação de consistência."""

import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Unidade = Literal["por_conteiner", "por_bl", "por_processo", "percentual", "por_dia", "por_kg"]

_PADRAO_CODIGO = r"^[A-Z][A-Z0-9]*(_[A-Z0-9]+)*$"


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento e com espaços colapsados."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento.casefold()).strip()


class CodigoCusto(BaseModel):
    model_config = ConfigDict(frozen=True)

    codigo: str = Field(pattern=_PADRAO_CODIGO)
    descricao: str = Field(min_length=1)
    grupo: str
    moeda_tipica: str = Field(pattern=r"^[A-Z]{3}$")
    unidade: Unidade
    sinonimos: tuple[str, ...] = ()


class Catalogo(BaseModel):
    model_config = ConfigDict(frozen=True)

    versao: int
    grupos: tuple[str, ...]
    itens: tuple[CodigoCusto, ...] = Field(alias="codigos")

    @model_validator(mode="after")
    def _validar(self) -> Self:
        repetidos = sorted({g for g in self.grupos if self.grupos.count(g) > 1})
        if repetidos:
            raise ValueError(f"grupos repetidos: {', '.join(repetidos)}")

        codigos = [i.codigo for i in self.itens]
        duplicados = sorted({c for c in codigos if codigos.count(c) > 1})
        if duplicados:
            raise ValueError(f"códigos repetidos: {', '.join(duplicados)}")

        invalidos = sorted(
            {f"{i.codigo} → {i.grupo}" for i in self.itens if i.grupo not in self.grupos}
        )
        if invalidos:
            raise ValueError(f"grupo inexistente: {', '.join(invalidos)}")

        donos: dict[str, set[str]] = defaultdict(set)
        for item in self.itens:
            for sinonimo in item.sinonimos:
                donos[normalizar(sinonimo)].add(item.codigo)
        conflitos = [
            f"'{sinonimo}' → {' e '.join(sorted(cods))}"
            for sinonimo, cods in sorted(donos.items())
            if len(cods) > 1
        ]
        if conflitos:
            raise ValueError("sinônimos apontam para mais de um código: " + "; ".join(conflitos))
        return self

    @classmethod
    def carregar(cls, path: str | Path) -> Self:
        with open(path, encoding="utf-8") as arquivo:
            return cls.model_validate(yaml.safe_load(arquivo))

    def codigos(self) -> list[str]:
        return [i.codigo for i in self.itens]

    def get(self, codigo: str) -> CodigoCusto:
        for item in self.itens:
            if item.codigo == codigo:
                return item
        raise KeyError(codigo)

    def sinonimos_globais(self) -> dict[str, str]:
        """Sinônimo normalizado (minúsculas, sem acento) → código."""
        return {normalizar(s): i.codigo for i in self.itens for s in i.sinonimos}
