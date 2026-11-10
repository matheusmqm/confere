"""Exporta o OpenAPI da API em `apps/api/openapi.json`, sem subir servidor (CF-123).

Uso: `uv run python infra/scripts/dump_openapi.py [caminho]`. O arquivo é versionado: o CI roda
`make gen-api` e falha se `git diff` mostrar mudança (schema alterado sem regenerar o cliente).
Roda com `DEMO_MODE=true` para incluir as rotas `/demo/*` no contrato.
"""

import json
import os
import sys
from pathlib import Path

os.environ["DEMO_MODE"] = "true"
os.environ.setdefault("ENV", "test")

from confere_api.main import app

DESTINO_PADRAO = Path(__file__).resolve().parents[2] / "apps" / "api" / "openapi.json"


def main() -> None:
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else DESTINO_PADRAO
    texto = json.dumps(app.openapi(), indent=2, ensure_ascii=False, sort_keys=True)
    destino.write_text(texto + "\n", encoding="utf-8", newline="\n")
    print(f"OpenAPI gravado em {destino}")


if __name__ == "__main__":
    main()
