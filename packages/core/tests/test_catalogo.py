"""Catálogo de códigos de custo: arquivo real e regras de validação."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from confere_core.costcode.catalogo import Catalogo, CodigoCusto, normalizar

YAML_REAL = Path(__file__).resolve().parents[3] / "config" / "codigos_custo.yaml"

OBRIGATORIOS = {
    "FRETE_MAR", "BAF", "CAF", "PSS", "THC_ORIG", "THC_DEST", "BL_FEE", "DOC_FEE_ORIG",
    "DESCONSOLIDACAO", "LIBERACAO_BL", "ISPS", "SCANNER", "ARMAZENAGEM", "POSICIONAMENTO",
    "LEVANTE", "DEMURRAGE", "DETENTION", "LAVAGEM_CNTR", "AFRMM", "SISCOMEX", "FRETE_RODO",
    "PEDAGIO", "GRIS", "AD_VALOREM_SEGURO", "HONORARIO_DESPACHO", "SDA", "EMISSAO_LI",
    "COURIER", "HANDLING_AGENTE", "CORRECAO_BL",
}  # fmt: skip


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    return Catalogo.carregar(YAML_REAL)


def _item(
    codigo: str, grupo: str = "g", sinonimos: tuple[str, ...] = ("a", "b", "c")
) -> dict[str, Any]:
    return {
        "codigo": codigo,
        "descricao": "d",
        "grupo": grupo,
        "moeda_tipica": "BRL",
        "unidade": "por_bl",
        "sinonimos": list(sinonimos),
    }


def _montar(*itens: dict[str, Any], grupos: tuple[str, ...] = ("g",)) -> Catalogo:
    return Catalogo.model_validate({"versao": 1, "grupos": list(grupos), "codigos": list(itens)})


# ------------------------------------------------------------ arquivo real


def test_arquivo_real_tem_os_30_codigos(catalogo: Catalogo) -> None:
    assert len(catalogo.codigos()) == 30
    assert set(catalogo.codigos()) == OBRIGATORIOS


def test_todo_codigo_tem_ao_menos_3_sinonimos(catalogo: Catalogo) -> None:
    pobres = [i.codigo for i in catalogo.itens if len(i.sinonimos) < 3]
    assert pobres == []


def test_todos_os_grupos_sao_usados(catalogo: Catalogo) -> None:
    usados = {i.grupo for i in catalogo.itens}
    assert usados == set(catalogo.grupos)


def test_sinonimos_globais_resolvem_para_o_codigo(catalogo: Catalogo) -> None:
    mapa = catalogo.sinonimos_globais()
    assert mapa["capatazia"] == "THC_DEST"
    assert mapa["dthc"] == "THC_DEST"
    assert mapa["sobreestadia"] == "DEMURRAGE"
    assert mapa["ajuste de combustivel"] == "BAF"
    assert mapa["premio de seguro"] == "AD_VALOREM_SEGURO"
    assert all(chave == normalizar(chave) for chave in mapa)


def test_get(catalogo: Catalogo) -> None:
    item = catalogo.get("THC_DEST")
    assert item.grupo == "destino"
    assert item.moeda_tipica == "BRL"
    with pytest.raises(KeyError):
        catalogo.get("NAO_EXISTE")


def test_modelos_sao_imutaveis(catalogo: Catalogo) -> None:
    with pytest.raises(ValidationError):
        catalogo.get("BAF").descricao = "outra"  # type: ignore[misc]


# ------------------------------------------------------------- normalizar


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Capatazia", "capatazia"),
        ("Desconsolidação", "desconsolidacao"),
        ("  THC   DEST ", "thc dest"),
        ("Prêmio de Seguro", "premio de seguro"),
        ("B/L Fee", "b/l fee"),
    ],
)
def test_normalizar(entrada: str, esperado: str) -> None:
    assert normalizar(entrada) == esperado


# ------------------------------------------------------------- validação


@pytest.mark.parametrize("codigo", ["thc_dest", "THC DEST", "THC-DEST", "_THC", "THC_", "1THC", ""])
def test_codigo_deve_ser_maiusculas_com_underscore(codigo: str) -> None:
    with pytest.raises(ValidationError):
        CodigoCusto.model_validate(_item(codigo))


def test_codigos_repetidos() -> None:
    with pytest.raises(ValidationError, match="códigos repetidos: BAF"):
        _montar(_item("BAF"), _item("BAF", sinonimos=("x", "y", "z")))


def test_grupo_inexistente() -> None:
    with pytest.raises(ValidationError, match="grupo inexistente: BAF → fantasma"):
        _montar(_item("BAF", grupo="fantasma"))


def test_sinonimo_em_dois_codigos_lista_o_conflito() -> None:
    with pytest.raises(ValidationError) as erro:
        _montar(
            _item("AAA", sinonimos=("Desconsolidação", "x", "y")),
            _item("BBB", sinonimos=("DESCONSOLIDACAO", "z", "w")),
        )
    mensagem = str(erro.value)
    assert "'desconsolidacao' → AAA e BBB" in mensagem


def test_mesmo_sinonimo_repetido_no_mesmo_codigo_e_aceito() -> None:
    catalogo = _montar(_item("AAA", sinonimos=("Taxa", "taxa", "TAXA")))
    assert catalogo.sinonimos_globais() == {"taxa": "AAA"}


def test_grupos_repetidos() -> None:
    with pytest.raises(ValidationError, match="grupos repetidos: g"):
        _montar(_item("AAA"), grupos=("g", "g"))
