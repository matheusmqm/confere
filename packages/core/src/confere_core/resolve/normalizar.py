"""Normalização e extração de referências (CF-57), base do casamento documento → processo (E3).

`normalizar_referencia(tipo, valor)` leva BL, contêiner e referência do cliente a uma forma
canônica comparável: sem acento, maiúsculas, sem espaços, `-`, `/`, `.`, `_`, `:` e `#`.

Decisões:
- BL (`bl_master`/`bl_house`): prefixos textuais ("BL", "B/L", "MBL", "HBL", "BILL OF LADING",
  "NO", "Nº", "NUMBER") caem só quando seguidos de separador; o prefixo alfabético do armador
  fica colado ao número. Logo "HBL-FOR-123456" vira "FOR123456" e "B/L: ATLX123456789" vira
  "ATLX123456789". O processo é normalizado pela mesma função, então os dois lados casam.
- `ref_cliente`: caem os prefixos "PO", "PEDIDO", "REF", "REFERENCIA", "CUSTOMER REF", mas os
  **zeros à esquerda do número são preservados** ("PO-00451" → "00451", não "451"): "00451" e
  "451" podem ser pedidos diferentes. Os dois formatos do gerador sintético, "PO-12345" e
  "PEDIDO 12345", viram "12345".
- `conteiner`: `iso6346.normalizar`.
"""

import re
import unicodedata

from confere_core.domain import Referencias
from confere_core.validators import iso6346

_SEPARADORES = re.compile(r"[\s\-/._:#]")
_SEP_CLASSE = r"[\s:.\-#/]"

_PREFIXOS_BL = re.compile(rf"^(?:BILL\s+OF\s+LADING|B/L|MBL|HBL|BL|NUMBER|NO){_SEP_CLASSE}+(?=\S)")
_PREFIXOS_REF_CLIENTE = re.compile(
    rf"^(?:CUSTOMER\s+REF|REFERENCIA|PEDIDO|REF|PO)(?:{_SEP_CLASSE}+|(?=\d))"
)

# Padrões de referência em texto livre (também usados por costcode.normalizar).
_LIMITE_E = r"(?<![A-Z0-9])"
_LIMITE_D = r"(?![A-Z0-9])"
PADRAO_BL_SYNTH = rf"{_LIMITE_E}[A-Z]{{3}}X\d{{9}}{_LIMITE_D}"
PADRAO_BL_GENERICO = rf"{_LIMITE_E}[A-Z]{{4}}\d{{8,10}}(?!\d)"
PADRAO_HBL = rf"{_LIMITE_E}HBL-?[A-Z]{{3}}-?\d{{6}}{_LIMITE_D}"
PADRAO_PO = rf"{_LIMITE_E}PO[-\s]?\d{{4,6}}{_LIMITE_D}"
PADRAO_PEDIDO = rf"{_LIMITE_E}PEDIDO\s?\d{{4,6}}{_LIMITE_D}"
PADROES_REFERENCIA = [
    re.compile(p, re.IGNORECASE)
    for p in (PADRAO_HBL, PADRAO_BL_SYNTH, PADRAO_BL_GENERICO, PADRAO_PEDIDO, PADRAO_PO)
]


def sem_acento_maiusculas(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in decomposto if not unicodedata.combining(c)).upper()


def normalizar_nome(texto: str) -> str:
    """Nome de empresa comparável: sem acento, maiúsculas, só letras e dígitos, espaços únicos."""
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", sem_acento_maiusculas(texto)).split())


def _tirar_prefixos(texto: str, padrao: re.Pattern[str]) -> str:
    anterior = None
    while anterior != texto:  # "BL NO. 123": mais de um prefixo
        anterior = texto
        texto = padrao.sub("", texto.strip(), count=1)
    return texto


def normalizar_referencia(tipo: str, valor: str) -> str:
    """Forma canônica de uma referência, para comparar documento e processo."""
    if tipo == "conteiner":
        return iso6346.normalizar(valor)
    texto = sem_acento_maiusculas(valor)
    if tipo in ("bl_master", "bl_house"):
        texto = _tirar_prefixos(texto, _PREFIXOS_BL)
    elif tipo == "ref_cliente":
        texto = _tirar_prefixos(texto, _PREFIXOS_REF_CLIENTE)
    return _SEPARADORES.sub("", texto)


def _sem_repetidos(itens: list[str]) -> list[str]:
    return list(dict.fromkeys(itens))


def extrair_referencias_texto(texto: str) -> Referencias:
    """BL, HBL, contêineres válidos (ISO 6346) e referências do cliente (PO/PEDIDO) de um texto."""
    t = sem_acento_maiusculas(texto)
    hbls = [m.group(0) for m in re.finditer(PADRAO_HBL, t)]
    mestres = [m.group(0) for p in (PADRAO_BL_SYNTH, PADRAO_BL_GENERICO) for m in re.finditer(p, t)]
    pedidos = [
        re.sub(r"\s+", " ", m.group(0))
        for p in (PADRAO_PO, PADRAO_PEDIDO)
        for m in re.finditer(p, t)
    ]
    return Referencias(
        bls=_sem_repetidos(mestres + hbls),
        conteineres=_sem_repetidos(iso6346.extrair_candidatos(texto)),
        ref_cliente=_sem_repetidos(pedidos),
    )
