"""Split por processo, hash do dataset e suas regras."""

import hashlib
import json
import random
import uuid
from pathlib import Path

import pytest

from confere_core.costcode.catalogo import Catalogo
from confere_synth import cte, dataset, faturas
from confere_synth.modelos import DocumentoSintetico, Mundo
from confere_synth.mundo import gerar_mundo
from confere_synth.split import (
    CONJUNTOS,
    Split,
    _componentes,
    carregar_split,
    escrever_split,
    gerar_split,
    metas,
)

YAML = Path(__file__).resolve().parents[3] / "config" / "codigos_custo.yaml"


@pytest.fixture(scope="module")
def mundo() -> Mundo:
    return gerar_mundo(42, Catalogo.carregar(YAML))


@pytest.fixture(scope="module")
def docs(mundo: Mundo) -> list[DocumentoSintetico]:
    catalogo = Catalogo.carregar(YAML)
    limpos = faturas.gerar_documentos_limpos(random.Random("42:faturas"), mundo, catalogo)
    return limpos + [c.documento for c in cte.gerar_ctes(random.Random("42:ctes"), mundo)]


@pytest.fixture(scope="module")
def split(mundo: Mundo, docs: list[DocumentoSintetico]) -> Split:
    return gerar_split(random.Random(1), 42, mundo.processos, docs)


def processos_do(doc: DocumentoSintetico) -> set[uuid.UUID]:
    ids = {linha.processo_id for linha in doc.linhas if linha.processo_id}
    return ids | ({doc.processo_id} if doc.processo_id else set())


# --------------------------------------------------------------------- metas


@pytest.mark.parametrize(
    ("n", "esperado"),
    [(50, (15, 10, 25)), (10, (3, 2, 5)), (5, (2, 1, 2)), (1, (0, 0, 1)), (0, (0, 0, 0))],
)
def test_metas(n: int, esperado: tuple[int, int, int]) -> None:
    assert tuple(metas(n).values()) == esperado and sum(metas(n).values()) == n


# ------------------------------------------------------------------- processos


def test_tamanhos_15_10_25(split: Split) -> None:
    assert {c: len(split.processos[c]) for c in CONJUNTOS} == {
        "treino": 15, "calibracao": 10, "teste": 25,
    }  # fmt: skip


def test_cada_processo_em_exatamente_um_conjunto(mundo: Mundo, split: Split) -> None:
    todos = [pid for c in CONJUNTOS for pid in split.processos[c]]
    assert len(todos) == len(set(todos)) == 50
    assert set(todos) == {p.id for p in mundo.processos}


@pytest.mark.parametrize("semente", range(1, 11))
def test_tamanhos_ficam_perto_da_meta_em_varias_sementes(
    mundo: Mundo, docs: list[DocumentoSintetico], semente: int
) -> None:
    s = gerar_split(random.Random(semente), 42, mundo.processos, docs)
    alvo = metas(50)
    assert sum(len(v) for v in s.processos.values()) == 50
    assert all(abs(len(s.processos[c]) - alvo[c]) <= 3 for c in CONJUNTOS)


def test_sem_rebalancear_o_forcamento_desequilibra(
    mundo: Mundo, docs: list[DocumentoSintetico]
) -> None:
    s = gerar_split(random.Random(1), 42, mundo.processos, docs, rebalancear=False)
    assert {len(v) for v in s.processos.values()} != {15, 10, 25}  # por isso existe o passo 3


# ------------------------------------------------------------------ documentos


def test_todo_documento_vai_para_o_conjunto_de_seus_processos(
    docs: list[DocumentoSintetico], split: Split
) -> None:
    por_doc = {d: c for c in CONJUNTOS for d in split.documentos[c]}
    assert len(por_doc) == len(docs) == sum(len(v) for v in split.documentos.values())
    for doc in docs:
        conjuntos = {split.conjunto_do_processo(pid) for pid in processos_do(doc)}
        assert conjuntos == {por_doc[doc.id]}, doc.numero


def test_documentos_de_varios_processos_forcam_todos_ao_mesmo_conjunto(
    docs: list[DocumentoSintetico], split: Split
) -> None:
    multi = [d for d in docs if len(processos_do(d)) > 1]
    assert len(multi) >= 15  # faturas de 2 processos e os 3 extratos
    for doc in multi:
        assert len({split.conjunto_do_processo(pid) for pid in processos_do(doc)}) == 1
    extratos = [d for d in docs if d.tipo == "extrato"]
    assert extratos and all(len(processos_do(d)) >= 4 for d in extratos)


def test_componentes_encadeados_ficam_juntos(
    mundo: Mundo, docs: list[DocumentoSintetico], split: Split
) -> None:
    for comp in _componentes(mundo.processos, docs):
        assert len({split.conjunto_do_processo(pid) for pid in comp}) == 1


def test_sem_rebalancear_vale_o_conjunto_do_processo_de_menor_indice(
    mundo: Mundo, docs: list[DocumentoSintetico]
) -> None:
    s = gerar_split(random.Random(1), 42, mundo.processos, docs, rebalancear=False)
    ids = [p.id for p in mundo.processos]
    embaralhados = list(ids)
    random.Random(1).shuffle(embaralhados)
    alvo = metas(50)
    ordem = [c for c in CONJUNTOS for _ in range(alvo[c])]
    inicial = dict(zip(embaralhados, ordem, strict=True))
    for comp in _componentes(mundo.processos, docs):
        menor = comp[0]  # componentes vêm em ordem de índice
        assert {s.conjunto_do_processo(pid) for pid in comp} == {inicial[menor]}


def test_duplicata_fica_no_conjunto_do_original(
    mundo: Mundo, docs: list[DocumentoSintetico]
) -> None:
    original = next(d for d in docs if d.tipo == "fatura")
    copia = original.model_copy(update={"id": uuid.uuid4()})
    s = gerar_split(random.Random(1), 42, mundo.processos, [*docs, copia])
    assert s.conjunto_do_documento(copia.id) == s.conjunto_do_documento(original.id)


def test_documento_citando_processo_desconhecido_ou_nenhum(
    mundo: Mundo, docs: list[DocumentoSintetico]
) -> None:
    linha = docs[0].linhas[0].model_copy(update={"processo_id": uuid.uuid4()})
    estranho = docs[0].model_copy(update={"processo_id": None, "linhas": [linha]})
    with pytest.raises(ValueError, match="fora do mundo"):
        gerar_split(random.Random(1), 42, mundo.processos, [estranho])
    vazio = docs[0].model_copy(update={"processo_id": None, "linhas": []})
    with pytest.raises(ValueError, match="não cita nenhum processo"):
        gerar_split(random.Random(1), 42, mundo.processos, [vazio])


# -------------------------------------------------------------- determinismo


def test_determinismo(mundo: Mundo, docs: list[DocumentoSintetico], split: Split) -> None:
    assert gerar_split(random.Random(1), 42, mundo.processos, docs) == split
    assert gerar_split(random.Random(2), 42, mundo.processos, docs) != split


def test_mundo_pequeno(mundo: Mundo, docs: list[DocumentoSintetico]) -> None:
    pequeno = mundo.processos[:5]
    ids = {p.id for p in pequeno}
    so_dessas = [d for d in docs if processos_do(d) <= ids]
    s = gerar_split(random.Random(3), 7, pequeno, so_dessas)
    assert sum(len(v) for v in s.processos.values()) == 5 and s.seed == 7


# ------------------------------------------------------------------ split.json


def test_split_json(tmp_path: Path, split: Split) -> None:
    arquivo = escrever_split(split, tmp_path / "saida")
    assert arquivo.name == "split.json"
    texto = arquivo.read_text(encoding="utf-8")
    assert texto.endswith("}\n") and texto.startswith('{\n  "documentos": {')
    dados = json.loads(texto)
    assert list(dados) == ["documentos", "processos", "seed"] and dados["seed"] == 42
    assert set(dados["processos"]) == set(dados["documentos"]) == set(CONJUNTOS)
    assert carregar_split(arquivo) == split


def test_consultas_por_conjunto(split: Split) -> None:
    pid = split.processos["calibracao"][0]
    assert split.conjunto_do_processo(pid) == "calibracao"
    with pytest.raises(KeyError):
        split.conjunto_do_processo(uuid.uuid4())
    with pytest.raises(KeyError):
        split.conjunto_do_documento(uuid.uuid4())


# ----------------------------------------------------------- hash do dataset


def montar(raiz: Path) -> None:
    (raiz / "documentos").mkdir(parents=True)
    # bytes, não write_text: no Windows o write_text trocaria "\n" por "\r\n"
    (raiz / "mundo.json").write_bytes(b'{"m": 1}\n')
    (raiz / "gabarito.jsonl").write_bytes(b'{"g": 1}\n')
    (raiz / "split.json").write_bytes(b'{"s": 1}\n')
    (raiz / "manifest.json").write_bytes(b'{"seed": 42}\n')
    (raiz / "documentos" / "b.pdf").write_bytes(b"PDF-B")
    (raiz / "documentos" / "a.pdf").write_bytes(b"PDF-A")
    (raiz / "documentos" / "sub").mkdir()
    (raiz / "documentos" / "sub" / "c.xml").write_bytes(b"<c/>")


def test_hash_e_o_sha256_do_conteudo_em_ordem_de_nome(tmp_path: Path) -> None:
    montar(tmp_path)
    nomes = dataset.arquivos_do_dataset(tmp_path)
    assert nomes == [
        "documentos/a.pdf", "documentos/b.pdf", "documentos/sub/c.xml",
        "gabarito.jsonl", "manifest.json", "mundo.json", "split.json",
    ]  # fmt: skip
    esperado = hashlib.sha256(
        b"PDF-A" + b"PDF-B" + b"<c/>" + b'{"g": 1}\n'
        + b'{\n  "seed": 42\n}\n' + b'{"m": 1}\n' + b'{"s": 1}\n'
    ).hexdigest()  # fmt: skip
    assert dataset.calcular_hash(tmp_path) == esperado


def test_qualquer_mudanca_altera_o_hash(tmp_path: Path) -> None:
    montar(tmp_path)
    base = dataset.calcular_hash(tmp_path)
    (tmp_path / "documentos" / "a.pdf").write_bytes(b"PDF-A!")
    assert dataset.calcular_hash(tmp_path) != base
    (tmp_path / "documentos" / "a.pdf").write_bytes(b"PDF-A")
    assert dataset.calcular_hash(tmp_path) == base
    (tmp_path / "documentos" / "novo.pdf").write_bytes(b"x")
    assert dataset.calcular_hash(tmp_path) != base


def test_gravar_hash_e_estavel_apesar_de_o_manifest_guardar_o_hash(tmp_path: Path) -> None:
    montar(tmp_path)
    primeiro = dataset.gravar_hash(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_sha256"] == primeiro and manifest["seed"] == 42
    assert (tmp_path / "dataset.sha256").read_text(encoding="utf-8") == primeiro + "\n"
    assert dataset.calcular_hash(tmp_path) == primeiro  # o próprio hash não entra no cálculo
    assert dataset.gravar_hash(tmp_path) == primeiro  # idempotente


def test_arquivo_obrigatorio_ausente(tmp_path: Path) -> None:
    montar(tmp_path)
    (tmp_path / "gabarito.jsonl").unlink()
    with pytest.raises(FileNotFoundError, match=r"gabarito\.jsonl"):
        dataset.calcular_hash(tmp_path)


def test_dataset_sem_pasta_documentos(tmp_path: Path) -> None:
    montar(tmp_path)
    for p in sorted((tmp_path / "documentos").rglob("*"), reverse=True):
        p.unlink() if p.is_file() else p.rmdir()
    (tmp_path / "documentos").rmdir()
    assert len(dataset.arquivos_do_dataset(tmp_path)) == 4
