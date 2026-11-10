"""Modelos Pydantic de domínio (funções puras do core recebem e devolvem estes tipos)."""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

TipoDocumento = Literal["fatura", "nota_debito", "extrato", "cte", "bl", "aviso_chegada", "outro"]
MetodoClassificacao = Literal["regra", "llm"]
OrigemExtracao = Literal["llm", "cte_xml"]


class CortePagina(BaseModel):
    """Intervalo de páginas (1-indexado, inclusivo) de um documento dentro de um arquivo."""

    model_config = ConfigDict(frozen=True)

    inicio: int = Field(ge=1)
    fim: int = Field(ge=1)
    tipo: TipoDocumento

    @model_validator(mode="after")
    def _intervalo(self) -> Self:
        if self.fim < self.inicio:
            raise ValueError(f"fim ({self.fim}) antes do início ({self.inicio})")
        return self


class ClassificacaoDocumento(BaseModel):
    """Resultado da classificação (E1): o que o arquivo é e como foi decidido."""

    tipo: TipoDocumento
    confianca: float = Field(ge=0, le=1)
    metodo: MetodoClassificacao
    fornecedor_provavel: str | None = None
    paginas: list[CortePagina] = Field(default_factory=list)
    motivo: str | None = None  # por que ficou "outro" (ex. nfe_nao_suportada)


# ------------------------------------------------------------------- extração (E2)
# As descrições dos campos vão para o LLM (via schema), então dizem o que cada um significa.


class BBox(BaseModel):
    """Caixa de um trecho na página, normalizada (independe de dpi)."""

    pagina: int = Field(ge=1, description="Número da página, começando em 1.")
    x0: float = Field(ge=0, le=1, description="Borda esquerda, de 0 (esquerda) a 1 (direita).")
    y0: float = Field(ge=0, le=1, description="Borda superior, de 0 (topo) a 1 (base).")
    x1: float = Field(ge=0, le=1, description="Borda direita, de 0 a 1 (maior ou igual a x0).")
    y1: float = Field(ge=0, le=1, description="Borda inferior, de 0 a 1 (maior ou igual a y0).")

    @model_validator(mode="after")
    def _ordem(self) -> Self:
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("bbox com x1 < x0 ou y1 < y0")
        return self


class Referencias(BaseModel):
    """Referências que ligam o documento (ou uma linha) a um processo de importação."""

    bls: list[str] = Field(
        default_factory=list,
        description="Números de BL (master ou house) citados, como impressos.",
    )
    conteineres: list[str] = Field(
        default_factory=list,
        description="Números de contêiner citados (4 letras + 7 dígitos, ex. MSKU1234567).",
    )
    ref_cliente: list[str] = Field(
        default_factory=list,
        description="Referências do cliente: pedido (PO), processo do cliente, invoice comercial.",
    )
    navio: str | None = Field(default=None, description="Nome do navio, se citado.")
    viagem: str | None = Field(default=None, description="Número da viagem, se citado (ex. 024W).")
    outras: list[str] = Field(
        default_factory=list,
        description="Outras referências úteis (chaves de NF-e, referência do agente, etc.).",
    )


class LinhaExtraida(BaseModel):
    """Uma cobrança do documento (não inclui subtotais nem totais)."""

    ordem: int = Field(ge=1, description="Posição da linha no documento, começando em 1.")
    descricao: str = Field(description="Descrição da cobrança, como impressa.")
    quantidade: Decimal | None = Field(default=None, description="Quantidade, se impressa.")
    valor_unitario: Decimal | None = Field(default=None, description="Valor unitário, se impresso.")
    valor: Decimal = Field(description="Valor total da linha na moeda da linha, com ponto decimal.")
    moeda: str = Field(
        pattern=r"^[A-Z]{3}$",
        description="Moeda ISO 4217 da linha (USD, BRL, EUR...). Sem moeda na linha, use a do cabeçalho.",
    )
    referencias: Referencias = Field(
        default_factory=Referencias, description="Referências citadas especificamente nesta linha."
    )
    taxa_cambio_informada: Decimal | None = Field(
        default=None,
        description='Taxa de câmbio impressa na linha ("USD 1.800,00 x 5,6120 = R$ ..."), se houver.',
    )
    valor_moeda_origem: Decimal | None = Field(
        default=None, description="Valor na moeda original, quando a linha mostra uma conversão."
    )
    moeda_origem: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{3}$",
        description="Moeda original, quando a linha mostra uma conversão.",
    )
    bbox: BBox | None = Field(default=None, description="Caixa aproximada da linha na página.")
    confianca: float = Field(default=1.0, ge=0, le=1, description="Confiança na extração (0 a 1).")


class CabecalhoExtraido(BaseModel):
    """Dados gerais do documento."""

    fornecedor_nome: str = Field(description="Nome do emissor, como aparece no documento.")
    fornecedor_documento: str | None = Field(
        default=None, description="CNPJ ou VAT/Tax ID do emissor, se impresso."
    )
    numero_documento: str = Field(description="Número da fatura, nota de débito ou documento.")
    data_emissao: date | None = Field(default=None, description="Data de emissão (YYYY-MM-DD).")
    data_vencimento: date | None = Field(
        default=None, description="Data de vencimento (YYYY-MM-DD)."
    )
    moeda: str = Field(pattern=r"^[A-Z]{3}$", description="Moeda ISO 4217 do total do documento.")
    total: Decimal = Field(description="Total do documento, com ponto decimal.")
    referencias: Referencias = Field(
        default_factory=Referencias, description="Referências citadas no cabeçalho do documento."
    )
    bbox_total: BBox | None = Field(default=None, description="Caixa aproximada do total.")


class FaturaExtraida(BaseModel):
    """Resultado da extração (E2): cabeçalho e linhas de cobrança."""

    cabecalho: CabecalhoExtraido = Field(description="Dados gerais do documento.")
    linhas: list[LinhaExtraida] = Field(min_length=1, description="Todas as linhas de cobrança.")
    origem: OrigemExtracao = Field(description="Como foi extraído: llm ou cte_xml.")
    avisos: list[str] = Field(
        default_factory=list, description="Avisos da extração (não são falhas)."
    )
    confianca_campos: dict[str, float] = Field(
        default_factory=dict,
        description="Confiança por campo do cabeçalho quando divergente entre extrações (CF-52).",
    )


# --------------------------------------------------------------- código de custo (E4)

MetodoCodigo = Literal["dicionario_fornecedor", "dicionario_global", "vizinhos", "llm"]


class ResultadoCodigo(BaseModel):
    """Código de custo atribuído a uma cobrança e como foi decidido."""

    codigo: str
    conf_codigo: float = Field(ge=0, le=1)  # 1,0 dicionário do fornecedor; 0,95 global
    metodo: MetodoCodigo
    detalhes: dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------------ casamento (E6)
# Forma MÍNIMA do resultado do casamento que as regras (E7) consomem. O módulo `match` (E6) a
# produz e pode acrescentar campos; as regras só dependem do que está aqui.


class CasamentoLinha(BaseModel):
    """Uma linha cobrada casada (ou não) com uma provisão, na moeda de comparação."""

    linha_id: uuid.UUID
    provisao_id: uuid.UUID | None = None  # None: linha sem provisão
    cobrado: Decimal | None = None  # valor cobrado na moeda de comparação
    previsto: Decimal | None = None  # valor previsto (provisão) na moeda de comparação
    moeda: str = Field(default="BRL", pattern=r"^[A-Z]{3}$")  # moeda de comparação
    ptax: Decimal | None = None  # BRL por unidade de `moeda` (1 para BRL); None sem cotação
    ptax_data: date | None = None


class ResultadoCasamento(BaseModel):
    """Casamento de um documento: uma entrada por linha cobrada."""

    casamentos: list[CasamentoLinha] = Field(default_factory=list)
