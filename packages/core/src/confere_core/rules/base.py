"""Framework de regras de negócio (E7, CF-80).

Cada regra é uma função pura `ContextoRegras -> list[ResultadoRegra]`, registrada com
`@regra(nome, ordem)`. `aplicar_regras` roda todas em ordem; o estado final de cada linha é o do
resultado de maior severidade (bloquear > revisar > info), e no empate o da regra de menor
`ordem`. Linha sem resultado é `ok`.

Em risco: soma do `valor_brl_em_risco` do resultado vencedor de cada linha mais o dos
resultados que não são de linha (documento/provisão); assim uma linha com dois achados não conta
o valor duas vezes.
"""

import uuid
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from confere_core.domain import CabecalhoExtraido, ResultadoCasamento

EstadoLinha = Literal[
    "ok",
    "acima_tolerancia",
    "abaixo_previsto",
    "sem_provisao",
    "duplicada",
    "cambio_divergente",
    "sem_fatura",
]
Severidade = Literal["info", "revisar", "bloquear"]
AlvoRegra = Literal["linha", "documento", "provisao"]
_RANK: dict[str, int] = {"info": 0, "revisar": 1, "bloquear": 2}


class Politica(BaseModel):
    """Política de aprovação (valores padrão de `config/politica_padrao.yaml`)."""

    tol_abs_brl: Decimal = Decimal("50.00")
    tol_rel: Decimal = Decimal("0.03")
    limite_cambio_rel: Decimal = Decimal("0.015")


class CotacaoLinha(BaseModel):
    moeda: str
    taxa: Decimal  # BRL por unidade de `moeda`
    data: date


class DocumentoRegras(BaseModel):
    id: uuid.UUID
    empresa_id: uuid.UUID
    fornecedor_id: str
    numero: str
    sha256: str | None = None
    cabecalho: CabecalhoExtraido
    total_brl: Decimal


class LinhaRegras(BaseModel):
    id: uuid.UUID
    ordem: int
    descricao: str
    codigo_custo: str | None = None
    processo_id: uuid.UUID | None = None
    valor: Decimal
    moeda: str
    valor_brl: Decimal
    cotacao: CotacaoLinha | None = None


@runtime_checkable
class HistoricoDocumentos(Protocol):
    """Consulta ao histórico da empresa. Os métodos devolvem o id do documento já existente
    (o "original") ou None, para a explicação poder apontar para ele."""

    def existe_sha256(
        self, empresa_id: uuid.UUID, sha256: str, excluir_id: uuid.UUID | None
    ) -> uuid.UUID | None: ...

    def existe_numero(
        self, empresa_id: uuid.UUID, fornecedor_id: str, numero: str, excluir_id: uuid.UUID | None
    ) -> uuid.UUID | None: ...

    def linha_aprovada_igual(
        self,
        empresa_id: uuid.UUID,
        fornecedor_id: str,
        processo_id: uuid.UUID,
        codigo: str,
        valor: Decimal,
        moeda: str,
        excluir_documento_id: uuid.UUID | None,
    ) -> uuid.UUID | None: ...


class ContextoRegras(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    politica: Politica = Field(default_factory=Politica)
    documento: DocumentoRegras
    casamento: ResultadoCasamento
    linhas: list[LinhaRegras]
    historico: HistoricoDocumentos | None = None


class ResultadoRegra(BaseModel):
    regra: str
    alvo: AlvoRegra
    alvo_id: str
    estado: EstadoLinha
    severidade: Severidade
    valor_brl_em_risco: Decimal = Decimal(0)
    dados: dict[str, Any] = Field(default_factory=dict)  # para a explicação (E10)
    ordem: int = 0  # ordem da regra que gerou o resultado (preenchida por aplicar_regras)


class AvaliacaoRegras(BaseModel):
    resultados: list[ResultadoRegra]
    estados_linha: dict[str, ResultadoRegra]  # id da linha → resultado vencedor (ok sintetizado)
    regras_violadas: int  # resultados com severidade >= revisar
    total_em_risco: Decimal


Regra = Callable[[ContextoRegras], list[ResultadoRegra]]
REGISTRO: list[tuple[int, str, Regra]] = []


def regra(nome: str, ordem: int) -> Callable[[Regra], Regra]:
    """Registra a regra em `REGISTRO`, ordenado por `ordem` (nome desempata)."""

    def registrar(funcao: Regra) -> Regra:
        REGISTRO[:] = [r for r in REGISTRO if r[1] != nome]  # recarregar o módulo não duplica
        REGISTRO.append((ordem, nome, funcao))
        REGISTRO.sort(key=lambda r: (r[0], r[1]))
        return funcao

    return registrar


def _vence(a: ResultadoRegra, b: ResultadoRegra) -> ResultadoRegra:
    """Maior severidade; no empate, a regra de menor ordem."""
    if _RANK[a.severidade] != _RANK[b.severidade]:
        return a if _RANK[a.severidade] > _RANK[b.severidade] else b
    return a if a.ordem <= b.ordem else b


def aplicar_regras(ctx: ContextoRegras) -> AvaliacaoRegras:
    resultados: list[ResultadoRegra] = []
    for ordem, _, funcao in REGISTRO:
        resultados += [r.model_copy(update={"ordem": ordem}) for r in funcao(ctx)]

    por_linha: dict[str, ResultadoRegra] = {}
    for r in resultados:
        if r.alvo == "linha":
            atual = por_linha.get(r.alvo_id)
            por_linha[r.alvo_id] = r if atual is None else _vence(atual, r)
    estados: dict[str, ResultadoRegra] = {}
    for linha in ctx.linhas:
        chave = str(linha.id)
        estados[chave] = por_linha.get(chave) or ResultadoRegra(
            regra="ok", alvo="linha", alvo_id=chave, estado="ok", severidade="info"
        )

    em_risco = sum((r.valor_brl_em_risco for r in estados.values()), Decimal(0))
    em_risco += sum((r.valor_brl_em_risco for r in resultados if r.alvo != "linha"), Decimal(0))
    return AvaliacaoRegras(
        resultados=resultados,
        estados_linha=estados,
        regras_violadas=sum(1 for r in resultados if _RANK[r.severidade] >= _RANK["revisar"]),
        total_em_risco=em_risco,
    )
