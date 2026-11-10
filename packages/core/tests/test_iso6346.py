"""ISO 6346: valores das letras, dígito verificador, validação, geração e extração."""

import random

import pytest
from hypothesis import given
from hypothesis import strategies as st

from confere_core.validators.iso6346 import (
    DONOS_FICTICIOS,
    VALORES_LETRAS,
    digito_verificador,
    extrair_candidatos,
    gerar,
    normalizar,
    valido,
)

# Exemplo clássico da própria norma ISO 6346 / BIC: CSQU305438-3.
VALIDO = "CSQU3054383"


@pytest.mark.parametrize(
    ("letra", "valor"),
    [
        ("A", 10),
        ("B", 12),
        ("C", 13),
        ("J", 20),
        ("K", 21),
        ("L", 23),
        ("U", 32),
        ("V", 34),
        ("Z", 38),
    ],
)
def test_valores_das_letras(letra: str, valor: int) -> None:
    assert VALORES_LETRAS[letra] == valor


def test_letras_pulam_multiplos_de_11() -> None:
    assert all(v % 11 != 0 for v in VALORES_LETRAS.values())
    assert len(set(VALORES_LETRAS.values())) == 26


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("MSKU 123456-7", "MSKU1234567"),
        ("msku.123456/7", "MSKU1234567"),
        ("  csqu 305438 3 ", "CSQU3054383"),
        ("MSKU1234567", "MSKU1234567"),
        ("", ""),
    ],
)
def test_normalizar(entrada: str, esperado: str) -> None:
    assert normalizar(entrada) == esperado


def test_digito_verificador_exemplo_da_norma() -> None:
    assert digito_verificador("CSQU305438") == 3


@pytest.mark.parametrize("prefixo", ["", "CSQU30543", "CSQU3054383", "csqu305438", "CSQ1305438"])
def test_digito_verificador_rejeita_prefixo_malformado(prefixo: str) -> None:
    with pytest.raises(ValueError):
        digito_verificador(prefixo)


def test_resto_10_vira_zero() -> None:
    # Procura um prefixo cuja soma dê resto 10 e confirma que o dígito é 0.
    rng = random.Random(1)
    for _ in range(2000):
        prefixo = f"ABCU{rng.randrange(1_000_000):06d}"
        soma = sum(
            (VALORES_LETRAS[c] if c.isalpha() else int(c)) * 2**i for i, c in enumerate(prefixo)
        )
        if soma % 11 == 10:
            assert digito_verificador(prefixo) == 0
            return
    pytest.fail("não achou prefixo com resto 10")


@pytest.mark.parametrize(
    "numero",
    [VALIDO, "csqu 305438-3", "CSQU 3054383", "CSQU-305438-3", "csqu3054383"],
)
def test_valido(numero: str) -> None:
    assert valido(numero)


@pytest.mark.parametrize(
    "numero",
    [
        "CSQU3054384",  # dígito errado
        "CSQU305438",  # curto
        "CSQU30543833",  # longo
        "CSQA3054383",  # categoria A não existe
        "CS1U3054383",  # dono com dígito
        "1234567890A",
        "",
    ],
)
def test_invalido(numero: str) -> None:
    assert not valido(numero)


@pytest.mark.parametrize("categoria", ["U", "J", "Z"])
def test_aceita_as_tres_categorias(categoria: str) -> None:
    prefixo = f"ZQA{categoria}123456"
    assert valido(f"{prefixo}{digito_verificador(prefixo)}")


def test_donos_ficticios() -> None:
    assert len(DONOS_FICTICIOS) == 15
    assert len(set(DONOS_FICTICIOS)) == 15
    assert all(len(d) == 3 and d.isupper() and d.isalpha() for d in DONOS_FICTICIOS)


def test_gerar_com_dono() -> None:
    numero = gerar(random.Random(7), dono="abc")
    assert numero.startswith("ABCU")
    assert valido(numero)


def test_gerar_dono_invalido() -> None:
    with pytest.raises(ValueError):
        gerar(random.Random(7), dono="ABCD")


def test_gerar_e_deterministico() -> None:
    assert gerar(random.Random(42)) == gerar(random.Random(42))
    assert gerar(random.Random(42)) != gerar(random.Random(43))


@given(st.integers(min_value=0, max_value=2**32))
def test_gerar_sempre_valido(semente: int) -> None:
    numero = gerar(random.Random(semente))
    assert valido(numero)
    assert numero[:3] in DONOS_FICTICIOS
    assert numero[3] == "U"


@given(st.integers(min_value=0, max_value=2**32), st.integers(min_value=1, max_value=9))
def test_trocar_o_digito_verificador_invalida(semente: int, delta: int) -> None:
    numero = gerar(random.Random(semente))
    errado = numero[:10] + str((int(numero[10]) + delta) % 10)
    assert not valido(errado)


# ----------------------------------------------------------- extração


def test_extrai_com_e_sem_separadores() -> None:
    texto = "Contêineres: CSQU 305438-3, csqu3054383 e CSQU-305438 3."
    assert extrair_candidatos(texto) == [VALIDO]


def test_extrai_varios_na_ordem_sem_repetir() -> None:
    a, b = gerar(random.Random(1)), gerar(random.Random(2))
    texto = f"Ctr {b[:4]} {b[4:10]}-{b[10]} / {a} / {b}"
    assert extrair_candidatos(texto) == [b, a]


def test_ignora_digito_errado() -> None:
    assert extrair_candidatos("CSQU3054384 e CSQU3054383") == [VALIDO]


def test_ignora_trecho_dentro_de_token_maior() -> None:
    assert extrair_candidatos("XCSQU3054383 e CSQU30543831") == []


def test_texto_sem_conteiner() -> None:
    assert extrair_candidatos("Fatura 2026/0142, BL MEDU1234567 sem ctr") == []
    assert extrair_candidatos("") == []
