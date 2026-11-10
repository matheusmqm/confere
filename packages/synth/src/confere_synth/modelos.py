"""Modelos do mundo sintético. Todos os dados são fictícios; dinheiro é sempre `Decimal`."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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
    id: uuid.UUID
    processo_id: uuid.UUID
    fornecedor_id: str
    codigo_custo: str
    moeda: str = Field(pattern=PADRAO_MOEDA)
    valor: Decimal = Field(gt=0)
    status: StatusProvisao = "aberta"


class Emitente(_Modelo):
    """Dados do fornecedor impressos no documento (tudo fictício)."""

    nome: str
    endereco: str
    cnpj: str | None = None
    email: str

    @field_validator("email")
    @classmethod
    def _dominio_example(cls, email: str) -> str:
        if not email.endswith(".example"):
            raise ValueError(f"e-mail deve terminar em .example: {email!r}")
        return email


class LinhaSintetica(_Modelo):
    descricao: str
    quantidade: Decimal = Decimal(1)
    valor_unit: Decimal
    valor: Decimal
    moeda: str = Field(pattern=PADRAO_MOEDA)
    # gabarito: a que processo, provisão e código de custo a cobrança corresponde
    codigo_custo: str
    processo_id: uuid.UUID | None = None
    provisao_id: uuid.UUID | None = None
    referencias: list[Referencia] = Field(default_factory=list)  # referências desta linha
    # campos que só alguns estilos de fatura imprimem
    codigo_fornecedor: str | None = None  # código interno do fornecedor (estilo 3)
    secao: Literal["reembolso", "honorario"] | None = None  # estilo 5
    periodo: tuple[date, date] | None = None  # estilo 4: entrada e saída
    base_cif: Decimal | None = None  # estilo 4
    percentual: Decimal | None = None  # estilo 4
    fatura_no: str | None = None  # estilo 6 (extrato): fatura a que a linha pertence
    # fatura em BRL de valor previsto em moeda estrangeira (fornecedor nacional que converte)
    moeda_origem: str | None = None
    valor_origem: Decimal | None = None
    taxa_cambio: Decimal | None = None  # BRL por unidade de `moeda_origem`, 4 casas
    informativa: bool = False  # linha sem cobrança (ex. "Taxa de câmbio aplicada"), valor 0
    bl: str | None = None  # estilo 6
    container: str | None = None  # estilo 6


class ErroInjetado(_Modelo):
    """Um erro injetado (CF-36). `linha_ordem` é 1-indexado; None = erro do documento todo."""

    doc_id: uuid.UUID
    linha_ordem: int | None = None
    tipo: TipoErro
    valor_erro_moeda: Decimal | None = None  # None quando o erro não tem valor (referência cruzada)
    moeda: str = Field(pattern=PADRAO_MOEDA)
    valor_erro_brl: Decimal | None = None  # None sem PTAX disponível (ex. CNY, data sem cotação)
    descricao: str


class DocumentoSintetico(_Modelo):
    id: uuid.UUID
    tipo: TipoDocumento
    fornecedor_id: str
    emitente: Emitente
    processo_id: uuid.UUID | None = None  # None quando junta mais de um processo
    numero: str
    emissao: date
    vencimento: date | None = None
    moeda: str = Field(pattern=PADRAO_MOEDA)
    linhas: list[LinhaSintetica] = Field(default_factory=list)
    total: Decimal
    formato: Literal["pdf", "xml"] = "pdf"
    estilo_id: int = Field(ge=1, le=6)
    erros: list[ErroInjetado] = Field(default_factory=list)
    arquivo: str | None = None  # relativo à pasta de saída, ex. documentos/<id>.pdf
    sha256: str | None = None  # do arquivo renderizado
    chave_acesso: str | None = None  # CT-e: chave de 44 dígitos
    duplicata_de: uuid.UUID | None = None  # id do documento original (erro "duplicada")
    duplicata_identica: bool = False  # True: o PDF é cópia byte a byte do original
    ruido: bool = False  # True se `arquivo` é a versão "foto de celular" (CF-37)
    arquivo_original: str | None = None  # a versão limpa, quando há ruído
    # o que o fornecedor cita do processo (documentos de um processo só)
    referencias: list[Referencia] = Field(default_factory=list)
    navio: str | None = None
    viagem: str | None = None
    observacoes: str = ""


class Mundo(_Modelo):
    seed: int
    fornecedores: list[Fornecedor]
    clientes: list[Cliente]
    processos: list[Processo]
    provisoes: list[Provisao] = Field(default_factory=list)
