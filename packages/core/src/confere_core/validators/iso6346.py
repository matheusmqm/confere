"""Validação e geração de números de contêiner ISO 6346.

Formato: 3 letras do código do dono + categoria (`U`, `J` ou `Z`) + 6 dígitos de série
+ 1 dígito verificador. O core hospeda este módulo porque a E2 valida contêineres e o
gerador sintético (`confere_synth`) importa daqui.
"""

import random
import re
import string

_REGEX_NUMERO = re.compile(r"^[A-Z]{3}[UJZ]\d{7}$")
_REGEX_PREFIXO = re.compile(r"^[A-Z]{4}\d{6}$")
_REGEX_DONO = re.compile(r"^[A-Z]{3}$")
_SEPARADORES = re.compile(r"[\s\-/.]+")
_REGEX_CANDIDATO = re.compile(
    r"(?<![A-Z0-9])([A-Z]{3}[UJZ])[ \-./]?(\d{6})[ \-./]?(\d)(?![A-Z0-9])"
)


def _valores_letras() -> dict[str, int]:
    """A=10, B=12, C=13... começa em 10 e pula os múltiplos de 11 (11, 22, 33)."""
    valores: dict[str, int] = {}
    valor = 10
    for letra in string.ascii_uppercase:
        if valor % 11 == 0:
            valor += 1
        valores[letra] = valor
        valor += 1
    return valores


VALORES_LETRAS: dict[str, int] = _valores_letras()

# Códigos de dono INVENTADOS para dados sintéticos. Não são de armadores conhecidos, mas
# não foram conferidos contra o registro do BIC: não use fora de dados fictícios.
DONOS_FICTICIOS: tuple[str, ...] = (
    "ZQA", "ZQB", "ZQC", "ZQD", "ZQE",
    "XQA", "XQB", "XQC", "XQD", "XQE",
    "QZA", "QZB", "QZC", "QXA", "QXB",
)  # fmt: skip


def normalizar(texto: str) -> str:
    """Maiúsculas, sem espaços, hífens, barras e pontos: "MSKU 123456-7" → "MSKU1234567"."""
    return _SEPARADORES.sub("", texto).upper()


def digito_verificador(prefixo10: str) -> int:
    """Dígito verificador dos 10 primeiros caracteres (4 letras + 6 dígitos)."""
    if not _REGEX_PREFIXO.match(prefixo10):
        raise ValueError(f"prefixo deve ter 4 letras maiúsculas e 6 dígitos: {prefixo10!r}")
    soma = 0
    for i, caractere in enumerate(prefixo10):
        valor = VALORES_LETRAS[caractere] if caractere.isalpha() else int(caractere)
        soma += valor * 2**i
    return soma % 11 % 10


def valido(numero: str) -> bool:
    """True se, após normalizar, o formato e o dígito verificador estão corretos."""
    normalizado = normalizar(numero)
    if not _REGEX_NUMERO.match(normalizado):
        return False
    return digito_verificador(normalizado[:10]) == int(normalizado[10])


def gerar(rng: random.Random, dono: str | None = None) -> str:
    """Gera um número válido, determinístico dado o `rng`. Sem `dono`, sorteia um fictício."""
    if dono is None:
        dono = rng.choice(DONOS_FICTICIOS)
    dono = dono.upper()
    if not _REGEX_DONO.match(dono):
        raise ValueError(f"dono deve ter 3 letras: {dono!r}")
    prefixo = f"{dono}U{rng.randrange(1_000_000):06d}"
    return f"{prefixo}{digito_verificador(prefixo)}"


def extrair_candidatos(texto: str) -> list[str]:
    """Acha contêineres válidos em texto livre (com ou sem espaço, hífen, barra ou ponto).

    Devolve números normalizados, sem repetição, na ordem em que aparecem.
    """
    achados: list[str] = []
    for m in _REGEX_CANDIDATO.finditer(texto.upper()):
        numero = "".join(m.groups())
        if valido(numero) and numero not in achados:
            achados.append(numero)
    return achados
