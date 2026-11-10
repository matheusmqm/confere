"""Renderização das faturas sintéticas: contexto tipado, filtros de formatação e Jinja2.

O contexto é o mesmo para os 6 estilos (`ContextoRender`). Os templates ficam em
`templates/estilo_{1..6}.html.j2`, estendem `_base.html.j2` (A4, margem 14 mm, sem recursos
externos) e trazem "SINTÉTICO — dados fictícios" no rodapé de toda página.
"""

import random
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from functools import lru_cache
from typing import Literal

from jinja2 import Environment, PackageLoader, StrictUndefined
from pydantic import BaseModel, ConfigDict, Field, field_validator

from confere_synth.mundo import FAIXA_CLIENTES, gerar_cnpj_ficticio

ESTILOS = (1, 2, 3, 4, 5, 6)
_MESES_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
LINHAS_POR_PAGINA_EXTRATO = 25


class _Modelo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DocInfo(_Modelo):
    numero: str
    emissao: date
    vencimento: date | None = None
    moeda: str = Field(pattern=r"^[A-Z]{3}$")
    total: Decimal
    observacoes: str = ""


class FornecedorInfo(_Modelo):
    nome: str
    endereco: str  # fictício
    cnpj: str | None = None  # fictício, só nacionais
    email: str

    @field_validator("email")
    @classmethod
    def _dominio_example(cls, email: str) -> str:
        if not email.endswith(".example"):
            raise ValueError(f"e-mail deve terminar em .example: {email!r}")
        return email


class TomadorInfo(_Modelo):
    nome: str
    endereco: str
    cnpj: str | None = None


class ProcessoRefs(_Modelo):
    """O que o fornecedor costuma citar do processo."""

    bl_master: str | None = None
    bl_house: list[str] = Field(default_factory=list)
    conteineres: list[str] = Field(default_factory=list)
    navio: str | None = None
    viagem: str | None = None
    ref_cliente: str | None = None
    ref_agente: str | None = None


class LinhaRender(_Modelo):
    descricao: str
    qtd: Decimal = Decimal(1)
    valor_unit: Decimal
    valor: Decimal
    moeda: str = Field(pattern=r"^[A-Z]{3}$")
    codigo: str | None = None  # código interno do fornecedor (estilo 3)
    refs_linha: list[str] = Field(default_factory=list)  # ex. contêiner da linha
    secao: Literal["reembolso", "honorario"] | None = None  # estilo 5
    periodo: tuple[date, date] | None = None  # estilo 4: entrada e saída
    base_cif: Decimal | None = None  # estilo 4
    percentual: Decimal | None = None  # estilo 4
    fatura_no: str | None = None  # estilo 6 (extrato)
    bl: str | None = None  # estilo 6
    container: str | None = None  # estilo 6
    cambio: str | None = None  # ex. "USD 1.800,00 x taxa 5,6120 = R$ 10.101,60" (estilo 3)


class ContextoRender(_Modelo):
    doc: DocInfo
    fornecedor: FornecedorInfo
    tomador: TomadorInfo
    processo_refs: ProcessoRefs = Field(default_factory=ProcessoRefs)
    linhas: list[LinhaRender]


TOMADOR_PADRAO = TomadorInfo(
    nome="Agência Demo Cargas Ltda. (fictícia)",
    endereco="Rua Fictícia, 100, Fortaleza/CE (endereço fictício)",
    cnpj=gerar_cnpj_ficticio(random.Random(0), FAIXA_CLIENTES),
)


# ------------------------------------------------------------------ filtros


def _formatar(valor: Decimal | int, casas: int, milhar: str, decimal: str) -> str:
    quantizado = Decimal(valor).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_EVEN)
    texto = f"{quantizado:,.{casas}f}"  # 1,234.56
    return texto.replace(",", "\0").replace(".", decimal).replace("\0", milhar)


def num_pt(valor: Decimal | int, casas: int = 2) -> str:
    """1234.5 → 1.234,50"""
    return _formatar(valor, casas, ".", ",")


def num_en(valor: Decimal | int, casas: int = 2) -> str:
    """1234.5 → 1,234.50"""
    return _formatar(valor, casas, ",", ".")


def _qtd(valor: Decimal, milhar: str, decimal: str) -> str:
    if valor == valor.to_integral_value():
        return _formatar(valor, 0, milhar, decimal)
    return _formatar(valor, 4, milhar, decimal).rstrip("0").rstrip(decimal)


def qtd_pt(valor: Decimal) -> str:
    return _qtd(valor, ".", ",")


def qtd_en(valor: Decimal) -> str:
    return _qtd(valor, ",", ".")


def dinheiro_pt(valor: Decimal | int, moeda: str) -> str:
    """R$ 12.345,67 / USD 380,00"""
    return f"{'R$' if moeda == 'BRL' else moeda} {num_pt(valor)}"


def dinheiro_en(valor: Decimal | int, moeda: str) -> str:
    """USD 12,345.67"""
    return f"{moeda} {num_en(valor)}"


def data_pt(d: date) -> str:
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def data_en(d: date) -> str:
    return f"{d.day:02d} {_MESES_EN[d.month - 1]} {d.year}"


@lru_cache(maxsize=1)
def ambiente() -> Environment:
    env = Environment(
        loader=PackageLoader("confere_synth", "templates"),
        autoescape=True,
        undefined=StrictUndefined,  # erro claro em vez de campo vazio silencioso
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(
        num_pt=num_pt,
        num_en=num_en,
        qtd_pt=qtd_pt,
        qtd_en=qtd_en,
        dinheiro_pt=dinheiro_pt,
        dinheiro_en=dinheiro_en,
        data_pt=data_pt,
        data_en=data_en,
    )
    env.globals["linhas_por_pagina"] = LINHAS_POR_PAGINA_EXTRATO
    return env


def renderizar_html(estilo_id: int, contexto: ContextoRender) -> str:
    if estilo_id not in ESTILOS:
        raise ValueError(f"estilo_id deve estar entre 1 e 6: {estilo_id}")
    return (
        ambiente()
        .get_template(f"estilo_{estilo_id}.html.j2")
        .render(
            doc=contexto.doc,
            fornecedor=contexto.fornecedor,
            tomador=contexto.tomador,
            processo_refs=contexto.processo_refs,
            linhas=contexto.linhas,
        )
    )
