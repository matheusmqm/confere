"""Injeção de erros da taxonomia nos documentos sintéticos (CF-36, `config/erros.yaml`).

`injetar` aplica, nesta ordem: valor_acima → taxa_nao_prevista → cambio_errado →
referencia_cruzada → duplicada (por último, para a cópia já sair com os outros erros). Cada passo
é uma função pura (`injetar_*`) que devolve a lista de documentos e os `ErroInjetado`. O
`ruido_visual` é aplicado depois, pela CF-37, e não passa por aqui.

Decisões:
- Só faturas e notas de débito em PDF recebem erro. CT-e (XML) e extratos não: o extrato apenas
  espelha as faturas e é ressincronizado depois dos passos que mudam valores.
- Quantidade = cota (`round(taxa x elegíveis)`, no mínimo 1), não sorteio por unidade.
- `linha_ordem` é 1-indexado; `None` marca erro do documento inteiro.
- `valor_erro_brl` usa a PTAX de venda da emissão (`cambio.py`); sem cotação (CNY, data fora da
  tabela) fica `None`: nada é inventado.
- Faturas convertidas pelo NVOCC nacional (linhas em BRL de valor previsto em USD) ficam
  reservadas ao `cambio_errado`: `valor_acima` e `taxa_nao_prevista` as ignoram.
- Duplicada: a cópia ganha novo id e outro nome de arquivo. Metade é idêntica byte a byte
  (`duplicata_identica`, o PDF é copiado do original) e metade é re-renderizada com emissão e
  vencimento +1 dia (sha256 diferente, mesmo número). Só a cópia carrega o erro `duplicada`.
- `codigo_custo` da taxa não prevista: o mais próximo do catálogo, ou `OUTROS` (fora do catálogo).
"""

import random
import re
import uuid
from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from confere_core.fx.tabela import TabelaPTAX
from confere_synth import cambio
from confere_synth.faturas import linha_para_extrato
from confere_synth.modelos import (
    DocumentoSintetico,
    ErroInjetado,
    LinhaSintetica,
    Mundo,
    Processo,
    Referencia,
)
from confere_synth.render import num_pt

CAMINHO_PADRAO = Path(__file__).resolve().parents[4] / "config" / "erros.yaml"
_CENTAVO = Decimal("0.01")
_QUATRO_CASAS = Decimal("0.0001")

_CODIGO_PROXIMO = {
    "Documentation fee": "DOC_FEE_ORIG",
    "Handling fee": "HANDLING_AGENTE",
    "Taxa de emissão de documento": "DOC_FEE_ORIG",
}
CODIGO_FORA_DO_CATALOGO = "OUTROS"


# ------------------------------------------------------------------ configuração


class _Cfg(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    taxa: float = Field(ge=0, le=1)
    unidade: Literal["linha", "fatura", "fatura_brl_convertida", "pdf"]


class CfgValorAcima(_Cfg):
    fator_min: float = Field(ge=1)
    fator_max: float = Field(ge=1)

    @model_validator(mode="after")
    def _ordem(self) -> Self:
        if self.fator_min > self.fator_max:
            raise ValueError("fator_min maior que fator_max")
        return self


class CfgTaxaNaoPrevista(_Cfg):
    descricoes: list[str] = Field(min_length=1)
    valor_min_brl: Decimal = Field(gt=0)
    valor_max_brl: Decimal = Field(gt=0)

    @model_validator(mode="after")
    def _ordem(self) -> Self:
        if self.valor_min_brl > self.valor_max_brl:
            raise ValueError("valor_min_brl maior que valor_max_brl")
        return self


class CfgCambioErrado(_Cfg):
    desvio_min: float = Field(gt=0)
    desvio_max: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordem(self) -> Self:
        if self.desvio_min > self.desvio_max:
            raise ValueError("desvio_min maior que desvio_max")
        return self


class ConfigErros(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    valor_acima: CfgValorAcima
    duplicada: _Cfg
    taxa_nao_prevista: CfgTaxaNaoPrevista
    cambio_errado: CfgCambioErrado
    referencia_cruzada: _Cfg
    ruido_visual: _Cfg

    @classmethod
    def carregar(cls, path: str | Path = CAMINHO_PADRAO) -> Self:
        with open(path, encoding="utf-8") as arquivo:
            return cls.model_validate(yaml.safe_load(arquivo))


# -------------------------------------------------------------------- auxiliares


def _quantos(taxa: float, elegiveis: int) -> int:
    return 0 if elegiveis == 0 else max(1, round(taxa * elegiveis))


def _cobranca(doc: DocumentoSintetico) -> bool:
    """Fatura ou nota de débito em PDF que não é cópia (só elas recebem erro)."""
    return (
        doc.formato == "pdf" and doc.tipo in ("fatura", "nota_debito") and doc.duplicata_de is None
    )


def _convertida(doc: DocumentoSintetico) -> bool:
    return any(linha.moeda_origem and not linha.informativa for linha in doc.linhas)


def _soma(linhas: list[LinhaSintetica]) -> Decimal:
    return sum((linha.valor for linha in linhas), Decimal(0))


def _bl_master(proc: Processo) -> str | None:
    return next((r.valor for r in proc.referencias if r.tipo == "bl_master"), None)


def _com_erro(
    doc: DocumentoSintetico, erro: ErroInjetado, **mudancas: object
) -> DocumentoSintetico:
    return doc.model_copy(update={**mudancas, "erros": [*doc.erros, erro]})


# ----------------------------------------------------------------------- passos


def injetar_valor_acima(
    rng: random.Random,
    documentos: list[DocumentoSintetico],
    mundo: Mundo,
    cfg: CfgValorAcima,
    ptax: TabelaPTAX,
) -> tuple[list[DocumentoSintetico], list[ErroInjetado]]:
    """Multiplica o valor de linhas por um fator em [fator_min, fator_max]."""
    docs = list(documentos)
    erros: list[ErroInjetado] = []
    provs = {p.id: p for p in mundo.provisoes}
    candidatas = [
        (i, j)
        for i, d in enumerate(docs)
        if _cobranca(d) and not _convertida(d)
        for j, linha in enumerate(d.linhas)
        if linha.provisao_id and not linha.informativa
    ]
    for i, j in sorted(rng.sample(candidatas, _quantos(cfg.taxa, len(candidatas)))):
        doc = docs[i]
        linha = doc.linhas[j]
        fator = Decimal(str(round(rng.uniform(cfg.fator_min, cfg.fator_max), 4)))
        novo = (linha.valor * fator).quantize(_CENTAVO, ROUND_HALF_EVEN)
        previsto = provs[linha.provisao_id or uuid.UUID(int=0)].valor
        erro_moeda = novo - previsto
        linhas = list(doc.linhas)
        linhas[j] = linha.model_copy(
            update={"valor": novo, "valor_unit": (novo / linha.quantidade).quantize(_CENTAVO)}
        )
        erro = ErroInjetado(
            doc_id=doc.id,
            linha_ordem=j + 1,
            tipo="valor_acima",
            valor_erro_moeda=erro_moeda,
            moeda=linha.moeda,
            valor_erro_brl=cambio.para_brl(ptax, erro_moeda, linha.moeda, doc.emissao),
            descricao=f"{linha.codigo_custo}: previsto {previsto}, cobrado {novo} (x{fator})",
        )
        docs[i] = _com_erro(doc, erro, linhas=linhas, total=_soma(linhas))
        erros.append(erro)
    return docs, erros


def _descricoes_no_idioma(descricoes: list[str], idioma: str) -> list[str]:
    pt = [d for d in descricoes if d.lower().startswith("taxa")]
    en = [d for d in descricoes if d not in pt]
    return (pt if idioma == "pt" else en) or descricoes


def injetar_taxa_nao_prevista(
    rng: random.Random,
    documentos: list[DocumentoSintetico],
    mundo: Mundo,
    cfg: CfgTaxaNaoPrevista,
    ptax: TabelaPTAX,
) -> tuple[list[DocumentoSintetico], list[ErroInjetado]]:
    """Acrescenta uma linha sem provisão (valor em BRL sorteado, na moeda da fatura)."""
    docs = list(documentos)
    erros: list[ErroInjetado] = []
    forn = {f.id: f for f in mundo.fornecedores}
    candidatas = [i for i, d in enumerate(docs) if _cobranca(d) and not _convertida(d)]
    alvo = _quantos(cfg.taxa, len(candidatas))
    for i in rng.sample(candidatas, len(candidatas)):
        if len(erros) >= alvo:
            break
        doc = docs[i]
        valor_brl = Decimal(
            str(round(rng.uniform(float(cfg.valor_min_brl), float(cfg.valor_max_brl)), 2))
        )
        taxa = cambio.venda(ptax, doc.moeda, doc.emissao)
        descricao = rng.choice(
            _descricoes_no_idioma(cfg.descricoes, forn[doc.fornecedor_id].idioma)
        )
        if taxa is None:  # sem câmbio para a data/moeda: tenta outra fatura
            continue
        valor = max((valor_brl / taxa).quantize(_CENTAVO, ROUND_HALF_EVEN), _CENTAVO)
        nova = LinhaSintetica(
            descricao=descricao,
            valor_unit=valor,
            valor=valor,
            moeda=doc.moeda,
            codigo_custo=_CODIGO_PROXIMO.get(descricao, CODIGO_FORA_DO_CATALOGO),
            processo_id=doc.processo_id or doc.linhas[0].processo_id,
            provisao_id=None,
            secao="honorario" if forn[doc.fornecedor_id].tipo == "despachante" else None,
        )
        linhas = [*doc.linhas, nova]
        erro = ErroInjetado(
            doc_id=doc.id,
            linha_ordem=len(linhas),
            tipo="taxa_nao_prevista",
            valor_erro_moeda=valor,
            moeda=doc.moeda,
            valor_erro_brl=cambio.para_brl(ptax, valor, doc.moeda, doc.emissao),
            descricao=f"cobrança sem provisão: {descricao} ({nova.codigo_custo})",
        )
        docs[i] = _com_erro(doc, erro, linhas=linhas, total=_soma(linhas))
        erros.append(erro)
    return docs, erros


def injetar_cambio_errado(
    rng: random.Random,
    documentos: list[DocumentoSintetico],
    mundo: Mundo,
    cfg: CfgCambioErrado,
    ptax: TabelaPTAX,
) -> tuple[list[DocumentoSintetico], list[ErroInjetado]]:
    """Faturas em BRL de valor previsto em moeda estrangeira: taxa = PTAX x (1 + desvio)."""
    docs = list(documentos)
    erros: list[ErroInjetado] = []
    candidatas = [i for i, d in enumerate(docs) if _cobranca(d) and _convertida(d)]
    for i in sorted(rng.sample(candidatas, _quantos(cfg.taxa, len(candidatas)))):
        doc = docs[i]
        desvio = Decimal(str(round(rng.uniform(cfg.desvio_min, cfg.desvio_max), 4)))
        novas_taxas: dict[str, Decimal] = {}
        linhas: list[LinhaSintetica] = []
        diferenca = Decimal(0)
        for linha in doc.linhas:
            if linha.moeda_origem is None or linha.informativa:
                linhas.append(linha)
                continue
            assert linha.valor_origem is not None and linha.taxa_cambio is not None
            nova_taxa = novas_taxas.setdefault(
                linha.moeda_origem,
                (linha.taxa_cambio * (1 + desvio)).quantize(_QUATRO_CASAS, ROUND_HALF_EVEN),
            )
            novo = (linha.valor_origem * nova_taxa).quantize(_CENTAVO, ROUND_HALF_EVEN)
            diferenca += novo - linha.valor
            linhas.append(
                linha.model_copy(
                    update={
                        "valor": novo,
                        "valor_unit": (novo / linha.quantidade).quantize(_CENTAVO),
                        "taxa_cambio": nova_taxa,
                    }
                )
            )
        linhas = [  # a linha informativa passa a mostrar a taxa aplicada (a errada)
            ln.model_copy(
                update={
                    "taxa_cambio": novas_taxas[ln.moeda_origem],
                    "descricao": re.sub(
                        r": [\d.,]+ \(",
                        f": {num_pt(novas_taxas[ln.moeda_origem], 4)} (",
                        ln.descricao,
                    ),
                }
            )
            if ln.informativa and ln.moeda_origem in novas_taxas
            else ln
            for ln in linhas
        ]
        erro = ErroInjetado(
            doc_id=doc.id,
            linha_ordem=None,
            tipo="cambio_errado",
            valor_erro_moeda=diferenca,
            moeda=doc.moeda,
            valor_erro_brl=diferenca,  # a fatura já está em BRL
            descricao="taxa aplicada "
            + ", ".join(
                f"{m}: {num_pt(t, 4)} (+{desvio * 100:.2f}% sobre a PTAX)"
                for m, t in novas_taxas.items()
            ),
        )
        docs[i] = _com_erro(doc, erro, linhas=linhas, total=_soma(linhas))
        erros.append(erro)
    return docs, erros


def sincronizar_extratos(
    documentos: list[DocumentoSintetico], mundo: Mundo
) -> list[DocumentoSintetico]:
    """Refaz as linhas dos extratos a partir das faturas que eles listam (valores atuais)."""
    por_proc = {p.id: p for p in mundo.processos}
    faturas = {(d.fornecedor_id, d.numero): d for d in documentos if d.tipo != "extrato"}
    resultado: list[DocumentoSintetico] = []
    for doc in documentos:
        if doc.tipo != "extrato":
            resultado.append(doc)
            continue
        numeros = list(dict.fromkeys(linha.fatura_no for linha in doc.linhas if linha.fatura_no))
        linhas = [
            linha_para_extrato(linha, numero, por_proc)
            for numero in numeros
            for linha in faturas[(doc.fornecedor_id, numero)].linhas
            if not linha.informativa
        ]
        resultado.append(doc.model_copy(update={"linhas": linhas, "total": _soma(linhas)}))
    return resultado


def injetar_referencia_cruzada(
    rng: random.Random,
    documentos: list[DocumentoSintetico],
    mundo: Mundo,
    cfg: _Cfg,
    ptax: TabelaPTAX,
) -> tuple[list[DocumentoSintetico], list[ErroInjetado]]:
    """Troca o BL citado pelo de OUTRO processo do mesmo armador; o gabarito mantém o verdadeiro."""
    docs = list(documentos)
    erros: list[ErroInjetado] = []
    proc = {p.id: p for p in mundo.processos}
    por_armador: dict[str, list[Processo]] = {}
    for p in mundo.processos:
        if p.armador_id and _bl_master(p):
            por_armador.setdefault(p.armador_id, []).append(p)

    def outros_do_armador(d: DocumentoSintetico) -> list[Processo]:
        p = proc[d.processo_id] if d.processo_id else None
        if p is None or p.armador_id is None:
            return []
        return [o for o in por_armador.get(p.armador_id, []) if o.id != p.id]

    candidatas = [
        i
        for i, d in enumerate(docs)
        if _cobranca(d)
        and any(r.tipo == "bl_master" for r in d.referencias)
        and outros_do_armador(d)
    ]
    for i in sorted(rng.sample(candidatas, _quantos(cfg.taxa, len(candidatas)))):
        doc = docs[i]
        verdadeiro = proc[doc.processo_id or uuid.UUID(int=0)]
        outro = rng.choice(outros_do_armador(doc))
        antigo, novo = _bl_master(verdadeiro) or "", _bl_master(outro) or ""

        def trocar(
            refs: list[Referencia], antigo: str = antigo, novo: str = novo
        ) -> list[Referencia]:
            return [
                Referencia(tipo=r.tipo, valor=novo)
                if r.tipo == "bl_master" and r.valor == antigo
                else r
                for r in refs
            ]

        linhas = [
            linha.model_copy(update={"referencias": trocar(linha.referencias)})
            for linha in doc.linhas
        ]
        erro = ErroInjetado(
            doc_id=doc.id,
            linha_ordem=None,
            tipo="referencia_cruzada",
            valor_erro_moeda=None,
            moeda=doc.moeda,
            valor_erro_brl=None,
            descricao=(
                f"cita o BL {novo} (processo {outro.codigo}); o verdadeiro é {antigo} "
                f"(processo {verdadeiro.codigo})"
            ),
        )
        docs[i] = _com_erro(doc, erro, referencias=trocar(doc.referencias), linhas=linhas)
        erros.append(erro)
    return docs, erros


def injetar_duplicada(
    rng: random.Random,
    documentos: list[DocumentoSintetico],
    mundo: Mundo,
    cfg: _Cfg,
    ptax: TabelaPTAX,
) -> tuple[list[DocumentoSintetico], list[ErroInjetado]]:
    """Reenvios de faturas (já com os outros erros), com outro nome de arquivo."""
    docs = list(documentos)
    erros: list[ErroInjetado] = []
    candidatas = [i for i, d in enumerate(docs) if _cobranca(d)]
    escolhidas = rng.sample(candidatas, _quantos(cfg.taxa, len(candidatas)))
    n_identicas = (len(escolhidas) + 1) // 2  # metade idêntica, metade re-renderizada
    for posicao, i in enumerate(escolhidas):
        original = documentos[i]
        identica = posicao < n_identicas
        novo_id = uuid.UUID(int=rng.getrandbits(128), version=4)
        mudancas: dict[str, object] = {}
        if not identica:  # re-renderizada: emissão e vencimento +1 dia, mesmo número
            mudancas["emissao"] = original.emissao + timedelta(days=1)
            if original.vencimento is not None:
                mudancas["vencimento"] = original.vencimento + timedelta(days=1)
        erro = ErroInjetado(
            doc_id=novo_id,
            linha_ordem=None,
            tipo="duplicada",
            valor_erro_moeda=original.total,
            moeda=original.moeda,
            valor_erro_brl=cambio.para_brl(
                ptax,
                original.total,
                original.moeda,
                mudancas.get("emissao", original.emissao),  # type: ignore[arg-type]
            ),
            descricao=(
                f"reenvio de {original.numero} ({original.id}), "
                + ("idêntico byte a byte" if identica else "re-renderizado com emissão +1 dia")
            ),
        )
        docs.append(
            original.model_copy(
                update={
                    **mudancas,
                    "id": novo_id,
                    "arquivo": f"documentos/{novo_id}.pdf",
                    "sha256": None,
                    "duplicata_de": original.id,
                    "duplicata_identica": identica,
                    "erros": [erro],
                    "ruido": False,
                    "arquivo_original": None,
                }
            )
        )
        erros.append(erro)
    return docs, erros


# ------------------------------------------------------------------------ geral


def injetar(
    rng: random.Random,
    documentos: list[DocumentoSintetico],
    mundo: Mundo,
    cfg: ConfigErros,
    *,
    ptax: TabelaPTAX | None = None,
) -> tuple[list[DocumentoSintetico], list[ErroInjetado]]:
    """Aplica os 5 passos em ordem e devolve (documentos com erros, lista de erros)."""
    tabela = ptax if ptax is not None else cambio.carregar_ptax_padrao()
    docs, erros = injetar_valor_acima(rng, list(documentos), mundo, cfg.valor_acima, tabela)
    docs, novos = injetar_taxa_nao_prevista(rng, docs, mundo, cfg.taxa_nao_prevista, tabela)
    erros += novos
    docs, novos = injetar_cambio_errado(rng, docs, mundo, cfg.cambio_errado, tabela)
    erros += novos
    docs = sincronizar_extratos(docs, mundo)  # extratos espelham os valores já alterados
    docs, novos = injetar_referencia_cruzada(rng, docs, mundo, cfg.referencia_cruzada, tabela)
    erros += novos
    docs, novos = injetar_duplicada(rng, docs, mundo, cfg.duplicada, tabela)
    return docs, erros + novos
