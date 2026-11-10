"""Validações pós-extração (CF-51): a extração é confiável o bastante para seguir no pipeline?

`validar` é pura: recebe a `FaturaExtraida` e devolve as falhas, a fatura com confianças e
referências ajustadas e `inconsistente`. Qualquer falha **grave** significa que o documento deve
virar a exceção `extracao_inconsistente` (quem cria a exceção é o worker; aqui só se reporta).
"""

from datetime import date, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field

from confere_core.domain import FaturaExtraida, LinhaExtraida, Referencias
from confere_core.validators import iso6346

CAMINHO_MOEDAS = Path(__file__).resolve().parents[5] / "config" / "moedas.yaml"
TOLERANCIA_ABSOLUTA = Decimal("0.02")
TOLERANCIA_RELATIVA = Decimal("0.001")
TOLERANCIA_QTD_X_UNITARIO = Decimal("0.02")
CONFIANCA_LINHA_SUSPEITA = 0.5
FATOR_FALHA_NAO_GRAVE = 0.5
JANELA_PASSADO_DIAS = 365
JANELA_FUTURO_DIAS = 120
_PALAVRAS_DESCONTO = ("desconto", "discount")
_PALAVRAS_CAMBIO = ("câmbio", "cambio", "exchange rate")  # linha informativa de valor 0


@lru_cache(maxsize=1)
def moedas_padrao() -> frozenset[str]:
    """Moedas aceitas, de `config/moedas.yaml`."""
    with open(CAMINHO_MOEDAS, encoding="utf-8") as arquivo:
        return frozenset(yaml.safe_load(arquivo)["moedas"])


class ContextoValidacao(BaseModel):
    model_config = ConfigDict(frozen=True)

    moedas_aceitas: frozenset[str]
    janela_inicio: date
    janela_fim: date

    @classmethod
    def padrao(cls, hoje: date | None = None) -> Self:
        """Janela de hoje − 365 dias até hoje + 120 dias e as moedas de `config/moedas.yaml`."""
        hoje = hoje or date.today()
        return cls(
            moedas_aceitas=moedas_padrao(),
            janela_inicio=hoje - timedelta(days=JANELA_PASSADO_DIAS),
            janela_fim=hoje + timedelta(days=JANELA_FUTURO_DIAS),
        )

    @classmethod
    def demo(cls, janela_inicio: date, janela_fim: date) -> Self:
        """Modo demo: a janela do mundo sintético (datas de 2026 fora da janela real)."""
        return cls(
            moedas_aceitas=moedas_padrao(), janela_inicio=janela_inicio, janela_fim=janela_fim
        )


class FalhaValidacao(BaseModel):
    codigo: str
    campo: str
    mensagem: str
    grave: bool


class ResultadoValidacao(BaseModel):
    falhas: list[FalhaValidacao] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    fatura: FaturaExtraida  # com confianças e referências ajustadas
    inconsistente: bool  # há falha grave: o worker cria a exceção `extracao_inconsistente`
    confianca: float = Field(ge=0, le=1)  # mínimo das linhas, x 0,5 se houver falha não grave


def _refs_validas(
    refs: Referencias, campo: str, falhas: list[FalhaValidacao]
) -> tuple[Referencias, bool]:
    """Mantém só contêineres válidos (normalizados); os inválidos vão para `outras`."""
    validos: list[str] = []
    outras = list(refs.outras)
    houve_invalido = False
    for bruto in refs.conteineres:
        numero = iso6346.normalizar(bruto)
        if iso6346.valido(numero):
            if numero not in validos:
                validos.append(numero)
        else:
            houve_invalido = True
            if bruto not in outras:
                outras.append(bruto)
            falhas.append(
                FalhaValidacao(
                    codigo="conteiner_invalido",
                    campo=campo,
                    mensagem=f"contêiner {bruto!r} não passa na ISO 6346",
                    grave=False,
                )
            )
    return refs.model_copy(update={"conteineres": validos, "outras": outras}), houve_invalido


def validar(fatura: FaturaExtraida, contexto: ContextoValidacao) -> ResultadoValidacao:
    falhas: list[FalhaValidacao] = []
    avisos: list[str] = []
    cab = fatura.cabecalho

    # 1. soma das linhas (na moeda do cabeçalho) x total ------------------------- grave
    na_moeda = [ln for ln in fatura.linhas if ln.moeda == cab.moeda]
    for ln in fatura.linhas:
        if ln.moeda != cab.moeda:
            avisos.append(
                f"linha_em_outra_moeda: linha {ln.ordem} em {ln.moeda} (cabeçalho {cab.moeda}), "
                "fora da soma"
            )
    soma = sum((ln.valor for ln in na_moeda), Decimal(0))
    tolerancia = max(TOLERANCIA_ABSOLUTA, TOLERANCIA_RELATIVA * abs(cab.total))
    if abs(soma - cab.total) > tolerancia:
        falhas.append(
            FalhaValidacao(
                codigo="soma_linhas",
                campo="cabecalho.total",
                mensagem=f"soma das linhas {soma} diverge do total {cab.total}",
                grave=True,
            )
        )

    # 2. contêineres (cabeçalho e linhas) ---------------------------------------- não grave
    refs_cab, _ = _refs_validas(cab.referencias, "cabecalho.referencias.conteineres", falhas)
    linhas: list[LinhaExtraida] = []
    for ln in fatura.linhas:
        refs_ln, invalido = _refs_validas(
            ln.referencias, f"linhas[{ln.ordem}].referencias.conteineres", falhas
        )
        confianca = min(ln.confianca, CONFIANCA_LINHA_SUSPEITA) if invalido else ln.confianca
        linhas.append(ln.model_copy(update={"referencias": refs_ln, "confianca": confianca}))

    # 3. datas ------------------------------------------------------------------------------
    emissao, vencimento = cab.data_emissao, cab.data_vencimento
    if emissao is None and vencimento is None:
        falhas.append(
            FalhaValidacao(
                codigo="datas",
                campo="cabecalho.data_emissao",
                mensagem="sem data de emissão nem de vencimento",
                grave=True,
            )
        )
    if emissao and vencimento and emissao > vencimento:
        falhas.append(
            FalhaValidacao(
                codigo="datas",
                campo="cabecalho.data_vencimento",
                mensagem=f"emissão {emissao} depois do vencimento {vencimento}",
                grave=False,
            )
        )
    for campo, valor in (("data_emissao", emissao), ("data_vencimento", vencimento)):
        if valor and not contexto.janela_inicio <= valor <= contexto.janela_fim:
            falhas.append(
                FalhaValidacao(
                    codigo="datas",
                    campo=f"cabecalho.{campo}",
                    mensagem=(
                        f"{valor} fora da janela plausível "
                        f"({contexto.janela_inicio} a {contexto.janela_fim})"
                    ),
                    grave=False,
                )
            )

    # 4. moeda desconhecida ------------------------------------------------------- grave
    moedas = [("cabecalho.moeda", cab.moeda)]
    for ln in fatura.linhas:
        moedas.append((f"linhas[{ln.ordem}].moeda", ln.moeda))
        if ln.moeda_origem:
            moedas.append((f"linhas[{ln.ordem}].moeda_origem", ln.moeda_origem))
    for campo, moeda in moedas:
        if moeda not in contexto.moedas_aceitas:
            falhas.append(
                FalhaValidacao(
                    codigo="moeda_desconhecida",
                    campo=campo,
                    mensagem=f"moeda {moeda!r} fora da lista aceita",
                    grave=True,
                )
            )

    # 5. valor não positivo ------------------------------------------------------ não grave
    for ln in fatura.linhas:
        descricao = ln.descricao.lower()
        if ln.valor > 0:
            continue
        if ln.valor < 0 and any(p in descricao for p in _PALAVRAS_DESCONTO):
            continue  # desconto pode ser negativo
        if ln.valor == 0 and any(p in descricao for p in _PALAVRAS_CAMBIO):
            continue  # linha informativa ("Taxa de câmbio aplicada")
        falhas.append(
            FalhaValidacao(
                codigo="valor_nao_positivo",
                campo=f"linhas[{ln.ordem}].valor",
                mensagem=f"valor {ln.valor} não é positivo",
                grave=False,
            )
        )

    # 6. quantidade x unitário --------------------------------------------------- não grave
    for i, ln in enumerate(linhas):
        if ln.quantidade is None or ln.valor_unitario is None:
            continue
        diferenca = abs(ln.quantidade * ln.valor_unitario - ln.valor)
        if diferenca > TOLERANCIA_QTD_X_UNITARIO:
            falhas.append(
                FalhaValidacao(
                    codigo="quantidade_x_unitario",
                    campo=f"linhas[{ln.ordem}].valor",
                    mensagem=(
                        f"{ln.quantidade} x {ln.valor_unitario} difere de {ln.valor} em {diferenca}"
                    ),
                    grave=False,
                )
            )
            linhas[i] = ln.model_copy(
                update={"confianca": min(ln.confianca, CONFIANCA_LINHA_SUSPEITA)}
            )

    confianca = min(ln.confianca for ln in linhas)
    if any(not f.grave for f in falhas):
        confianca *= FATOR_FALHA_NAO_GRAVE
    ajustada = fatura.model_copy(
        update={
            "cabecalho": cab.model_copy(update={"referencias": refs_cab}),
            "linhas": linhas,
            "avisos": [*fatura.avisos, *avisos],
        }
    )
    return ResultadoValidacao(
        falhas=falhas,
        avisos=avisos,
        fatura=ajustada,
        inconsistente=any(f.grave for f in falhas),
        confianca=confianca,
    )
