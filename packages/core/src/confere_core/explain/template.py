"""Explicação por template (E10, fallback do MVP): texto em pt-BR sem LLM.

Os números vêm sempre dos dados da regra (nunca inventados). Quando existir a explicação por LLM
com validação de números (CF-97/98), este módulo vira o fallback dela.
"""

from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any


def reais(valor: Decimal | float | str) -> str:
    """`Decimal("12345.6")` → `R$ 12.345,60`."""
    v = Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    texto = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    sinal = chr(0x2212) if v < 0 else ""  # sinal de menos, não hífen
    return f"{sinal}R$ {texto}"


def explicar(tipo: str, dados: dict[str, Any]) -> tuple[str, str]:
    """(explicação, ação sugerida) para um tipo de exceção."""
    descricao = dados.get("descricao", "A cobrança")
    if tipo == "acima_tolerancia":
        return (
            f"{descricao}: cobrado {reais(dados['cobrado'])}, previsto {reais(dados['previsto'])}. "
            f"A diferença é de {reais(dados['dif_brl'])}, acima da tolerância.",
            "Contestar a diferença com o fornecedor ou aprovar se for legítima.",
        )
    if tipo == "sem_provisao":
        return (
            f"{descricao} ({reais(dados['valor_brl'])}) não tem custo previsto neste processo.",
            "Confirmar se a cobrança é legítima: repassar ao cliente ou contestar.",
        )
    if tipo == "duplicada":
        return (
            f"{descricao} ({reais(dados['valor_brl'])}) já foi cobrada em outro documento.",
            "Bloquear o pagamento e avisar o fornecedor.",
        )
    if tipo == "cambio_divergente":
        return (
            f"{descricao}: o câmbio usado difere da PTAX em {reais(dados['dif_brl'])}.",
            "Contestar o câmbio com o fornecedor.",
        )
    if tipo == "codigo_incerto":
        return (
            f"Não foi possível identificar o código de custo de “{dados.get('descricao', '')}”.",
            "Escolher o código de custo correto.",
        )
    if tipo == "sem_processo":
        return (
            "Nenhuma referência do documento bate com um processo cadastrado.",
            "Informar a qual processo o documento pertence.",
        )
    if tipo == "confirmar_processo":
        return (
            dados.get("motivo", "O processo encontrado precisa de confirmação."),
            "Confirmar o processo.",
        )
    if tipo == "moeda_sem_cotacao":
        return (
            f"Não há cotação PTAX para {dados.get('moeda', 'a moeda')}: valor em reais "
            "indisponível.",
            "Informar a cotação ou revisar manualmente.",
        )
    if tipo == "extracao_inconsistente":
        return (
            dados.get("motivo", "Os dados extraídos do documento não fecham."),
            "Conferir o documento manualmente.",
        )
    return ("Exceção encontrada no documento.", "Revisar o documento.")
