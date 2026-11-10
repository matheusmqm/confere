"""Carga do mundo sintético no banco (CF-41, versão reduzida do MVP mínimo).

`python -m confere_api.seed [--limpar] [--seed 42]`

Gera o mundo (fornecedores, clientes, 50 processos e provisões) em memória com `confere_synth`
e grava no banco da empresa demo, com ids determinísticos (rodar de novo não duplica). Fica de
fora, por ora: PTAX, exemplos de treino e embeddings. Tudo é fictício.
"""

import argparse
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, delete, insert, select
from sqlalchemy.orm import Session

from confere_api.controllers.auth import EMAIL_USUARIO_DEMO
from confere_api.models.codigo_custo import CodigoCusto
from confere_api.models.empresa import Empresa, Usuario, politica_padrao
from confere_api.models.fornecedor import Fornecedor, FornecedorAlias
from confere_api.models.processo import Processo, ProcessoReferencia
from confere_api.models.provisao import Provisao
from confere_api.models.sinonimo import SinonimoCusto
from confere_api.settings import RAIZ, get_settings
from confere_core.costcode.catalogo import Catalogo
from confere_core.costcode.normalizar import normalizar_descricao
from confere_core.resolve.normalizar import normalizar_nome, normalizar_referencia
from confere_synth.mundo import gerar_mundo

EMPRESA_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
NOME_EMPRESA = "Agência Demo Cargas Ltda. (fictícia)"
CNPJ_FICTICIO = "00.000.000/0001-00"
_NS = uuid.UUID("c0ffee00-0000-4000-8000-000000000042")


def id_fornecedor(slug: str) -> uuid.UUID:
    """Id estável do fornecedor sintético (o `id` do mundo é um slug)."""
    return uuid.uuid5(_NS, f"fornecedor:{slug}")


def _lote(sessao: Session, modelo: Any, linhas: list[dict[str, Any]]) -> None:
    if linhas:
        sessao.execute(insert(modelo), linhas)


def _limpar(sessao: Session) -> None:
    for modelo in (
        Provisao,
        ProcessoReferencia,
        Processo,
        FornecedorAlias,
        SinonimoCusto,
        Fornecedor,
        Usuario,
    ):
        sessao.execute(delete(modelo).where(modelo.empresa_id == EMPRESA_ID))
    sessao.execute(delete(Empresa).where(Empresa.id == EMPRESA_ID))


def carregar(sessao: Session, seed: int = 42, limpar: bool = False) -> dict[str, int]:
    """Grava o mundo na empresa demo. A transação é de quem chama."""
    if limpar:
        _limpar(sessao)
    if sessao.get(Empresa, EMPRESA_ID) is not None:
        return {}  # já carregado: idempotente

    mundo = gerar_mundo(seed)
    catalogo = Catalogo.carregar(RAIZ / "config" / "codigos_custo.yaml")
    clientes = {c.id: c.nome for c in mundo.clientes}

    sessao.add(
        Empresa(
            id=EMPRESA_ID,
            nome=NOME_EMPRESA,
            cnpj_ficticio=CNPJ_FICTICIO,
            politica_json=politica_padrao(),
        )
    )
    sessao.flush()
    sessao.add(
        Usuario(
            id=uuid.uuid5(_NS, "usuario:demo"),
            empresa_id=EMPRESA_ID,
            email=EMAIL_USUARIO_DEMO,
            nome="Usuário Demo",
            papel="gestor",
        )
    )

    # catálogo global (sem empresa) — idempotente por chave natural
    existentes = set(sessao.scalars(select(CodigoCusto.codigo)))
    _lote(
        sessao,
        CodigoCusto,
        [
            {"codigo": i.codigo, "descricao": i.descricao, "grupo": i.grupo, "unidade": i.unidade}
            for i in catalogo.itens
            if i.codigo not in existentes
        ],
    )
    sessao.flush()

    _lote(
        sessao,
        Fornecedor,
        [
            {
                "id": id_fornecedor(f.id),
                "empresa_id": EMPRESA_ID,
                "nome": f.nome,
                "tipo": f.tipo,
                "pais": f.pais,
                "moeda_padrao": f.moeda_padrao,
                "dominio_email": f.dominio_email,
                "idioma": f.idioma,
            }
            for f in mundo.fornecedores
        ],
    )
    aliases: list[dict[str, Any]] = []
    for f in mundo.fornecedores:
        for alias in dict.fromkeys([f.nome, *f.aliases]):
            aliases.append(
                {
                    "id": uuid.uuid4(),
                    "empresa_id": EMPRESA_ID,
                    "fornecedor_id": id_fornecedor(f.id),
                    "alias": alias,
                    "alias_normalizado": normalizar_nome(alias),
                }
            )
    _lote(sessao, FornecedorAlias, aliases)

    _lote(
        sessao,
        Processo,
        [
            {
                "id": p.id,
                "empresa_id": EMPRESA_ID,
                "codigo": p.codigo,
                "cliente": clientes[p.cliente_id],
                "modal": p.modal,
                "origem": p.origem,
                "destino": p.destino,
                "navio": p.navio,
                "viagem": p.viagem,
                "etd": p.etd,
                "eta": p.eta,
                "status": "aberto",
            }
            for p in mundo.processos
        ],
    )
    _lote(
        sessao,
        ProcessoReferencia,
        [
            {
                "id": uuid.uuid4(),
                "empresa_id": EMPRESA_ID,
                "processo_id": p.id,
                "tipo": r.tipo,
                "valor": r.valor,
                "valor_normalizado": normalizar_referencia(r.tipo, r.valor),
                "origem": "cadastro",
            }
            for p in mundo.processos
            for r in p.referencias
        ],
    )
    sessao.flush()
    _lote(
        sessao,
        Provisao,
        [
            {
                "id": v.id,
                "empresa_id": EMPRESA_ID,
                "processo_id": v.processo_id,
                "fornecedor_id": id_fornecedor(v.fornecedor_id),
                "codigo_custo": v.codigo_custo,
                "moeda": v.moeda,
                "valor": Decimal(v.valor),
                "status": "aberta",
            }
            for v in mundo.provisoes
        ],
    )

    # sinônimos globais do catálogo, normalizados como as descrições das faturas
    vistos: set[str] = set()
    sinonimos: list[dict[str, Any]] = []
    for item in catalogo.itens:
        for texto in item.sinonimos:
            norm = normalizar_descricao(texto)
            if norm and norm not in vistos:
                vistos.add(norm)
                sinonimos.append(
                    {
                        "id": uuid.uuid4(),
                        "empresa_id": EMPRESA_ID,
                        "fornecedor_id": None,
                        "texto_normalizado": norm,
                        "codigo_custo": item.codigo,
                        "origem": "catalogo",
                    }
                )
    _lote(sessao, SinonimoCusto, sinonimos)
    return {
        "fornecedores": len(mundo.fornecedores),
        "processos": len(mundo.processos),
        "provisoes": len(mundo.provisoes),
        "sinonimos": len(sinonimos),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Carrega o mundo sintético no banco")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limpar", action="store_true", help="apaga a empresa demo antes")
    args = parser.parse_args()

    # Conexão direta/session (porta 5432): o seed grava em lote.
    engine = create_engine(get_settings().database_url_worker.get_secret_value())
    with Session(engine) as sessao, sessao.begin():
        totais = carregar(sessao, args.seed, args.limpar)
    if totais:
        print("Carregado:", ", ".join(f"{n} {k}" for k, n in totais.items()))
    else:
        print("A empresa demo já existe (use --limpar para recarregar).")


if __name__ == "__main__":
    main()
