"""Processos sintéticos: cotas, fornecedores coerentes, referências únicas e o mundo salvo."""

import json
import random
import re
import uuid
from collections import Counter
from datetime import date
from pathlib import Path

import pytest

from confere_core.costcode.catalogo import Catalogo
from confere_core.validators import iso6346
from confere_synth.modelos import Cliente, Fornecedor, Mundo, Processo
from confere_synth.mundo import (
    ETD_FIM,
    ETD_INICIO,
    _novo,
    gerar_clientes,
    gerar_fornecedores,
    gerar_mundo,
    gerar_processos,
    salvar_mundo,
)

YAML = Path(__file__).resolve().parents[3] / "config" / "codigos_custo.yaml"
ORIGENS = {"CNSHA", "CNNGB", "CNSZX", "NLRTM", "DEHAM", "BEANR", "ESVLC"}
DESTINOS = {"BRFOR", "BRPEC", "BRSUA", "BRSSZ"}
TERMINAL = {
    "BRFOR": "terminal-mar-azul",
    "BRPEC": "terminal-cajueiro-pecem",
    "BRSUA": "terminal-mare-alta-suape",
}


@pytest.fixture(scope="module")
def catalogo() -> Catalogo:
    return Catalogo.carregar(YAML)


@pytest.fixture(scope="module")
def mundo(catalogo: Catalogo) -> Mundo:
    return gerar_mundo(42, catalogo)


@pytest.fixture(scope="module")
def processos(mundo: Mundo) -> list[Processo]:
    return mundo.processos


@pytest.fixture(scope="module")
def forn(mundo: Mundo) -> dict[str, Fornecedor]:
    return {f.id: f for f in mundo.fornecedores}


def refs(p: Processo, tipo: str) -> list[str]:
    return [r.valor for r in p.referencias if r.tipo == tipo]


# ------------------------------------------------------------- identidade


def test_cinquenta_processos_com_codigos_sequenciais(processos: list[Processo]) -> None:
    assert [p.codigo for p in processos] == [f"IMP-2026-{i:04d}" for i in range(1, 51)]


def test_ids_sao_uuid_v4_distintos(processos: list[Processo]) -> None:
    assert len({p.id for p in processos}) == 50
    assert all(isinstance(p.id, uuid.UUID) and p.id.version == 4 for p in processos)


def test_clientes_existem(processos: list[Processo], mundo: Mundo) -> None:
    ids = {c.id for c in mundo.clientes}
    assert {p.cliente_id for p in processos} <= ids


# ------------------------------------------------------------------ cotas


def test_cotas_de_modal_e_trecho_rodoviario(processos: list[Processo]) -> None:
    modais = Counter(p.modal for p in processos)
    assert modais == {"maritimo": 42, "rodoviario": 8}
    maritimos_com_trecho = [p for p in processos if p.modal == "maritimo" and p.transportadora_id]
    assert len(maritimos_com_trecho) == 13  # 30% de 42, arredondado
    assert all(p.transportadora_id for p in processos if p.modal == "rodoviario")


@pytest.mark.parametrize("n", [1, 5, 20, 100])
def test_cotas_valem_para_outros_tamanhos(n: int, catalogo: Catalogo) -> None:
    rng = random.Random(3)
    forns = gerar_fornecedores(rng, catalogo)
    procs = gerar_processos(rng, gerar_clientes(rng), forns, n=n)
    assert len(procs) == n
    rod = sum(p.modal == "rodoviario" for p in procs)
    assert rod == round(n * 0.15)


# ------------------------------------------------------------ rotas e datas


def test_portos_e_datas(processos: list[Processo]) -> None:
    for p in processos:
        assert p.destino_locode in DESTINOS
        assert ETD_INICIO <= p.etd <= ETD_FIM
        dias = (p.eta - p.etd).days
        if p.modal == "maritimo":
            assert p.origem_locode in ORIGENS
            assert 25 <= dias <= 45
        else:
            assert p.origem_locode in DESTINOS and p.origem_locode != p.destino_locode
            assert 2 <= dias <= 7
    assert date(2026, 8, 1) == ETD_INICIO and date(2026, 10, 15) == ETD_FIM


def test_navio_e_viagem(processos: list[Processo]) -> None:
    for p in processos:
        if p.modal == "maritimo":
            assert p.navio and p.navio.startswith("MV ")
            assert p.viagem and re.fullmatch(r"\d{3}[WE]", p.viagem)
        else:
            assert p.navio is None and p.viagem is None


# ------------------------------------------------------------ fornecedores


def test_fornecedores_do_tipo_certo(processos: list[Processo], forn: dict[str, Fornecedor]) -> None:
    for p in processos:
        assert forn[p.despachante_id].tipo == "despachante"
        assert forn[p.armazem_id or ""].tipo == "armazem"
        if p.transportadora_id:
            assert forn[p.transportadora_id].tipo == "transportadora"
        if p.modal == "maritimo":
            assert forn[p.armador_id or ""].tipo == "armador"
            assert forn[p.agente_exterior_id or ""].tipo == "agente_exterior"
        else:
            assert p.armador_id is None and p.agente_exterior_id is None
            assert p.terminal_id is None


def test_agente_coerente_com_a_origem(
    processos: list[Processo], forn: dict[str, Fornecedor]
) -> None:
    for p in processos:
        if p.modal == "maritimo":
            esperado = "CN" if p.origem_locode.startswith("CN") else "DE"
            assert forn[p.agente_exterior_id or ""].pais == esperado


def test_terminal_conforme_o_porto_de_destino(processos: list[Processo]) -> None:
    for p in processos:
        if p.modal == "maritimo":
            assert p.terminal_id == TERMINAL.get(p.destino_locode)  # Santos: None


def test_todos_os_tipos_de_fornecedor_aparecem(
    processos: list[Processo], forn: dict[str, Fornecedor]
) -> None:
    usados = {
        i
        for p in processos
        for i in (
            p.armador_id, p.agente_exterior_id, p.terminal_id,
            p.armazem_id, p.despachante_id, p.transportadora_id,
        )
        if i
    }  # fmt: skip
    assert {forn[i].tipo for i in usados} == {
        "armador", "agente_exterior", "terminal", "armazem", "transportadora", "despachante"
    }  # fmt: skip


# -------------------------------------------------------------- referências


def test_bl_master(processos: list[Processo], forn: dict[str, Fornecedor]) -> None:
    prefixos = {"atlantida-ocean-lines": "ATLX", "boreal-container-line": "BORX",
                "tarquin-marine-lines": "TARX"}  # fmt: skip
    for p in processos:
        masters = refs(p, "bl_master")
        if p.modal == "maritimo":
            assert len(masters) == 1
            assert re.fullmatch(r"[A-Z]{3}X\d{9}", masters[0])
            assert masters[0].startswith(prefixos[p.armador_id or ""])
        else:
            assert masters == []


def test_demais_referencias(processos: list[Processo]) -> None:
    com_agente = 0
    for p in processos:
        hbls = refs(p, "bl_house")
        assert 1 <= len(hbls) <= 2
        assert all(re.fullmatch(rf"HBL-{p.destino_locode[2:]}-\d{{6}}", h) for h in hbls)
        conteineres = refs(p, "conteiner")
        assert 1 <= len(conteineres) <= 4
        assert all(iso6346.valido(c) for c in conteineres)
        clientes = refs(p, "ref_cliente")
        assert len(clientes) == 1 and re.fullmatch(r"PO-\d{5}|PEDIDO \d{5}", clientes[0])
        agentes = refs(p, "ref_agente")
        assert len(agentes) <= 1
        assert all(re.fullmatch(r"AGT-2026-\d{5}", a) for a in agentes)
        com_agente += len(agentes)
    assert 0 < com_agente < 42  # só em parte dos marítimos


def test_ref_cliente_nos_dois_formatos(processos: list[Processo]) -> None:
    formatos = {
        r.split("-")[0] if r.startswith("PO") else "PEDIDO"
        for p in processos
        for r in refs(p, "ref_cliente")
    }
    assert formatos == {"PO", "PEDIDO"}


def test_nenhum_valor_de_referencia_se_repete(processos: list[Processo]) -> None:
    valores = [r.valor for p in processos for r in p.referencias]
    assert len(valores) == len(set(valores))
    assert len(valores) > 150


def test_novo_regera_em_colisao() -> None:
    sequencia = iter(["a", "a", "b", "c"])
    usados = {"a"}
    assert _novo(usados, lambda: next(sequencia)) == "b"
    assert usados == {"a", "b"}
    assert _novo(usados, lambda: next(sequencia)) == "c"


# ------------------------------------------------------- mundo e persistência


def test_mundo_completo(mundo: Mundo) -> None:
    assert (len(mundo.fornecedores), len(mundo.clientes), len(mundo.processos)) == (14, 12, 50)
    assert mundo.provisoes == [] and mundo.seed == 42


def test_determinismo(catalogo: Catalogo) -> None:
    assert gerar_mundo(42, catalogo) == gerar_mundo(42, catalogo)
    a, b = gerar_mundo(1, catalogo), gerar_mundo(2, catalogo)
    assert [p.id for p in a.processos] != [p.id for p in b.processos]


def test_catalogo_padrao_e_o_do_repositorio() -> None:
    assert gerar_mundo(7) == gerar_mundo(7, Catalogo.carregar(YAML))


def test_salvar_mundo(mundo: Mundo, tmp_path: Path) -> None:
    arquivo = salvar_mundo(mundo, tmp_path / "saida" / "seed42")
    assert arquivo.name == "mundo.json"
    texto = arquivo.read_text(encoding="utf-8")
    assert texto.endswith("}\n") and not texto.endswith("\n\n")
    assert texto.startswith('{\n  "clientes": [')  # chaves ordenadas, indentação 2
    dados = json.loads(texto)
    assert list(dados) == sorted(dados)
    assert texto == json.dumps(dados, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    assert Mundo.model_validate_json(texto) == mundo


def test_salvar_mundo_e_identico_entre_execucoes(catalogo: Catalogo, tmp_path: Path) -> None:
    a = salvar_mundo(gerar_mundo(42, catalogo), tmp_path / "a").read_bytes()
    b = salvar_mundo(gerar_mundo(42, catalogo), tmp_path / "b").read_bytes()
    assert a == b


def test_clientes_tipados(mundo: Mundo) -> None:
    assert all(isinstance(c, Cliente) for c in mundo.clientes)
