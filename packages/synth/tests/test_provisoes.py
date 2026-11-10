"""Custos típicos e provisões sintéticas."""

import math
import random
import uuid
from collections import Counter, defaultdict
from decimal import Decimal
from itertools import combinations
from pathlib import Path
from typing import Any

import pytest
import yaml

from confere_core.costcode.catalogo import Catalogo
from confere_synth.custos import CustosTipicos
from confere_synth.modelos import Fornecedor, Mundo, Processo, Provisao
from confere_synth.mundo import gerar_mundo, gerar_provisoes, salvar_mundo

RAIZ = Path(__file__).resolve().parents[3]
YAML_CATALOGO = RAIZ / "config" / "codigos_custo.yaml"
YAML_CUSTOS = RAIZ / "config" / "custos_tipicos.yaml"


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    return Catalogo.carregar(YAML_CATALOGO)


@pytest.fixture(scope="module")
def custos(catalogo: Catalogo) -> CustosTipicos:
    return CustosTipicos.carregar(YAML_CUSTOS, catalogo)


@pytest.fixture(scope="module")
def mundo(catalogo: Catalogo) -> Mundo:
    return gerar_mundo(42, catalogo)


@pytest.fixture(scope="module")
def por_processo(mundo: Mundo) -> dict[uuid.UUID, list[Provisao]]:
    grupos: dict[uuid.UUID, list[Provisao]] = defaultdict(list)
    for p in mundo.provisoes:
        grupos[p.processo_id].append(p)
    return grupos


# ------------------------------------------------------------ configuração


def test_cobre_os_30_codigos_com_unidade_do_catalogo(
    custos: CustosTipicos, catalogo: Catalogo
) -> None:
    assert set(custos.codigos) == set(catalogo.codigos()) and len(custos.codigos) == 30
    assert all(c.unidade == catalogo.get(k).unidade for k, c in custos.codigos.items())


def test_valores_de_referencia(custos: CustosTipicos) -> None:
    c = custos.codigos
    assert (c["FRETE_MAR"].moeda, c["FRETE_MAR"].base) == ("USD", Decimal(1800))
    assert (c["THC_ORIG"].moeda, c["THC_ORIG"].base) == ("USD", Decimal(180))
    assert (c["THC_DEST"].moeda, c["THC_DEST"].base) == ("BRL", Decimal(1350))
    assert (c["BL_FEE"].moeda, c["BL_FEE"].base) == ("USD", Decimal(75))
    assert (c["DESCONSOLIDACAO"].moeda, c["DESCONSOLIDACAO"].base) == ("BRL", Decimal(420))
    assert c["SISCOMEX"].base == Decimal("154.23")
    assert c["HONORARIO_DESPACHO"].base == Decimal(850)
    assert c["FRETE_RODO"].base == Decimal(2900)
    assert (c["ARMAZENAGEM"].base, c["ARMAZENAGEM"].percentual_de) == (Decimal("0.35"), "cif")
    assert c["ARMAZENAGEM"].minimo == Decimal(950)
    assert (c["AFRMM"].base, c["AFRMM"].percentual_de) == (Decimal(8), "FRETE_MAR")
    assert c["DEMURRAGE"].prob == 0.1


def _yaml_com(alteracao: dict[str, Any]) -> dict[str, Any]:
    dados: dict[str, Any] = yaml.safe_load(YAML_CUSTOS.read_text(encoding="utf-8"))
    dados["codigos"]["BAF"].update(alteracao)
    return dados


@pytest.mark.parametrize(
    ("alteracao", "mensagem"),
    [
        ({"unidade": "por_bl"}, "BAF: unidade por_bl difere do catálogo"),
        ({"moeda": "JPY"}, "BAF: moeda JPY sem cambio_referencia"),
        ({"unidade": "percentual"}, "unidade percentual exige percentual_de"),
        ({"percentual_de": "NAO_EXISTE"}, "percentual_de aponta para código inexistente"),
        ({"percentual_de": "CAF"}, "não pode apontar para outro percentual"),
        ({"minimo": 10}, "minimo só vale com percentual_de"),
    ],
)
def test_config_invalida(alteracao: dict[str, Any], mensagem: str, catalogo: Catalogo) -> None:
    with pytest.raises(ValueError, match=mensagem):
        CustosTipicos.model_validate(_yaml_com(alteracao)).validar(catalogo)


def test_codigo_base_precisa_de_prob_1(catalogo: Catalogo) -> None:
    dados = yaml.safe_load(YAML_CUSTOS.read_text(encoding="utf-8"))
    dados["codigos"]["FRETE_MAR"]["prob"] = 0.9
    with pytest.raises(ValueError, match=r"código-base FRETE_MAR precisa de prob 1\.0"):
        CustosTipicos.model_validate(dados).validar(catalogo)


def test_codigo_faltando_ou_sobrando(catalogo: Catalogo) -> None:
    dados = yaml.safe_load(YAML_CUSTOS.read_text(encoding="utf-8"))
    del dados["codigos"]["PSS"]
    dados["codigos"]["XYZ"] = dados["codigos"]["BAF"]
    with pytest.raises(ValueError) as erro:
        CustosTipicos.model_validate(dados).validar(catalogo)
    assert "sem custo típico: ['PSS']" in str(erro.value) and "fora do catálogo: ['XYZ']" in str(
        erro.value
    )


# ----------------------------------------------------------------- provisões


def test_forma_basica(mundo: Mundo) -> None:
    provs = mundo.provisoes
    assert len({p.id for p in provs}) == len(provs) > 400
    assert all(p.status == "aberta" for p in provs)
    assert all(isinstance(p.valor, Decimal) and p.valor > 0 for p in provs)
    assert all(p.valor == p.valor.quantize(Decimal("0.01")) for p in provs)
    assert {p.processo_id for p in provs} == {p.id for p in mundo.processos}


def test_faixas_por_modal(mundo: Mundo, por_processo: dict[uuid.UUID, list[Provisao]]) -> None:
    for proc in mundo.processos:
        n = len(por_processo[proc.id])
        faixa = (8, 15) if proc.modal == "maritimo" else (6, 8)
        assert faixa[0] <= n <= faixa[1], (proc.codigo, n)


def test_fornecedor_ligado_ao_processo_e_cobra_o_codigo(
    mundo: Mundo, por_processo: dict[uuid.UUID, list[Provisao]]
) -> None:
    forn = {f.id: f for f in mundo.fornecedores}
    for proc in mundo.processos:
        ligados = {
            i
            for i in (
                proc.armador_id, proc.agente_exterior_id, proc.terminal_id,
                proc.armazem_id, proc.despachante_id, proc.transportadora_id,
            )
            if i
        }  # fmt: skip
        for p in por_processo[proc.id]:
            assert p.fornecedor_id in ligados, (proc.codigo, p.codigo_custo)
            assert p.codigo_custo in forn[p.fornecedor_id].codigos


def test_codigo_unico_por_processo_e_moeda_da_config(
    mundo: Mundo, por_processo: dict[uuid.UUID, list[Provisao]], custos: CustosTipicos
) -> None:
    for provs in por_processo.values():
        codigos = [p.codigo_custo for p in provs]
        assert len(codigos) == len(set(codigos))
        assert all(p.moeda == custos.codigos[p.codigo_custo].moeda for p in provs)


def test_obrigatorios_e_ausencias_por_modal(
    mundo: Mundo, por_processo: dict[uuid.UUID, list[Provisao]]
) -> None:
    for proc in mundo.processos:
        codigos = {p.codigo_custo for p in por_processo[proc.id]}
        assert {"HONORARIO_DESPACHO", "SISCOMEX"} <= codigos
        if proc.transportadora_id:
            assert "FRETE_RODO" in codigos
        else:
            assert not codigos & {"FRETE_RODO", "PEDAGIO", "GRIS", "AD_VALOREM_SEGURO"}
        if proc.modal == "maritimo":
            assert "FRETE_MAR" in codigos
            assert ("THC_DEST" in codigos) == (proc.terminal_id is not None)
        else:
            assert not codigos & {"FRETE_MAR", "AFRMM", "CAF", "BAF", "PSS", "THC_ORIG"}


def test_valores_plausiveis(mundo: Mundo, por_processo: dict[uuid.UUID, list[Provisao]]) -> None:
    n_cntr = {p.id: sum(r.tipo == "conteiner" for r in p.referencias) for p in mundo.processos}
    unitarios = [
        p.valor / n_cntr[p.processo_id] for p in mundo.provisoes if p.codigo_custo == "FRETE_MAR"
    ]
    assert Decimal(1200) < sorted(unitarios)[len(unitarios) // 2] < Decimal(2500)
    siscomex = {p.valor for p in mundo.provisoes if p.codigo_custo == "SISCOMEX"}
    assert siscomex == {Decimal("154.23")}  # sem ruído


def test_afrmm_e_8_por_cento_do_frete(por_processo: dict[uuid.UUID, list[Provisao]]) -> None:
    visto = 0
    for provs in por_processo.values():
        por_codigo = {p.codigo_custo: p.valor for p in provs}
        if "AFRMM" in por_codigo:
            esperado = por_codigo["FRETE_MAR"] * Decimal("5.40") * Decimal("0.08")
            assert abs(por_codigo["AFRMM"] / esperado - 1) < Decimal("0.12")
            visto += 1
    assert visto > 10


def test_armazenagem_respeita_o_minimo(mundo: Mundo) -> None:
    valores = [p.valor for p in mundo.provisoes if p.codigo_custo == "ARMAZENAGEM"]
    assert valores and min(valores) > Decimal(950) * Decimal("0.4")  # mínimo 950 com ruído


# ---------------------------------------------------------- pares próximos


def _tem_par(provs: list[Provisao]) -> bool:
    return any(
        a.fornecedor_id == b.fornecedor_id
        and a.moeda == b.moeda
        and a.codigo_custo != b.codigo_custo
        and max(a.valor, b.valor) / min(a.valor, b.valor) <= Decimal("1.12")
        for a, b in combinations(provs, 2)
    )


@pytest.mark.parametrize("semente", [42, 1, 2, 3])
def test_ao_menos_20_por_cento_com_par_proximo(semente: int, catalogo: Catalogo) -> None:
    m = gerar_mundo(semente, catalogo)
    grupos: dict[uuid.UUID, list[Provisao]] = defaultdict(list)
    for p in m.provisoes:
        grupos[p.processo_id].append(p)
    com_par = sum(_tem_par(provs) for provs in grupos.values())
    assert com_par >= math.ceil(0.20 * len(m.processos))
    assert com_par >= math.ceil(0.25 * len(m.processos))  # a meta do gerador


def test_pares_forcados_nao_sao_valores_identicos(
    por_processo: dict[uuid.UUID, list[Provisao]],
) -> None:
    for provs in por_processo.values():
        for a, b in combinations(provs, 2):
            if a.fornecedor_id == b.fornecedor_id and a.moeda == b.moeda:
                assert a.valor != b.valor or a.codigo_custo == b.codigo_custo


# ------------------------------------------------------- determinismo e uso


def test_determinismo(catalogo: Catalogo) -> None:
    assert gerar_mundo(42, catalogo).provisoes == gerar_mundo(42, catalogo).provisoes
    assert gerar_mundo(1, catalogo).provisoes != gerar_mundo(2, catalogo).provisoes


def test_gerar_provisoes_direto(mundo: Mundo, catalogo: Catalogo) -> None:
    rng = random.Random(5)
    provs = gerar_provisoes(rng, mundo.processos[:10], mundo.fornecedores, catalogo)
    assert {p.processo_id for p in provs} == {p.id for p in mundo.processos[:10]}
    assert gerar_provisoes(random.Random(5), [], mundo.fornecedores, catalogo) == []


def test_processo_sem_candidatos_suficientes_falha_claro(mundo: Mundo, catalogo: Catalogo) -> None:
    sem_vinculos = {
        "armador_id": None,
        "agente_exterior_id": None,
        "terminal_id": None,
        "armazem_id": None,
        "transportadora_id": None,
    }
    proc: Processo = mundo.processos[0].model_copy(update=sem_vinculos)
    with pytest.raises(ValueError, match="códigos possíveis"):
        gerar_provisoes(random.Random(1), [proc], mundo.fornecedores, catalogo)


def test_fornecedor_ausente_falha_claro(mundo: Mundo, catalogo: Catalogo) -> None:
    forn: list[Fornecedor] = [f for f in mundo.fornecedores if f.tipo == "despachante"]
    with pytest.raises(ValueError, match="fornecedor ausente"):
        gerar_provisoes(random.Random(1), mundo.processos[:1], forn, catalogo)


def test_distribuicao_de_codigos(mundo: Mundo) -> None:
    contagem = Counter(p.codigo_custo for p in mundo.provisoes)
    assert contagem["FRETE_MAR"] == 42 and contagem["HONORARIO_DESPACHO"] == 50
    assert contagem["DEMURRAGE"] < contagem["BAF"]


def test_mundo_salvo_com_provisoes_ida_e_volta(mundo: Mundo, tmp_path: Path) -> None:
    arquivo = salvar_mundo(mundo, tmp_path)
    assert Mundo.model_validate_json(arquivo.read_text(encoding="utf-8")) == mundo
