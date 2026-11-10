"""SCHEMAS: painel de KPIs."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from confere_api.schemas.comuns import DecimalTexto, Dinheiro


class KpiDinheiro(BaseModel):
    valor: Dinheiro
    baseline: Dinheiro | None  # B0 (manual)


class KpiPercentual(BaseModel):
    valor: float  # 0 a 1
    baseline: float | None


class KpiSegundos(BaseModel):
    valor: float | None  # nulo se ainda não há documento decidido
    baseline: float | None


class KpiContagem(BaseModel):
    valor: int
    baseline: int | None


class KpiUsd(BaseModel):
    valor: DecimalTexto
    baseline: DecimalTexto | None


class Kpis(BaseModel):
    rs_evitado: KpiDinheiro
    pct_sem_toque: KpiPercentual
    tempo_mediano_s: KpiSegundos
    tempo_p95_s: KpiSegundos
    n_documentos: KpiContagem
    custo_ia_por_fatura_usd: KpiUsd


class PontoSerie(BaseModel):
    instante: datetime
    documentos: int
    rs_evitado: Dinheiro


class FornecedorRanking(BaseModel):
    fornecedor_id: uuid.UUID
    nome: str
    n_documentos: int
    pct_com_excecao: float
    rs_em_risco: Dinheiro
    rs_evitado: Dinheiro
    tipo_mais_comum: str | None


class TipoExcecaoPainel(BaseModel):
    tipo: str
    quantidade: int
    rs: Dinheiro


class PainelSaida(BaseModel):
    kpis: Kpis
    serie_temporal: list[PontoSerie]
    ranking_fornecedores: list[FornecedorRanking]
    por_tipo_excecao: list[TipoExcecaoPainel]
