"""ROUTE: painel de KPIs. Só HTTP; o SQL está em `controllers/painel.py`."""

from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter

from confere_api.controllers.painel import PainelController
from confere_api.deps import DbDep, TenantDep
from confere_api.schemas.painel import (
    FornecedorRanking,
    KpiContagem,
    KpiDinheiro,
    KpiPercentual,
    Kpis,
    KpiSegundos,
    KpiUsd,
    PainelSaida,
    PontoSerie,
    TipoExcecaoPainel,
)

router = APIRouter(tags=["painel"])
ZERO = Decimal(0)


@router.get("/painel", response_model=PainelSaida)
def obter_painel(
    db: DbDep,
    tenant: TenantDep,
    de: date | None = None,
    ate: date | None = None,
    lote: Literal["demo", "todos"] = "todos",
) -> PainelSaida:
    painel = PainelController(db, tenant).calcular(de, ate, lote)
    k = painel.kpis
    # Baseline B0 = processo manual: nada é aprovado sem toque e nada é evitado.
    return PainelSaida(
        kpis=Kpis(
            rs_evitado=KpiDinheiro(valor=k["rs_evitado"], baseline=ZERO),
            pct_sem_toque=KpiPercentual(valor=k["pct_sem_toque"], baseline=0.0),
            tempo_mediano_s=KpiSegundos(
                valor=None if k["tempo_mediano_s"] is None else float(k["tempo_mediano_s"]),
                baseline=None,
            ),
            tempo_p95_s=KpiSegundos(
                valor=None if k["tempo_p95_s"] is None else float(k["tempo_p95_s"]),
                baseline=None,
            ),
            n_documentos=KpiContagem(valor=k["n_documentos"], baseline=None),
            custo_ia_por_fatura_usd=KpiUsd(valor=k["custo_ia_por_fatura_usd"], baseline=None),
        ),
        serie_temporal=[PontoSerie(**ponto) for ponto in painel.serie],
        ranking_fornecedores=[
            FornecedorRanking(
                fornecedor_id=f["fornecedor_id"],
                nome=f["nome"],
                n_documentos=f["n_documentos"],
                pct_com_excecao=f["n_com_excecao"] / f["n_documentos"]
                if f["n_documentos"]
                else 0.0,
                rs_em_risco=f["rs_em_risco"],
                rs_evitado=f["rs_evitado"],
                tipo_mais_comum=f["tipo_mais_comum"],
            )
            for f in painel.fornecedores
        ],
        por_tipo_excecao=[
            TipoExcecaoPainel(tipo=t["tipo"], quantidade=t["quantidade"], rs=t["rs"])
            for t in painel.por_tipo
        ],
    )
