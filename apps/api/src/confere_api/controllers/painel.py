"""CONTROLLER: KPIs do painel em SQL (CTEs), uma consulta por bloco (CF-112).

Definição de "R$ evitado" (CF-85, `docs/avaliacao.md`), aplicada às exceções:

- conta o `valor_brl_em_risco` das exceções de severidade `bloquear` (bloqueio automático) e das
  que um humano contestou ou bloqueou;
- no lote de demo (`lote=demo`) conta também as de severidade `revisar` (o jurado não decide tudo);
- nunca conta a exceção que um humano decidiu aprovar (isso é "vazado").

Todas as consultas filtram por `empresa_id` (o tenant) e pelo período e lote pedidos.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from confere_api.controllers.base import RepositorioBase

STATUS_FINALIZADOS = "('aprovado_auto', 'aprovado_manual', 'em_revisao', 'bloqueado')"

_DOCS = f"""
WITH docs AS (
    SELECT d.id, d.status, d.fornecedor_id
    FROM documento d
    WHERE d.empresa_id = :e
      AND (CAST(:de AS date) IS NULL OR d.criado_em >= CAST(:de AS date))
      AND (CAST(:ate AS date) IS NULL OR d.criado_em < CAST(:ate AS date) + 1)
      AND (:lote_demo = FALSE OR d.em_lote_demo)
),
finais AS (SELECT * FROM docs WHERE status IN {STATUS_FINALIZADOS})
"""

# Exceção `x` que entra em "R$ evitado" (ver o docstring do módulo).
_EVITADA = """
    x.valor_brl_em_risco > 0
    AND x.severidade <> 'info'
    AND NOT EXISTS (SELECT 1 FROM decisao dc WHERE dc.excecao_id = x.id AND dc.acao = 'aprovar')
    AND (
        x.severidade = 'bloquear'
        OR EXISTS (SELECT 1 FROM decisao dc
                   WHERE dc.excecao_id = x.id AND dc.acao IN ('contestar', 'bloquear'))
        OR (:lote_demo AND x.severidade = 'revisar')
    )
"""

SQL_KPIS = (
    _DOCS
    + f"""
, tempos AS (
    SELECT ev.documento_id,
           EXTRACT(EPOCH FROM (
               MAX(ev.criado_em) FILTER (WHERE ev.etapa = 'decidido')
             - MIN(ev.criado_em) FILTER (WHERE ev.etapa = 'recebido'))) AS segundos
    FROM evento ev JOIN docs ON docs.id = ev.documento_id
    WHERE ev.empresa_id = :e
    GROUP BY ev.documento_id
),
evitado AS (
    SELECT COALESCE(SUM(x.valor_brl_em_risco), 0) AS valor
    FROM excecao x JOIN docs ON docs.id = x.documento_id
    WHERE x.empresa_id = :e AND {_EVITADA}
)
SELECT
    (SELECT COUNT(*) FROM docs) AS n_documentos,
    (SELECT COUNT(*) FROM finais) AS n_finais,
    (SELECT COUNT(*) FROM finais WHERE status = 'aprovado_auto') AS n_auto,
    (SELECT valor FROM evitado) AS rs_evitado,
    (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY segundos)
       FROM tempos WHERE segundos IS NOT NULL) AS tempo_mediano_s,
    (SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY segundos)
       FROM tempos WHERE segundos IS NOT NULL) AS tempo_p95_s,
    (SELECT COALESCE(SUM(l.custo_usd), 0)
       FROM llm_call l JOIN finais f ON f.id = l.documento_id
      WHERE l.empresa_id = :e) AS custo_ia_usd
"""
)

SQL_SERIE = (
    _DOCS
    + f"""
, decididos AS (
    SELECT ev.documento_id, MAX(ev.criado_em) AS quando
    FROM evento ev JOIN docs ON docs.id = ev.documento_id
    WHERE ev.empresa_id = :e AND ev.etapa = 'decidido'
    GROUP BY ev.documento_id
),
evitado_por_doc AS (
    SELECT x.documento_id, SUM(x.valor_brl_em_risco) AS valor
    FROM excecao x JOIN docs ON docs.id = x.documento_id
    WHERE x.empresa_id = :e AND {_EVITADA}
    GROUP BY x.documento_id
)
SELECT date_trunc(CAST(:grao AS text), d.quando) AS instante,
       COUNT(*) AS documentos,
       COALESCE(SUM(r.valor), 0) AS rs_evitado
FROM decididos d LEFT JOIN evitado_por_doc r ON r.documento_id = d.documento_id
GROUP BY 1
ORDER BY 1
"""
)

SQL_FORNECEDORES = (
    _DOCS
    + f"""
, por_fornecedor AS (
    SELECT d.fornecedor_id,
           COUNT(DISTINCT d.id) AS n_documentos,
           COUNT(DISTINCT d.id) FILTER (WHERE x.id IS NOT NULL AND x.severidade <> 'info')
               AS n_com_excecao,
           COALESCE(SUM(x.valor_brl_em_risco) FILTER (WHERE x.severidade <> 'info'), 0)
               AS rs_em_risco,
           COALESCE(SUM(x.valor_brl_em_risco) FILTER (WHERE {_EVITADA}), 0) AS rs_evitado,
           MODE() WITHIN GROUP (ORDER BY x.tipo) FILTER (WHERE x.severidade <> 'info')
               AS tipo_mais_comum
    FROM docs d
    LEFT JOIN excecao x ON x.documento_id = d.id AND x.empresa_id = :e
    WHERE d.fornecedor_id IS NOT NULL
    GROUP BY d.fornecedor_id
)
SELECT f.id AS fornecedor_id, f.nome, p.n_documentos, p.n_com_excecao, p.rs_em_risco,
       p.rs_evitado, p.tipo_mais_comum
FROM por_fornecedor p JOIN fornecedor f ON f.id = p.fornecedor_id
ORDER BY p.rs_em_risco DESC, p.rs_evitado DESC, f.nome
LIMIT 8
"""
)

SQL_POR_TIPO = (
    _DOCS
    + """
SELECT x.tipo, COUNT(*) AS quantidade, COALESCE(SUM(x.valor_brl_em_risco), 0) AS rs
FROM excecao x JOIN docs ON docs.id = x.documento_id
WHERE x.empresa_id = :e
GROUP BY x.tipo
ORDER BY rs DESC, quantidade DESC
"""
)


@dataclass
class Painel:
    kpis: dict[str, Any]
    serie: list[dict[str, Any]]
    fornecedores: list[dict[str, Any]]
    por_tipo: list[dict[str, Any]]


class PainelController(RepositorioBase):
    def _executar(self, sql: str, parametros: dict[str, Any]) -> list[dict[str, Any]]:
        return [dict(linha) for linha in self.db.execute(text(sql), parametros).mappings()]

    def calcular(self, de: date | None, ate: date | None, lote: str) -> Painel:
        lote_demo = lote == "demo"
        parametros: dict[str, Any] = {
            "e": self.tenant.empresa_id,
            "de": de,
            "ate": ate,
            "lote_demo": lote_demo,
            "grao": "minute" if lote_demo else "day",
        }
        kpis = self._executar(SQL_KPIS, parametros)[0]
        finais = int(kpis["n_finais"])
        kpis["custo_ia_por_fatura_usd"] = (
            Decimal(kpis["custo_ia_usd"]) / finais if finais else Decimal(0)
        )
        kpis["pct_sem_toque"] = int(kpis["n_auto"]) / finais if finais else 0.0
        return Painel(
            kpis=kpis,
            serie=self._executar(SQL_SERIE, parametros),
            fornecedores=self._executar(SQL_FORNECEDORES, parametros),
            por_tipo=self._executar(SQL_POR_TIPO, parametros),
        )
