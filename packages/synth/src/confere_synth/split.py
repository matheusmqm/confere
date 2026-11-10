"""Split treino/calibração/teste POR PROCESSO (CF-39).

Regras:

1. Os processos são embaralhados com o `rng` e divididos em 30% / 20% / 50% (15 / 10 / 25 para
   50 processos). Nenhum processo fica em dois conjuntos.
2. Um documento que cita mais de um processo (fatura de dois processos, extrato) pertence ao
   conjunto do processo de MENOR índice (posição em `mundo.processos`) e **todos** os processos
   dele são forçados para esse mesmo conjunto. Como isso encadeia (A junta B, B junta C), o
   forçamento vale para o componente conectado inteiro: movem-se processos inteiros, nunca se
   divide um componente.
3. O forçamento desequilibra os tamanhos. Para voltar perto de 15/10/25, os componentes
   (nunca divididos) são redistribuídos pela combinação de menor desvio total em relação à
   meta, preferindo mover poucos processos (busca exata, ver `_rebalancear`). Se um componente
   for maior que o conjunto, o desvio é inevitável. `rebalancear=False` desliga esse passo.
4. Todo documento vai para o conjunto de seus processos; duplicatas têm os mesmos processos do
   original e por isso caem no mesmo conjunto.

`split.json`: `{"seed", "processos": {conjunto: [ids]}, "documentos": {conjunto: [ids]}}`.
"""

import json
import random
import uuid
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from confere_synth.modelos import DocumentoSintetico, Processo

CONJUNTOS = ("treino", "calibracao", "teste")
PROPORCOES = (0.30, 0.20, 0.50)


class Split(BaseModel):
    model_config = ConfigDict(frozen=True)

    seed: int
    processos: dict[str, list[uuid.UUID]]
    documentos: dict[str, list[uuid.UUID]]

    def conjunto_do_processo(self, processo_id: uuid.UUID) -> str:
        for nome, ids in self.processos.items():
            if processo_id in ids:
                return nome
        raise KeyError(processo_id)

    def conjunto_do_documento(self, documento_id: uuid.UUID) -> str:
        for nome, ids in self.documentos.items():
            if documento_id in ids:
                return nome
        raise KeyError(documento_id)


def metas(n: int) -> dict[str, int]:
    """Tamanho-alvo de cada conjunto (treino e calibração arredondados; teste fica com o resto)."""
    treino = round(PROPORCOES[0] * n)
    calibracao = round(PROPORCOES[1] * n)
    return {"treino": treino, "calibracao": calibracao, "teste": n - treino - calibracao}


def _componentes(
    processos: Sequence[Processo], documentos: Sequence[DocumentoSintetico]
) -> list[list[uuid.UUID]]:
    """Processos ligados por documentos de vários processos (união-busca), em ordem de índice."""
    indice = {p.id: i for i, p in enumerate(processos)}
    pai = {p.id: p.id for p in processos}

    def raiz(x: uuid.UUID) -> uuid.UUID:
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    for doc in documentos:
        ids = {linha.processo_id for linha in doc.linhas if linha.processo_id}
        if doc.processo_id:
            ids.add(doc.processo_id)
        desconhecidos = ids - indice.keys()
        if desconhecidos:
            raise ValueError(f"documento {doc.numero} cita processo fora do mundo: {desconhecidos}")
        ordenados = sorted(ids, key=indice.__getitem__)
        for outro in ordenados[1:]:
            pai[raiz(outro)] = raiz(ordenados[0])

    grupos: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for p in processos:
        grupos[raiz(p.id)].append(p.id)
    return sorted(grupos.values(), key=lambda g: indice[g[0]])


def _desvio(tamanhos: dict[str, int], alvo: dict[str, int]) -> int:
    return sum(abs(tamanhos[c] - alvo[c]) for c in CONJUNTOS)


def _rebalancear(
    atribuicao: dict[int, str], componentes: list[list[uuid.UUID]], alvo: dict[str, int]
) -> None:
    """Redistribui componentes INTEIROS pela combinação de menor desvio total em relação à meta.

    É uma busca exata (programação dinâmica sobre os tamanhos de treino e calibração, o teste
    fica com o resto). No empate de desvio, prefere a que move menos processos em relação à
    atribuição da regra 2. Uma busca local simples não serviria: um componente maior que um
    conjunto (aqui, extratos e faturas juntadas encadeiam dezenas de processos) só melhora a
    soma depois de várias trocas.
    """
    total = sum(len(c) for c in componentes)
    inicial = dict(atribuicao)
    # (processos em treino, em calibração) -> (processos movidos, escolhas até aqui)
    estados: dict[tuple[int, int], tuple[int, list[str]]] = {(0, 0): (0, [])}
    for i, comp in enumerate(componentes):
        tam = len(comp)
        novos: dict[tuple[int, int], tuple[int, list[str]]] = {}
        for (a, b), (movidos, escolhas) in estados.items():
            for conjunto in CONJUNTOS:
                chave = (
                    a + (tam if conjunto == "treino" else 0),
                    b + (tam if conjunto == "calibracao" else 0),
                )
                custo = movidos + (0 if conjunto == inicial[i] else tam)
                if chave not in novos or custo < novos[chave][0]:
                    novos[chave] = (custo, [*escolhas, conjunto])
        estados = novos

    def qualidade(item: tuple[tuple[int, int], tuple[int, list[str]]]) -> tuple[int, int, int, int]:
        (a, b), (movidos, _) = item
        tamanhos = {"treino": a, "calibracao": b, "teste": total - a - b}
        return (_desvio(tamanhos, alvo), movidos, a, b)

    _, (_, escolhas) = min(estados.items(), key=qualidade)
    for i, conjunto in enumerate(escolhas):
        atribuicao[i] = conjunto


def gerar_split(
    rng: random.Random,
    seed: int,
    processos: Sequence[Processo],
    documentos: Sequence[DocumentoSintetico],
    *,
    rebalancear: bool = True,
) -> Split:
    """Split por processo; todo documento cai no conjunto de seus processos."""
    alvo = metas(len(processos))
    embaralhados = [p.id for p in processos]
    rng.shuffle(embaralhados)
    inicial: dict[uuid.UUID, str] = {}
    ordem_conjuntos = [c for c in CONJUNTOS for _ in range(alvo[c])]
    for pid, conjunto in zip(embaralhados, ordem_conjuntos, strict=True):
        inicial[pid] = conjunto

    componentes = _componentes(processos, documentos)
    # regra 2: o componente vai para o conjunto do processo de menor índice (o 1º de cada lista)
    atribuicao = {i: inicial[comp[0]] for i, comp in enumerate(componentes)}
    if rebalancear:
        _rebalancear(atribuicao, componentes, alvo)

    conjunto_do_processo = {
        pid: atribuicao[i] for i, comp in enumerate(componentes) for pid in comp
    }
    ordem = {p.id: i for i, p in enumerate(processos)}
    proc_por_conjunto: dict[str, list[uuid.UUID]] = {c: [] for c in CONJUNTOS}
    for p in processos:
        proc_por_conjunto[conjunto_do_processo[p.id]].append(p.id)

    docs_por_conjunto: dict[str, list[uuid.UUID]] = {c: [] for c in CONJUNTOS}
    for doc in documentos:
        ids = {linha.processo_id for linha in doc.linhas if linha.processo_id}
        if doc.processo_id:
            ids.add(doc.processo_id)
        if not ids:
            raise ValueError(f"documento {doc.numero} não cita nenhum processo")
        conjuntos = {conjunto_do_processo[pid] for pid in ids}
        if len(conjuntos) != 1:  # não deveria acontecer: o componente inteiro foi unificado
            menor = min(ids, key=ordem.__getitem__)
            raise AssertionError(f"documento {doc.numero} dividido; menor índice: {menor}")
        docs_por_conjunto[conjuntos.pop()].append(doc.id)

    return Split(seed=seed, processos=proc_por_conjunto, documentos=docs_por_conjunto)


def escrever_split(split: Split, saida: str | Path) -> Path:
    """Grava `split.json` (chaves ordenadas, indentação 2)."""
    pasta = Path(saida)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / "split.json"
    texto = json.dumps(split.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
    arquivo.write_text(texto + "\n", encoding="utf-8", newline="\n")
    return arquivo


def carregar_split(path: str | Path) -> Split:
    return Split.model_validate_json(Path(path).read_text(encoding="utf-8"))
