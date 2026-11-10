"""Schemas "amigáveis ao LLM" para o `response_schema` do Gemini (CF-48).

O Gemini aceita só um subconjunto do JSON Schema. `para_schema_gemini` converte um modelo
Pydantic: faz o inline de `$defs`/`$ref`, remove `default`, `title`, `additionalProperties` e
`format`, troca `anyOf [X, null]` por `X` com `nullable`, `Decimal` por string com padrão
decimal e `date` por string `YYYY-MM-DD`.

`FaturaExtraidaLLM` é o espelho de `FaturaExtraida` com tudo em string (o LLM devolve
"1495.20" e "2026-10-14"). Os padrões entram só no schema enviado ao modelo
(`json_schema_extra`), NÃO na validação Pydantic: assim `para_dominio()` ainda aceita
"1.495,20" ou "14/10/2026" e normaliza.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field

from confere_core.domain import (
    BBox,
    CabecalhoExtraido,
    FaturaExtraida,
    LinhaExtraida,
    Referencias,
)

PADRAO_DECIMAL = r"^-?\d+(\.\d{1,4})?$"
PADRAO_DATA = r"^\d{4}-\d{2}-\d{2}$"
_REMOVER = {"title", "default", "additionalProperties", "$defs", "examples", "format", "const"}
_NUMERICOS = {"number", "string"}


# ---------------------------------------------------------------------- JSON Schema


def _resolver(no: Any, defs: dict[str, Any], pilha: tuple[str, ...] = ()) -> Any:
    """Troca cada `$ref` pelo conteúdo referenciado (inline); recusa referência circular."""
    if isinstance(no, list):
        return [_resolver(x, defs, pilha) for x in no]
    if not isinstance(no, dict):
        return no
    if "$ref" in no:
        nome = str(no["$ref"]).rsplit("/", 1)[-1]
        if nome in pilha:
            raise ValueError(f"schema recursivo não suportado pelo Gemini: {nome}")
        resolvido = _resolver(defs[nome], defs, (*pilha, nome))
        extras = {k: _resolver(v, defs, pilha) for k, v in no.items() if k != "$ref"}
        return {**resolvido, **extras}
    return {k: _resolver(v, defs, pilha) for k, v in no.items()}


def _limpar(no: Any) -> Any:
    if isinstance(no, list):
        return [_limpar(x) for x in no]
    if not isinstance(no, dict):
        return no
    resto = {k: v for k, v in no.items() if k != "anyOf"}
    if "anyOf" in no:
        variantes = no["anyOf"]
        nao_nulas = [v for v in variantes if v.get("type") != "null"]
        aceita_nulo = len(nao_nulas) != len(variantes)
        if {v.get("type") for v in nao_nulas} == _NUMERICOS and len(nao_nulas) == 2:
            base: dict[str, Any] = {"type": "string", "pattern": PADRAO_DECIMAL}  # Decimal
        elif len(nao_nulas) == 1:
            base = _limpar(nao_nulas[0])
        else:
            raise ValueError(f"união de tipos não suportada pelo Gemini: {variantes}")
        no = {**base, **resto}
        if aceita_nulo:
            no["nullable"] = True
    if no.get("type") == "string" and no.get("format") == "date":
        no = {**no, "pattern": PADRAO_DATA}
    if "const" in no:
        no = {**no, "enum": [no["const"]]}
    saida: dict[str, Any] = {}
    for chave, valor in no.items():
        if chave in _REMOVER or chave.startswith(("exclusive", "$")):
            continue
        if chave == "properties":
            saida[chave] = {nome: _limpar(sub) for nome, sub in valor.items()}
        elif chave == "items":
            saida[chave] = _limpar(valor)
        else:
            saida[chave] = valor
    return saida


def para_schema_gemini(model: type[BaseModel]) -> dict[str, Any]:
    """Schema do modelo no subconjunto aceito pelo Gemini (sem `$ref`, `default` nem `title`)."""
    bruto = model.model_json_schema()
    defs = bruto.get("$defs", {})
    resolvido = _resolver({k: v for k, v in bruto.items() if k != "$defs"}, defs)
    limpo: dict[str, Any] = _limpar(resolvido)
    return limpo


# ---------------------------------------------------------------- normalizadores


class ConversaoLLMError(ValueError):
    """Um campo obrigatório da saída do LLM não pôde ser convertido."""


_SIMBOLOS_MOEDA = {
    "US$": "USD", "U$": "USD", "USD$": "USD", "$": "USD", "DOLAR": "USD", "DÓLAR": "USD",
    "R$": "BRL", "REAL": "BRL", "REAIS": "BRL", "€": "EUR", "EURO": "EUR", "EUROS": "EUR",
    "£": "GBP", "RMB": "CNY", "CNH": "CNY", "YUAN": "CNY", "CN¥": "CNY", "JP¥": "JPY", "¥": "JPY",
}  # fmt: skip


def normalizar_moeda(texto: str) -> str:
    """ "US$" → USD, "R$" → BRL, "eur" → EUR. Erra se não reconhecer."""
    limpo = re.sub(r"[\s.]", "", texto.strip().upper())
    if limpo in _SIMBOLOS_MOEDA:
        return _SIMBOLOS_MOEDA[limpo]
    if re.fullmatch(r"[A-Z]{3}", limpo):
        return limpo
    raise ValueError(f"moeda não reconhecida: {texto!r}")


def normalizar_decimal(texto: str) -> Decimal:
    """ "1.495,20" → 1495.20; "1,495.20" → 1495.20; "R$ -12,5" → -12.5; "(120,00)" → -120.00.

    O LLM é instruído a devolver ponto decimal, então um único ponto é decimal. Uma única
    vírgula com exatamente 3 dígitos depois ("1,495") é tratada como milhar.
    """
    bruto = texto.strip()
    negativo = bruto.startswith("-") or (bruto.startswith("(") and bruto.endswith(")"))
    negativo = negativo or bruto.endswith("-")
    numero = re.sub(r"[^\d.,]", "", bruto)
    if not numero or not re.search(r"\d", numero):
        raise ValueError(f"número inválido: {texto!r}")
    if "," in numero and "." in numero:
        decimal = "," if numero.rfind(",") > numero.rfind(".") else "."
        milhar = "." if decimal == "," else ","
        numero = numero.replace(milhar, "").replace(decimal, ".")
    elif "," in numero:
        depois = numero.rsplit(",", 1)[1]
        if numero.count(",") > 1 or len(depois) == 3:
            numero = numero.replace(",", "")  # milhar
        else:
            numero = numero.replace(",", ".")
    elif numero.count(".") > 1:
        numero = numero.replace(".", "")  # "1.495.200" → milhar
    try:
        valor = Decimal(numero)
    except InvalidOperation as erro:
        raise ValueError(f"número inválido: {texto!r}") from erro
    return -valor if negativo else valor


def normalizar_data(texto: str) -> date:
    """ "2026-10-14" ou "14/10/2026" (ou "14-10-2026") → date."""
    limpo = texto.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", limpo):
        return date.fromisoformat(limpo)
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", limpo)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    raise ValueError(f"data inválida: {texto!r}")


# ------------------------------------------------------------------ espelho (strings)

_DEC = {"pattern": PADRAO_DECIMAL}
_DATA = {"pattern": PADRAO_DATA}


class BBoxLLM(BaseModel):
    """Caixa aproximada de um trecho na página, normalizada de 0 a 1."""

    pagina: int = Field(description="Número da página, começando em 1.")
    x0: float = Field(description="Borda esquerda, de 0 (esquerda) a 1 (direita).")
    y0: float = Field(description="Borda superior, de 0 (topo) a 1 (base).")
    x1: float = Field(description="Borda direita, de 0 a 1 (maior ou igual a x0).")
    y1: float = Field(description="Borda inferior, de 0 a 1 (maior ou igual a y0).")


class ReferenciasLLM(BaseModel):
    """Referências que ligam o documento ou a linha a um processo de importação."""

    bls: list[str] = Field(default_factory=list, description="Números de BL citados.")
    conteineres: list[str] = Field(
        default_factory=list, description="Números de contêiner citados."
    )
    ref_cliente: list[str] = Field(
        default_factory=list, description="Referências do cliente (pedido, processo do cliente)."
    )
    navio: str | None = Field(default=None, description="Nome do navio, se citado.")
    viagem: str | None = Field(default=None, description="Viagem, se citada (ex. 024W).")
    outras: list[str] = Field(default_factory=list, description="Outras referências úteis.")


class LinhaExtraidaLLM(BaseModel):
    """Uma linha de cobrança do documento (nunca subtotal nem total)."""

    ordem: int = Field(description="Posição da linha, começando em 1.")
    descricao: str = Field(description="Descrição da cobrança, como impressa.")
    quantidade: str | None = Field(
        default=None, description="Quantidade, com ponto decimal.", json_schema_extra=_DEC
    )
    valor_unitario: str | None = Field(
        default=None, description="Valor unitário, com ponto decimal.", json_schema_extra=_DEC
    )
    valor: str = Field(
        description="Valor total da linha, com ponto decimal (ex. 1495.20).", json_schema_extra=_DEC
    )
    moeda: str = Field(description="Moeda ISO 4217 da linha (USD, BRL, EUR...).")
    referencias: ReferenciasLLM = Field(
        default_factory=ReferenciasLLM, description="Referências específicas desta linha."
    )
    taxa_cambio_informada: str | None = Field(
        default=None, description="Taxa de câmbio impressa na linha.", json_schema_extra=_DEC
    )
    valor_moeda_origem: str | None = Field(
        default=None, description="Valor na moeda original, se a linha mostra conversão.",
        json_schema_extra=_DEC,
    )  # fmt: skip
    moeda_origem: str | None = Field(
        default=None, description="Moeda original, se a linha mostra conversão."
    )
    bbox: BBoxLLM | None = Field(default=None, description="Caixa aproximada da linha.")


class CabecalhoExtraidoLLM(BaseModel):
    """Dados gerais do documento."""

    fornecedor_nome: str = Field(description="Nome do emissor, como aparece no documento.")
    fornecedor_documento: str | None = Field(default=None, description="CNPJ ou VAT do emissor.")
    numero_documento: str = Field(description="Número do documento.")
    data_emissao: str | None = Field(
        default=None, description="Data de emissão, YYYY-MM-DD.", json_schema_extra=_DATA
    )
    data_vencimento: str | None = Field(
        default=None, description="Data de vencimento, YYYY-MM-DD.", json_schema_extra=_DATA
    )
    moeda: str = Field(description="Moeda ISO 4217 do total.")
    total: str = Field(description="Total do documento, com ponto decimal.", json_schema_extra=_DEC)
    referencias: ReferenciasLLM = Field(
        default_factory=ReferenciasLLM, description="Referências do cabeçalho."
    )
    bbox_total: BBoxLLM | None = Field(default=None, description="Caixa aproximada do total.")


class FaturaExtraidaLLM(BaseModel):
    """Saída pedida ao LLM: cabeçalho e todas as linhas de cobrança."""

    cabecalho: CabecalhoExtraidoLLM = Field(description="Dados gerais do documento.")
    linhas: list[LinhaExtraidaLLM] = Field(min_length=1, description="Todas as linhas de cobrança.")

    def para_dominio(self) -> FaturaExtraida:
        """Converte para `FaturaExtraida` normalizando números, datas e moedas.

        Campos obrigatórios inconvertíveis (`valor`, `total`, `moeda` do cabeçalho) levantam
        `ConversaoLLMError`; os opcionais viram None e geram um aviso.
        """
        avisos: list[str] = []

        def dec(valor: str | None, campo: str, obrigatorio: bool = False) -> Decimal | None:
            if valor is None or not valor.strip():
                if obrigatorio:
                    raise ConversaoLLMError(f"{campo}: valor ausente")
                return None
            try:
                return normalizar_decimal(valor)
            except ValueError as erro:
                if obrigatorio:
                    raise ConversaoLLMError(f"{campo}: {erro}") from erro
                avisos.append(f"conversao_invalida: {campo}={valor!r}")
                return None

        def dia(valor: str | None, campo: str) -> date | None:
            if valor is None or not valor.strip():
                return None
            try:
                return normalizar_data(valor)
            except ValueError:
                avisos.append(f"conversao_invalida: {campo}={valor!r}")
                return None

        def moeda_opcional(valor: str | None, campo: str) -> str | None:
            if valor is None or not valor.strip():
                return None
            try:
                return normalizar_moeda(valor)
            except ValueError:
                avisos.append(f"conversao_invalida: {campo}={valor!r}")
                return None

        def refs(r: ReferenciasLLM) -> Referencias:
            def lista(itens: list[str]) -> list[str]:
                return [i.strip() for i in itens if i and i.strip()]

            return Referencias(
                bls=lista(r.bls),
                conteineres=lista(r.conteineres),
                ref_cliente=lista(r.ref_cliente),
                navio=(r.navio or "").strip() or None,
                viagem=(r.viagem or "").strip() or None,
                outras=lista(r.outras),
            )

        def caixa(b: BBoxLLM | None) -> BBox | None:
            if b is None:
                return None

            def c(x: float) -> float:
                return min(max(x, 0.0), 1.0)

            x0, x1 = sorted((c(b.x0), c(b.x1)))
            y0, y1 = sorted((c(b.y0), c(b.y1)))
            return BBox(pagina=max(b.pagina, 1), x0=x0, y0=y0, x1=x1, y1=y1)

        c = self.cabecalho
        try:
            moeda_cab = normalizar_moeda(c.moeda)
        except ValueError as erro:
            raise ConversaoLLMError(f"cabecalho.moeda: {erro}") from erro
        total = dec(c.total, "cabecalho.total", obrigatorio=True)
        assert total is not None
        cabecalho = CabecalhoExtraido(
            fornecedor_nome=c.fornecedor_nome.strip(),
            fornecedor_documento=(c.fornecedor_documento or "").strip() or None,
            numero_documento=c.numero_documento.strip(),
            data_emissao=dia(c.data_emissao, "cabecalho.data_emissao"),
            data_vencimento=dia(c.data_vencimento, "cabecalho.data_vencimento"),
            moeda=moeda_cab,
            total=total,
            referencias=refs(c.referencias),
            bbox_total=caixa(c.bbox_total),
        )

        linhas: list[LinhaExtraida] = []
        for posicao, ln in enumerate(self.linhas, start=1):
            campo = f"linhas[{posicao}]"
            valor = dec(ln.valor, f"{campo}.valor", obrigatorio=True)
            assert valor is not None
            try:
                moeda = normalizar_moeda(ln.moeda) if ln.moeda.strip() else moeda_cab
            except ValueError as erro:
                raise ConversaoLLMError(f"{campo}.moeda: {erro}") from erro
            linhas.append(
                LinhaExtraida(
                    ordem=ln.ordem if ln.ordem >= 1 else posicao,
                    descricao=ln.descricao.strip(),
                    quantidade=dec(ln.quantidade, f"{campo}.quantidade"),
                    valor_unitario=dec(ln.valor_unitario, f"{campo}.valor_unitario"),
                    valor=valor,
                    moeda=moeda,
                    referencias=refs(ln.referencias),
                    taxa_cambio_informada=dec(ln.taxa_cambio_informada, f"{campo}.taxa_cambio"),
                    valor_moeda_origem=dec(ln.valor_moeda_origem, f"{campo}.valor_moeda_origem"),
                    moeda_origem=moeda_opcional(ln.moeda_origem, f"{campo}.moeda_origem"),
                    bbox=caixa(ln.bbox),
                )
            )
        return FaturaExtraida(cabecalho=cabecalho, linhas=linhas, origem="llm", avisos=avisos)
