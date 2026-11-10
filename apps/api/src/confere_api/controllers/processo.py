"""CONTROLLER: processos, previsto x cobrado e saldo a repassar (CF-110).

Conversão para BRL: as linhas já trazem `valor_brl` (câmbio da E5). Já a provisão, que não tem
câmbio próprio, é convertida pela PTAX de venda MAIS RECENTE de `ptax_cache`. Sem cotação para a
moeda, o valor em BRL fica nulo e o total é marcado como `cotacao_incompleta`.
"""

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_

from confere_api.controllers.base import RepositorioBase
from confere_api.models.casamento import Casamento
from confere_api.models.documento import Documento, Linha
from confere_api.models.excecao import Decisao, Excecao
from confere_api.models.fornecedor import Fornecedor
from confere_api.models.global_ import PtaxCache
from confere_api.models.processo import Processo, ProcessoReferencia
from confere_api.models.provisao import Provisao
from confere_core.resolve.normalizar import sem_acento_maiusculas

ZERO = Decimal("0.00")
_SEPARADORES = re.compile(r"[\s\-/._:#]")


@dataclass
class ResumoProcesso:
    processo: Processo
    n_documentos: int = 0
    previsto_brl: Decimal = ZERO
    cobrado_brl: Decimal = ZERO
    n_excecoes_abertas: int = 0
    cotacao_incompleta: bool = False


@dataclass
class LinhaPrevistoCobrado:
    fornecedor_id: uuid.UUID
    fornecedor_nome: str
    codigo_custo: str
    previsto_moeda: str | None = None
    previsto_valor: Decimal | None = None
    previsto_brl: Decimal | None = None
    cobrado_moeda: str | None = None
    cobrado_valor: Decimal | None = None
    cobrado_brl: Decimal | None = None
    diferenca_brl: Decimal | None = None
    estado: str = "ok"  # ok | acima | abaixo | sem_fatura | sem_provisao
    documento_ids: list[uuid.UUID] = field(default_factory=list)
    linha_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass
class DetalheProcesso:
    processo: Processo
    referencias: list[ProcessoReferencia]
    itens: list[LinhaPrevistoCobrado]
    previsto_brl: Decimal
    cobrado_brl: Decimal
    diferenca_brl: Decimal
    saldo_a_repassar_brl: Decimal
    cotacao_incompleta: bool


def normalizar_busca(texto: str) -> str:
    return _SEPARADORES.sub("", sem_acento_maiusculas(texto))


class ProcessoController(RepositorioBase):
    def por_referencias(self, normalizadas: set[str]) -> dict[uuid.UUID, set[str]]:
        """Processos com alguma das referências (busca exata): processo → referências achadas."""
        if not normalizadas:
            return {}
        achados: dict[uuid.UUID, set[str]] = defaultdict(set)
        for processo_id, valor in self.db.execute(
            self._q(ProcessoReferencia)
            .with_only_columns(ProcessoReferencia.processo_id, ProcessoReferencia.valor_normalizado)
            .where(ProcessoReferencia.valor_normalizado.in_(normalizadas))
        ):
            achados[processo_id].add(valor)
        return dict(achados)

    def _taxas(self, moedas: set[str]) -> dict[str, Decimal]:
        """PTAX de venda mais recente por moeda (BRL = 1)."""
        taxas = {"BRL": Decimal(1)}
        pendentes = moedas - {"BRL"}
        if pendentes:
            for cotacao in self.db.scalars(
                self._g(PtaxCache)
                .where(PtaxCache.moeda.in_(pendentes))
                .order_by(PtaxCache.moeda, PtaxCache.data.desc())
            ):
                taxas.setdefault(cotacao.moeda, cotacao.venda)
        return taxas

    def listar(
        self, busca: str | None, status: str | None, limite: int = 200
    ) -> list[ResumoProcesso]:
        consulta = self._q(Processo)
        if status:
            consulta = consulta.where(Processo.status == status)
        if busca and busca.strip():
            normalizada = normalizar_busca(busca)
            por_referencia = (
                self._q(ProcessoReferencia)
                .with_only_columns(ProcessoReferencia.processo_id)
                .where(ProcessoReferencia.valor_normalizado.ilike(f"%{normalizada}%"))
            )
            consulta = consulta.where(
                or_(Processo.codigo.ilike(f"%{busca.strip()}%"), Processo.id.in_(por_referencia))
            )
        processos = list(
            self.db.scalars(
                consulta.order_by(Processo.eta.desc().nulls_last(), Processo.codigo).limit(limite)
            )
        )
        resumos = {p.id: ResumoProcesso(p) for p in processos}
        if not resumos:
            return []
        ids = list(resumos)

        # documentos e cobrado (BRL) por processo
        for pid, n_docs, cobrado in self.db.execute(
            self._q(Linha)
            .with_only_columns(
                Linha.processo_id,
                func.count(func.distinct(Linha.documento_id)),
                func.coalesce(func.sum(Linha.valor_brl), 0),
            )
            .where(Linha.processo_id.in_(ids), Linha.estado != "duplicada")
            .group_by(Linha.processo_id)
        ):
            if pid in resumos:
                resumos[pid].n_documentos = n_docs
                resumos[pid].cobrado_brl = Decimal(cobrado or 0)

        # previsto: soma por (processo, moeda), convertida pela PTAX mais recente
        previstos = list(
            self.db.execute(
                self._q(Provisao)
                .with_only_columns(Provisao.processo_id, Provisao.moeda, func.sum(Provisao.valor))
                .where(Provisao.processo_id.in_(ids), Provisao.status != "cancelada")
                .group_by(Provisao.processo_id, Provisao.moeda)
            )
        )
        taxas = self._taxas({moeda for _, moeda, _ in previstos})
        for pid, moeda, valor in previstos:
            taxa = taxas.get(moeda)
            if taxa is None:
                resumos[pid].cotacao_incompleta = True
            else:
                resumos[pid].previsto_brl += Decimal(valor) * taxa

        # exceções abertas: por processo da linha ou, sem linha, da provisão
        processo_da_excecao = func.coalesce(Linha.processo_id, Provisao.processo_id)
        for pid, quantidade in self.db.execute(
            self._q(Excecao)
            .with_only_columns(processo_da_excecao, func.count())
            .select_from(Excecao)
            .outerjoin(Linha, Linha.id == Excecao.linha_id)
            .outerjoin(Provisao, Provisao.id == Excecao.provisao_id)
            .where(Excecao.status == "aberta")
            .group_by(processo_da_excecao)
        ):
            if pid in resumos:
                resumos[pid].n_excecoes_abertas = quantidade
        return [resumos[p.id] for p in processos]

    def detalhe(self, processo_id: uuid.UUID) -> DetalheProcesso:
        processo = self.obter(Processo, processo_id)
        referencias = list(
            self.db.scalars(
                self._q(ProcessoReferencia).where(ProcessoReferencia.processo_id == processo_id)
            )
        )
        provisoes = list(
            self.db.execute(
                self._q(Provisao)
                .add_columns(Fornecedor.nome)
                .join(Fornecedor, Fornecedor.id == Provisao.fornecedor_id)
                .where(Provisao.processo_id == processo_id, Provisao.status != "cancelada")
            )
        )
        linhas = list(
            self.db.execute(
                self._q(Linha)
                .add_columns(Documento.fornecedor_id, Fornecedor.nome, Casamento.diferenca_brl)
                .join(Documento, Documento.id == Linha.documento_id)
                .outerjoin(Fornecedor, Fornecedor.id == Documento.fornecedor_id)
                .outerjoin(Casamento, Casamento.linha_id == Linha.id)
                .where(
                    Linha.processo_id == processo_id,
                    Linha.codigo_custo.is_not(None),
                    Linha.estado != "duplicada",
                )
            )
        )
        taxas = self._taxas({p.moeda for p, _ in provisoes})
        incompleta = False
        itens: dict[tuple[uuid.UUID | None, str], LinhaPrevistoCobrado] = {}

        def item(
            fornecedor_id: uuid.UUID | None, nome: str | None, codigo: str
        ) -> LinhaPrevistoCobrado:
            chave = (fornecedor_id, codigo)
            if chave not in itens:
                itens[chave] = LinhaPrevistoCobrado(
                    fornecedor_id=fornecedor_id or uuid.UUID(int=0),
                    fornecedor_nome=nome or "Fornecedor não identificado",
                    codigo_custo=codigo,
                )
            return itens[chave]

        for provisao, nome in provisoes:
            it = item(provisao.fornecedor_id, nome, provisao.codigo_custo)
            it.previsto_moeda = it.previsto_moeda or provisao.moeda
            it.previsto_valor = (it.previsto_valor or ZERO) + provisao.valor
            taxa = taxas.get(provisao.moeda)
            if taxa is None:
                incompleta = True
            else:
                it.previsto_brl = (it.previsto_brl or ZERO) + provisao.valor * taxa

        for linha, fornecedor_id, nome, _dif in linhas:
            assert linha.codigo_custo is not None  # filtrado na consulta
            it = item(fornecedor_id, nome, linha.codigo_custo)
            it.cobrado_moeda = it.cobrado_moeda or linha.moeda
            it.cobrado_valor = (it.cobrado_valor or ZERO) + linha.valor
            if linha.valor_brl is None:
                incompleta = True
            else:
                it.cobrado_brl = (it.cobrado_brl or ZERO) + linha.valor_brl
            if linha.documento_id not in it.documento_ids:
                it.documento_ids.append(linha.documento_id)
            it.linha_ids.append(linha.id)
            if linha.estado == "acima_tolerancia":
                it.estado = "acima"
            elif linha.estado == "abaixo_previsto" and it.estado == "ok":
                it.estado = "abaixo"
            elif linha.estado == "sem_provisao":
                it.estado = "sem_provisao"

        for it in itens.values():
            if it.cobrado_valor is None:
                it.estado = "sem_fatura"
            elif it.previsto_valor is None:
                it.estado = "sem_provisao"
            if it.previsto_brl is not None or it.cobrado_brl is not None:
                it.diferenca_brl = (it.cobrado_brl or ZERO) - (it.previsto_brl or ZERO)

        previsto = sum((i.previsto_brl or ZERO for i in itens.values()), ZERO)
        cobrado = sum((i.cobrado_brl or ZERO for i in itens.values()), ZERO)
        saldo = self._saldo_a_repassar(linhas)
        return DetalheProcesso(
            processo=processo,
            referencias=referencias,
            itens=sorted(itens.values(), key=lambda i: (i.fornecedor_nome, i.codigo_custo)),
            previsto_brl=previsto,
            cobrado_brl=cobrado,
            diferenca_brl=cobrado - previsto,
            saldo_a_repassar_brl=saldo,
            cotacao_incompleta=incompleta,
        )

    def _saldo_a_repassar(self, linhas: list[Any]) -> Decimal:
        """Saldo a repassar ao cliente (CF-110).

        = linhas `sem_provisao` com decisão `repassar` + diferenças das linhas `acima_tolerancia`
        que um humano aprovou e ninguém contestou.
        """
        ids = [linha.id for linha, *_ in linhas]
        if not ids:
            return ZERO
        acoes: dict[uuid.UUID, set[str]] = defaultdict(set)
        for linha_id, acao in self.db.execute(
            self._q(Decisao)
            .with_only_columns(Excecao.linha_id, Decisao.acao)
            .select_from(Decisao)
            .join(Excecao, Excecao.id == Decisao.excecao_id)
            .where(Excecao.linha_id.in_(ids))
        ):
            if linha_id is not None:
                acoes[linha_id].add(acao)
        saldo = ZERO
        for linha, _fid, _nome, diferenca_brl in linhas:
            decisoes = acoes.get(linha.id, set())
            if linha.estado == "sem_provisao" and "repassar" in decisoes:
                saldo += linha.valor_brl or ZERO
            elif (
                linha.estado == "acima_tolerancia"
                and "aprovar" in decisoes
                and "contestar" not in decisoes
            ):
                saldo += diferenca_brl or ZERO
        return saldo
