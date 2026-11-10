"""Normalização da descrição de uma cobrança para classificação em código de custo (CF-64).

Passos: (1) sem acento e minúsculas; (2) tira contêineres, BLs e referências, moedas, datas,
números e valores; (3) expande siglas (`config/siglas.yaml`); (4) pontuação vira espaço; (5) tira
stopwords e colapsa espaços, preservando a ordem dos tokens.

Siglas com símbolo ("b/l", "w/m") são expandidas antes da pontuação virar espaço; as demais, e
as frases ("terminal handling charge"), depois, numa única passada (sem re-expandir).
"""

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from confere_core.resolve.normalizar import PADROES_REFERENCIA
from confere_core.validators import iso6346

CAMINHO_SIGLAS = Path(__file__).resolve().parents[5] / "config" / "siglas.yaml"

_MOEDA = re.compile(r"(?<![a-z0-9])(?:usd|eur|brl|cny)(?![a-z0-9])|r\$|us\$|€")
_DATA = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b")
_NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
_CONTEINER_GENERICO = re.compile(r"(?<![a-z0-9])[a-z]{4}[\s\-./]?\d{6}[\s\-./]?\d(?![a-z0-9])")
_PONTUACAO = re.compile(r"[^\w\s]|_")


def _sem_acento_minusculas(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).lower()


@lru_cache(maxsize=1)
def carregar_config(caminho: Path = CAMINHO_SIGLAS) -> dict[str, Any]:
    with open(caminho, encoding="utf-8") as arquivo:
        dados: dict[str, Any] = yaml.safe_load(arquivo)
    return dados


def _regex_chaves(chaves: list[str]) -> re.Pattern[str] | None:
    if not chaves:
        return None
    alternativas = "|".join(re.escape(k) for k in sorted(chaves, key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])(?:{alternativas})(?![a-z0-9])")


def _expandir(texto: str, mapa: dict[str, str], chaves: list[str]) -> str:
    padrao = _regex_chaves(chaves)
    return padrao.sub(lambda m: mapa[m.group(0)], texto) if padrao else texto


def normalizar_descricao(texto: str, config: dict[str, Any] | None = None) -> str:
    cfg = config or carregar_config()
    siglas = {str(k): str(v) for k, v in cfg["siglas"].items()}
    stopwords = {str(s) for s in cfg["stopwords"]}

    t = _sem_acento_minusculas(texto)

    # 2. contêineres (válidos pela ISO 6346 e qualquer 4 letras + 7 dígitos), BLs e referências
    for numero in iso6346.extrair_candidatos(texto):
        t = re.sub(
            re.escape(numero[:4].lower()) + r"[\s\-./]?" + numero[4:10] + r"[\s\-./]?" + numero[10],
            " ",
            t,
        )
    t = _CONTEINER_GENERICO.sub(" ", t)
    for padrao in PADROES_REFERENCIA:
        t = padrao.sub(" ", t)
    t = _MOEDA.sub(" ", t)
    t = _DATA.sub(" ", t)  # antes dos números
    t = _NUMERO.sub(" ", t)

    # 3a. siglas com símbolo, antes de a pontuação sumir
    com_simbolo = [k for k in siglas if not re.fullmatch(r"[a-z0-9 ]+", k)]
    t = _expandir(t, siglas, com_simbolo)
    t = _PONTUACAO.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # 3b. frases e palavras, numa passada
    t = _expandir(t, siglas, [k for k in siglas if k not in com_simbolo])

    # 4 e 5. stopwords, espaços colapsados, ordem preservada
    return " ".join(token for token in re.sub(r"\s+", " ", t).split() if token not in stopwords)
