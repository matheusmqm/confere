"""Mundo sintético: fornecedores, clientes, CNPJs fictícios e validações dos modelos."""

import random
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from confere_core.costcode.catalogo import Catalogo, normalizar
from confere_synth.modelos import Cliente, Fornecedor
from confere_synth.mundo import (
    cnpj_valido,
    gerar_clientes,
    gerar_cnpj_ficticio,
    gerar_fornecedores,
)

YAML = Path(__file__).resolve().parents[3] / "config" / "codigos_custo.yaml"


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    return Catalogo.carregar(YAML)


@pytest.fixture(scope="module")
def fornecedores(catalogo: Catalogo) -> list[Fornecedor]:
    return gerar_fornecedores(random.Random(42), catalogo)


# ------------------------------------------------------------ fornecedores


def test_quatorze_fornecedores_em_seis_tipos(fornecedores: list[Fornecedor]) -> None:
    assert len(fornecedores) == 14
    assert Counter(f.tipo for f in fornecedores) == {
        "armador": 3,
        "agente_exterior": 2,
        "terminal": 3,
        "armazem": 2,
        "transportadora": 2,
        "despachante": 2,
    }


def test_ids_e_nomes_unicos(fornecedores: list[Fornecedor]) -> None:
    assert len({f.id for f in fornecedores}) == 14
    assert len({f.nome for f in fornecedores}) == 14


def test_os_seis_estilos_sao_cobertos(fornecedores: list[Fornecedor]) -> None:
    assert {f.estilo_id for f in fornecedores} == {1, 2, 3, 4, 5, 6}


def test_todo_email_termina_em_example(fornecedores: list[Fornecedor]) -> None:
    assert all(f.dominio_email.endswith(".example") for f in fornecedores)


def test_idioma_moeda_e_pais_por_tipo(fornecedores: list[Fornecedor]) -> None:
    for f in fornecedores:
        if f.tipo in ("armador", "agente_exterior"):
            assert (f.idioma, f.pais != "BR") == ("en", True)
        else:
            assert (f.idioma, f.pais, f.moeda_padrao) == ("pt", "BR", "BRL")
    armadores = [f for f in fornecedores if f.tipo == "armador"]
    assert all(f.moeda_padrao == "USD" for f in armadores)
    agentes = {f.pais: f.moeda_padrao for f in fornecedores if f.tipo == "agente_exterior"}
    assert agentes == {"CN": "CNY", "DE": "EUR"}


def test_aliases_codigos_e_nomes_de_taxa(
    fornecedores: list[Fornecedor], catalogo: Catalogo
) -> None:
    conhecidos = set(catalogo.codigos())
    for f in fornecedores:
        assert 2 <= len(f.aliases) <= 4, f.id
        assert 4 <= len(f.codigos) <= 9, f.id
        assert set(f.codigos) <= conhecidos, f.id
        assert set(f.nomes_taxa) == set(f.codigos), f.id
        assert all(1 <= len(nomes) <= 3 for nomes in f.nomes_taxa.values()), f.id


def test_codigos_coerentes_com_o_tipo(fornecedores: list[Fornecedor]) -> None:
    por_tipo = {f.tipo: set(f.codigos) for f in fornecedores}
    assert "FRETE_RODO" in por_tipo["transportadora"]
    assert "HONORARIO_DESPACHO" in por_tipo["despachante"]
    assert "THC_DEST" in por_tipo["terminal"]
    assert "FRETE_MAR" in por_tipo["armador"]


def test_nomes_de_taxa_misturam_sinonimos_do_catalogo_e_variacoes(
    fornecedores: list[Fornecedor], catalogo: Catalogo
) -> None:
    mapa = catalogo.sinonimos_globais()
    nomes = [(c, n) for f in fornecedores for c, ns in f.nomes_taxa.items() for n in ns]
    conhecidos = [(c, n) for c, n in nomes if mapa.get(normalizar(n)) == c]
    desconhecidos = [(c, n) for c, n in nomes if normalizar(n) not in mapa]
    assert conhecidos and desconhecidos
    # nenhum nome de taxa aponta, pelo catálogo, para OUTRO código
    assert [(c, n) for c, n in nomes if mapa.get(normalizar(n), c) != c] == []


def test_cnpj_so_para_nacionais_e_sempre_ficticio(fornecedores: list[Fornecedor]) -> None:
    for f in fornecedores:
        if f.pais == "BR":
            assert f.cnpj_ficticio is not None and cnpj_valido(f.cnpj_ficticio), f.id
            assert f.cnpj_ficticio.startswith("00.000."), f.id
            assert not f.cnpj_ficticio.startswith("00.000.000"), f.id
        else:
            assert f.cnpj_ficticio is None, f.id
    cnpjs = [f.cnpj_ficticio for f in fornecedores if f.cnpj_ficticio]
    assert len(cnpjs) == len(set(cnpjs)) == 9


def test_determinismo_por_semente(catalogo: Catalogo) -> None:
    a = gerar_fornecedores(random.Random(1), catalogo)
    assert a == gerar_fornecedores(random.Random(1), catalogo)
    b = gerar_fornecedores(random.Random(2), catalogo)
    assert [f.id for f in a] == [f.id for f in b]  # lista fixa
    assert [f.cnpj_ficticio for f in a] != [f.cnpj_ficticio for f in b]


def test_codigo_fora_do_catalogo_e_rejeitado(monkeypatch: pytest.MonkeyPatch) -> None:
    mini = Catalogo.model_validate(
        {
            "versao": 1,
            "grupos": ["g"],
            "codigos": [
                {
                    "codigo": "SO_ESTE",
                    "descricao": "d",
                    "grupo": "g",
                    "moeda_tipica": "BRL",
                    "unidade": "por_bl",
                    "sinonimos": ["a", "b", "c"],
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="códigos fora do catálogo"):
        gerar_fornecedores(random.Random(0), mini)


# ----------------------------------------------------------------- clientes


def test_doze_clientes_ficticios() -> None:
    clientes = gerar_clientes(random.Random(42))
    assert len(clientes) == 12
    assert all(c.nome.endswith("(fictícia)") for c in clientes)
    assert len({c.id for c in clientes}) == len({c.nome for c in clientes}) == 12
    cnpjs = [c.cnpj_ficticio for c in clientes]
    assert len(set(cnpjs)) == 12
    assert all(cnpj_valido(c) and c.startswith("00.000.") for c in cnpjs)


def test_clientes_n_menor_e_invalido() -> None:
    assert len(gerar_clientes(random.Random(0), n=3)) == 3
    for n in (0, 13):
        with pytest.raises(ValueError):
            gerar_clientes(random.Random(0), n=n)


def test_cnpj_de_clientes_nunca_colide_com_o_de_fornecedores(catalogo: Catalogo) -> None:
    for semente in range(50):
        rng = random.Random(semente)
        f = {x.cnpj_ficticio for x in gerar_fornecedores(rng, catalogo)}
        c = {x.cnpj_ficticio for x in gerar_clientes(rng)}
        assert not (f & c)


# --------------------------------------------------------------------- CNPJ


@pytest.mark.parametrize("semente", range(30))
def test_cnpj_gerado_e_valido(semente: int) -> None:
    cnpj = gerar_cnpj_ficticio(random.Random(semente))
    assert cnpj_valido(cnpj)
    assert cnpj.startswith("00.000.") and cnpj.endswith("/0001-" + cnpj[-2:])


@pytest.mark.parametrize(
    ("cnpj", "esperado"),
    [
        ("11.222.333/0001-81", True),  # exemplo clássico de CNPJ válido (algoritmo)
        ("11.222.333/0001-80", False),
        ("11222333000181", False),  # sem máscara
        ("00.000.000/0000-00", False),
        ("", False),
    ],
)
def test_cnpj_valido(cnpj: str, esperado: bool) -> None:
    assert cnpj_valido(cnpj) is esperado


# ------------------------------------------------------------------- modelos


def _base() -> dict[str, object]:
    return {
        "id": "x",
        "nome": "X",
        "tipo": "armador",
        "pais": "SG",
        "idioma": "en",
        "moeda_padrao": "USD",
        "dominio_email": "x.example",
        "estilo_id": 1,
        "aliases": ["X"],
        "nomes_taxa": {"BAF": ["BAF"]},
        "codigos": ["BAF"],
    }


def test_modelo_base_valido() -> None:
    assert Fornecedor.model_validate(_base()).cnpj_ficticio is None


@pytest.mark.parametrize(
    "alteracao",
    [
        {"dominio_email": "x.com"},
        {"dominio_email": "x.example.com"},
        {"estilo_id": 0},
        {"estilo_id": 7},
        {"tipo": "banco"},
        {"idioma": "es"},
        {"pais": "BRA"},
        {"moeda_padrao": "usd"},
        {"nomes_taxa": {"PSS": ["PSS"]}},  # taxa que ele não cobra
        {"id": "Com Espaço"},
    ],
)
def test_fornecedor_invalido(alteracao: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Fornecedor.model_validate({**_base(), **alteracao})


def test_modelos_sao_imutaveis_e_rejeitam_campo_extra() -> None:
    c = Cliente(id="c-1", nome="C (fictícia)", cnpj_ficticio="00.000.001/0001-00")
    with pytest.raises(ValidationError):
        c.nome = "outro"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        Cliente.model_validate({"id": "c-1", "nome": "C", "cnpj_ficticio": "x", "extra": 1})
