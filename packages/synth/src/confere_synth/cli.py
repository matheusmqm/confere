"""CLI do gerador sintético.

    python -m confere_synth.cli faturas --seed 42 --saida data/seed42
    python -m confere_synth.cli ctes    --seed 42 --saida data/seed42
    python -m confere_synth.cli ruido   --seed 42 --saida data/seed42
    python -m confere_synth.cli compostos --seed 42 --saida data/seed42

- `faturas`: gera o mundo (determinístico no seed), as faturas e extratos limpos e renderiza os
  PDFs em `<saida>/documentos/`. Grava `mundo.json`, `documentos.json` e `manifest.json`.
- `ctes`: CT-e 4.00 (XML) das transportadoras e o DACTE (PDF, fora do lote por padrão).
- `ruido`: aplica "foto de celular" a ~15% dos PDFs (rode depois de `faturas`).
- `compostos`: 3 PDFs fatura + BL com `cortes_esperados` no manifest (rode depois de `faturas`).

Todos preservam no `manifest.json` as chaves que outras etapas já gravaram, e `documentos.json`
é mesclado: cada comando troca só os documentos dos tipos que ele gera.
"""

import argparse
import hashlib
import json
import random
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import Any

from confere_core.costcode.catalogo import Catalogo
from confere_synth import compostos, cte, faturas, ruido
from confere_synth.modelos import DocumentoSintetico
from confere_synth.mundo import gerar_mundo, salvar_mundo

RAIZ = Path(__file__).resolve().parents[4]
CATALOGO_PADRAO = RAIZ / "config" / "codigos_custo.yaml"
SAIDA_PADRAO = RAIZ / "data" / "seed42"


def _gravar_json(caminho: Path, dados: Any) -> str:
    texto = json.dumps(dados, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    caminho.write_text(texto, encoding="utf-8", newline="\n")
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _ler_json(caminho: Path, padrao: Any) -> Any:
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else padrao


def _mesclar_documentos(
    saida: Path,
    manifest: dict[str, Any],
    novos: list[DocumentoSintetico],
    manter: Callable[[dict[str, Any]], bool],
) -> None:
    """Regrava `documentos.json` com os existentes que `manter` aceita mais os `novos`."""
    docs: list[dict[str, Any]] = [
        d for d in _ler_json(saida / "documentos.json", []) if manter(d)
    ] + [d.model_dump(mode="json") for d in novos]
    docs.sort(key=lambda d: (d["tipo"], d["fornecedor_id"], d["emissao"], d["numero"], d["id"]))
    sha = _gravar_json(saida / "documentos.json", docs)
    manifest["documentos"] = {
        "arquivo": "documentos.json",
        "sha256": sha,
        "total": len(docs),
        "por_tipo": dict(sorted(Counter(d["tipo"] for d in docs).items())),
    }


def _registrar_mundo(saida: Path, manifest: dict[str, Any], seed: int, mundo: Any) -> None:
    arquivo = salvar_mundo(mundo, saida)
    manifest["seed"] = seed
    manifest["mundo"] = {
        "arquivo": arquivo.name,
        "sha256": hashlib.sha256(arquivo.read_bytes()).hexdigest(),
    }


def comando_faturas(seed: int, saida: Path, catalogo_path: Path = CATALOGO_PADRAO) -> int:
    catalogo = Catalogo.carregar(catalogo_path)
    mundo = gerar_mundo(seed, catalogo)
    documentos = faturas.gerar_documentos_limpos(random.Random(f"{seed}:faturas"), mundo, catalogo)

    try:
        com_hash = []
        for doc in documentos:
            caminho = faturas.renderizar(doc, saida)
            com_hash.append(doc.model_copy(update={"sha256": faturas.sha256_de(caminho)}))
    except faturas.WeasyPrintIndisponivelError as erro:
        print(
            f"WeasyPrint indisponível (faltam bibliotecas do sistema, veja docs/setup.md): {erro}",
            file=sys.stderr,
        )
        return 1

    saida.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = _ler_json(saida / "manifest.json", {})
    _registrar_mundo(saida, manifest, seed, mundo)
    _mesclar_documentos(saida, manifest, com_hash, manter=lambda d: d["tipo"] == "cte")
    manifest["pdfs"] = [
        {
            "arquivo": d.arquivo,
            "sha256": d.sha256,
            "id": str(d.id),
            "tipo": d.tipo,
            "fornecedor_id": d.fornecedor_id,
            "numero": d.numero,
        }
        for d in sorted(com_hash, key=lambda d: d.arquivo or "")
    ]
    _gravar_json(saida / "manifest.json", manifest)
    print(f"{len(com_hash)} documentos em {saida / 'documentos'}")
    return 0


def comando_ctes(seed: int, saida: Path, catalogo_path: Path = CATALOGO_PADRAO) -> int:
    catalogo = Catalogo.carregar(catalogo_path)
    mundo = gerar_mundo(seed, catalogo)
    gerados = cte.gerar_ctes(random.Random(f"{seed}:ctes"), mundo)

    invalidos = {g.documento.numero: erros for g in gerados if (erros := cte.validar_xml(g.xml))}
    if invalidos:
        print(f"XML de CT-e inválido no XSD: {invalidos}", file=sys.stderr)
        return 2

    saida.mkdir(parents=True, exist_ok=True)
    docs, xmls, dactes = [], [], []
    for g in gerados:
        caminho = cte.gravar_xml(g, saida)
        sha = faturas.sha256_de(caminho)
        pdf = cte.gerar_dacte(caminho, saida / f"documentos/{g.documento.id}_dacte.pdf")
        docs.append(g.documento.model_copy(update={"sha256": sha}))
        xmls.append(
            {
                "arquivo": g.documento.arquivo,
                "sha256": sha,
                "id": str(g.documento.id),
                "tipo": "cte",
                "fornecedor_id": g.documento.fornecedor_id,
                "numero": g.documento.numero,
                "chave_acesso": g.chave,
            }
        )
        dactes.append(
            {
                "arquivo": pdf.relative_to(saida).as_posix(),
                "sha256": faturas.sha256_de(pdf),
                "tipo": "dacte",
                "origem_xml": str(g.documento.id),
                "incluir_no_lote": False,  # o pipeline usa o XML; o DACTE é só para exibir
            }
        )

    manifest: dict[str, Any] = _ler_json(saida / "manifest.json", {})
    _registrar_mundo(saida, manifest, seed, mundo)
    _mesclar_documentos(saida, manifest, docs, manter=lambda d: d["tipo"] != "cte")
    manifest["xmls"] = sorted(xmls, key=lambda x: x["arquivo"])
    manifest["dactes"] = sorted(dactes, key=lambda x: x["arquivo"])
    _gravar_json(saida / "manifest.json", manifest)
    print(f"{len(docs)} CT-e (XML) e {len(dactes)} DACTE em {saida / 'documentos'}")
    return 0


def comando_ruido(seed: int, saida: Path) -> int:
    if not (saida / "manifest.json").exists():
        print("manifest.json não existe: rode `faturas` antes de `ruido`.", file=sys.stderr)
        return 1
    escolhidos = ruido.aplicar_ruido_ao_lote(random.Random(f"{seed}:ruido"), saida)
    print(f"{len(escolhidos)} documentos com ruído de foto de celular")
    return 0


def comando_compostos(seed: int, saida: Path, catalogo_path: Path = CATALOGO_PADRAO) -> int:
    caminho_manifest = saida / "manifest.json"
    if not caminho_manifest.exists():
        print("manifest.json não existe: rode `faturas` antes de `compostos`.", file=sys.stderr)
        return 1
    catalogo = Catalogo.carregar(catalogo_path)
    mundo = gerar_mundo(seed, catalogo)
    documentos = faturas.gerar_documentos_limpos(random.Random(f"{seed}:faturas"), mundo, catalogo)
    planos = compostos.gerar_compostos(random.Random(f"{seed}:compostos"), mundo, documentos)

    manifest: dict[str, Any] = _ler_json(caminho_manifest, {})
    for antigo in manifest.get("compostos", []):  # refazer não deixa composto antigo para trás
        (saida / antigo["arquivo"]).unlink(missing_ok=True)
    try:
        entradas = [compostos.gravar_composto(plano, saida) for plano in planos]
    except FileNotFoundError as erro:
        print(erro, file=sys.stderr)
        return 1
    except faturas.WeasyPrintIndisponivelError as erro:
        print(f"WeasyPrint indisponível (veja docs/setup.md): {erro}", file=sys.stderr)
        return 1
    manifest["compostos"] = sorted(entradas, key=lambda e: e["arquivo"])
    _gravar_json(caminho_manifest, manifest)
    print(f"{len(entradas)} PDFs compostos (fatura + BL) em {saida / 'documentos'}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="confere_synth.cli", description=__doc__)
    sub = parser.add_subparsers(dest="comando", required=True)
    for nome, ajuda in (
        ("faturas", "gera faturas e extratos limpos em PDF"),
        ("ctes", "gera CT-e (XML) e DACTE (PDF)"),
        ("ruido", "aplica ruído de foto de celular a ~15% dos PDFs"),
        ("compostos", "gera PDFs com fatura + BL para testar a separação"),
    ):
        p = sub.add_parser(nome, help=ajuda)
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    args = parser.parse_args(argv)
    if args.comando == "faturas":
        return comando_faturas(args.seed, args.saida)
    if args.comando == "ctes":
        return comando_ctes(args.seed, args.saida)
    if args.comando == "compostos":
        return comando_compostos(args.seed, args.saida)
    return comando_ruido(args.seed, args.saida)


if __name__ == "__main__":
    raise SystemExit(main())
