"""Modelos do mundo sintético. Todos os dados são fictícios; dinheiro é sempre `Decimal`."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

TipoFornecedor = Literal[
    "armador", "agente_exterior", "terminal", "armazem", "transportadora", "despachante"
]
TipoReferencia = Literal["bl_master", "bl_house", "conteiner", "ref_cliente", "ref_agente"]
Modal = Literal["maritimo", "aereo", "rodoviario"]
StatusProvisao = Literal["aberta", "casada", "parcial", "cancelada"]
TipoDocumento = Literal["fatura", "nota_debito", "extrato", "cte", "bl", "aviso_chegada", "outro"]
TipoErro = Literal[
    "valor_acima",
    "duplicada",
    "taxa_nao_prevista",
    "cambio_errado",
    "referencia_cruzada",
    "ruido_visual",
]

PADRAO_MOEDA = r"^[A-Z]{3}$"
PADRAO_SLUG = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class _Modelo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Fornecedor(_Modelo):
    id: str = Field(pattern=PADRAO_SLUG)
    nome: str = Field(min_length=1)
    tipo: TipoFornecedor
    pais: str = Field(pattern=r"^[A-Z]{2}$")
    idioma: Literal["pt", "en"]
    moeda_padrao: str = Field(pattern=PADRAO_MOEDA)
    dominio_email: str  # sempre *.example (RFC 2606): garante ficção
    estilo_id: int = Field(ge=1, le=6)
    aliases: list[str]  # como o nome aparece nas faturas
    nomes_taxa: dict[str, list[str]]  # codigo_custo → variações do nome neste fornecedor
    codigos: list[str]  # codigos de custo que ele cobra
    cnpj_ficticio: str | None = None  # só fornecedores nacionais

    @model_validator(mode="after")
    def _validar(self) -> Self:
        if not self.dominio_email.endswith(".example"):
            raise ValueError(f"dominio_email deve terminar em .example: {self.dominio_email!r}")
        fora = sorted(set(self.nomes_taxa) - set(self.codigos))
        if fora:
            raise ValueError(f"nomes_taxa com código que o fornecedor não cobra: {fora}")
        return self


class Cliente(_Modelo):
    id: str = Field(pattern=PADRAO_SLUG)
    nome: str
    cnpj_ficticio: str


class Referencia(_Modelo):
    tipo: TipoReferencia
    valor: str


class Processo(_Modelo):
    id: uuid.UUID
    codigo: str  # ex. IMP-2026-0142
    cliente_id: str
    modal: Modal
    origem: str  # nome do porto, ex. Shanghai
    origem_locode: str = Field(pattern=r"^[A-Z]{5}$")
    destino: str
    destino_locode: str = Field(pattern=r"^[A-Z]{5}$")
    navio: str | None = None  # None nos processos só rodoviários
    viagem: str | None = None
    etd: date
    eta: date
    armador_id: str | None = None
    agente_exterior_id: str | None = None
    terminal_id: str | None = None
    armazem_id: str | None = None
    despachante_id: str
    transportadora_id: str | None = None  # presente quando há trecho rodoviário (CT-e)
    referencias: list[Referencia] = Field(default_factory=list)


class Provisao(_Modelo):
    id: str
    processo_id: str
    fornecedor_id: str
    codigo_custo: str
    moeda: str = Field(pattern=PADRAO_MOEDA)
    valor: Decimal
    status: StatusProvisao = "aberta"


class LinhaSintetica(_Modelo):
    descricao: str
    quantidade: Decimal = Decimal(1)
    valor_unit: Decimal
    valor: Decimal
    moeda: str = Field(pattern=PADRAO_MOEDA)
    codigo_custo: str  # gabarito: o código correto desta cobrança
    provisao_id: str | None = None  # gabarito: provisão a que a linha corresponde
    referencias: list[Referencia] = Field(default_factory=list)


class ErroInjetado(_Modelo):
    tipo: TipoErro
    documento_id: str
    linha_indice: int | None = None
    detalhe: str = ""
    impacto_brl: Decimal | None = None


class DocumentoSintetico(_Modelo):
    id: str
    tipo: TipoDocumento
    fornecedor_id: str
    processo_id: str | None = None
    numero: str
    emissao: date
    vencimento: date | None = None
    moeda: str = Field(pattern=PADRAO_MOEDA)
    linhas: list[LinhaSintetica] = Field(default_factory=list)
    total: Decimal
    formato: Literal["pdf", "xml"] = "pdf"
    estilo_id: int = Field(ge=1, le=6)
    erros: list[ErroInjetado] = Field(default_factory=list)
    arquivo: str | None = None


class Mundo(_Modelo):
    seed: int
    fornecedores: list[Fornecedor]
    clientes: list[Cliente]
    processos: list[Processo]
    provisoes: list[Provisao] = Field(default_factory=list)
