"""Gera CT-e XML sintéticos do mundo seed 42 em `data/demo_xml/`, para testar o upload.

`uv run python infra/scripts/gerar_ctes_demo.py [pasta]`. São os mesmos processos que
`make seed` carrega: cada CT-e cita uma referência de um processo (BL house, contêiner...) e
cobra os componentes do frete (frete peso, pedágio, GRIS, ad valorem). Tudo fictício, sem LLM.
"""

import random
import sys
from pathlib import Path

from confere_synth.cte import gerar_ctes, gravar_xml
from confere_synth.mundo import gerar_mundo

PASTA_PADRAO = Path(__file__).resolve().parents[2] / "data" / "demo_xml"


def main() -> None:
    pasta = Path(sys.argv[1]) if len(sys.argv) > 1 else PASTA_PADRAO
    pasta.mkdir(parents=True, exist_ok=True)
    mundo = gerar_mundo(42)
    ctes = gerar_ctes(random.Random(42), mundo)
    for cte in ctes:
        gravar_xml(cte, pasta)
    print(f"{len(ctes)} CT-e XML em {pasta}")


if __name__ == "__main__":
    main()
