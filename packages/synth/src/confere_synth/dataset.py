"""Hash do dataset sintético (CF-39): uma impressão digital de tudo que o avalia.

`dataset.sha256` é o SHA-256 do conteúdo concatenado, em ordem de nome (caminho relativo, com
`/`), de `mundo.json`, `manifest.json`, `gabarito.jsonl`, `split.json` e de todos os arquivos
em `documentos/`. O manifest guarda o próprio hash (`dataset_sha256`); para não haver círculo,
ele entra no cálculo SEM essa chave, na forma canônica (chaves ordenadas, indentação 2).
"""

import hashlib
import json
from pathlib import Path
from typing import Any

ARQUIVOS_OBRIGATORIOS = ("mundo.json", "manifest.json", "gabarito.jsonl", "split.json")
CHAVE_NO_MANIFEST = "dataset_sha256"
ARQUIVO_HASH = "dataset.sha256"


def arquivos_do_dataset(saida: str | Path) -> list[str]:
    """Caminhos relativos (posix) dos arquivos que entram no hash, em ordem de nome."""
    raiz = Path(saida)
    ausentes = [a for a in ARQUIVOS_OBRIGATORIOS if not (raiz / a).is_file()]
    if ausentes:
        raise FileNotFoundError(f"arquivos do dataset ausentes em {raiz}: {ausentes}")
    nomes = list(ARQUIVOS_OBRIGATORIOS)
    documentos = raiz / "documentos"
    if documentos.is_dir():
        nomes += [p.relative_to(raiz).as_posix() for p in documentos.rglob("*") if p.is_file()]
    return sorted(nomes)


def _manifest_canonico(caminho: Path) -> bytes:
    manifest: dict[str, Any] = json.loads(caminho.read_text(encoding="utf-8"))
    manifest.pop(CHAVE_NO_MANIFEST, None)
    texto = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return texto.encode("utf-8")


def calcular_hash(saida: str | Path) -> str:
    raiz = Path(saida)
    h = hashlib.sha256()
    for nome in arquivos_do_dataset(raiz):
        caminho = raiz / nome
        h.update(_manifest_canonico(caminho) if nome == "manifest.json" else caminho.read_bytes())
    return h.hexdigest()


def gravar_hash(saida: str | Path) -> str:
    """Calcula o hash, grava `dataset.sha256` e `dataset_sha256` no manifest; devolve o hash."""
    raiz = Path(saida)
    valor = calcular_hash(raiz)
    (raiz / ARQUIVO_HASH).write_text(valor + "\n", encoding="utf-8", newline="\n")
    manifest: dict[str, Any] = json.loads((raiz / "manifest.json").read_text(encoding="utf-8"))
    manifest[CHAVE_NO_MANIFEST] = valor
    texto = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    (raiz / "manifest.json").write_text(texto, encoding="utf-8", newline="\n")
    return valor
