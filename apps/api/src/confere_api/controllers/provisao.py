"""CONTROLLER: provisões (custo previsto) com validação e reprocessamento ao editar."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from confere_api.controllers.base import RepositorioBase
from confere_api.controllers.job import JobController
from confere_api.erros import ErroNegocio
from confere_api.models.casamento import Casamento
from confere_api.models.codigo_custo import CodigoCusto
from confere_api.models.documento import Linha
from confere_api.models.fornecedor import Fornecedor
from confere_api.models.processo import Processo
from confere_api.models.provisao import Provisao
from confere_core.extract.validacoes import moedas_padrao


class DadoInvalido(ErroNegocio):
    codigo = "dado_invalido"
    status_http = 422
    mensagem_padrao = "Dados inválidos."


@dataclass
class ProvisaoComFornecedor:
    provisao: Provisao
    fornecedor: Fornecedor
    documentos_reprocessados: int = 0


class ProvisaoController(RepositorioBase):
    def abertas(self, processo_id: uuid.UUID, fornecedor_id: uuid.UUID) -> list[Provisao]:
        """Provisões ainda não casadas do fornecedor no processo (insumo do casamento)."""
        return list(
            self.db.scalars(
                self._q(Provisao).where(
                    Provisao.processo_id == processo_id,
                    Provisao.fornecedor_id == fornecedor_id,
                    Provisao.status.in_(("aberta", "parcial")),
                )
            )
        )

    def do_processo(self, processo_id: uuid.UUID, fornecedor_id: uuid.UUID) -> int:
        """Quantas provisões (qualquer status) o fornecedor tem no processo."""
        return len(
            self.db.scalars(
                self._q(Provisao).where(
                    Provisao.processo_id == processo_id, Provisao.fornecedor_id == fornecedor_id
                )
            ).all()
        )

    def _validar(
        self, *, moeda: str | None, valor: Decimal | None, codigo_custo: str | None
    ) -> None:
        if moeda is not None and moeda not in moedas_padrao():
            raise DadoInvalido(f"Moeda {moeda!r} fora da lista aceita.")
        if valor is not None and valor <= 0:
            raise DadoInvalido("O valor previsto deve ser maior que zero.")
        if codigo_custo is not None and self.db.get(CodigoCusto, codigo_custo) is None:
            raise DadoInvalido(f"Código de custo {codigo_custo!r} não existe no catálogo.")

    def criar(
        self,
        processo_id: uuid.UUID,
        *,
        fornecedor_id: uuid.UUID,
        codigo_custo: str,
        moeda: str,
        valor: Decimal,
    ) -> ProvisaoComFornecedor:
        self.obter(Processo, processo_id)
        fornecedor = self.obter(Fornecedor, fornecedor_id)
        self._validar(moeda=moeda, valor=valor, codigo_custo=codigo_custo)
        provisao = Provisao(
            processo_id=processo_id,
            fornecedor_id=fornecedor_id,
            codigo_custo=codigo_custo,
            moeda=moeda,
            valor=valor,
            status="aberta",
        )
        self.adicionar(provisao)
        self.db.flush()
        return ProvisaoComFornecedor(provisao, fornecedor)

    def editar(
        self,
        provisao_id: uuid.UUID,
        *,
        valor: Decimal | None = None,
        moeda: str | None = None,
        codigo_custo: str | None = None,
        status: str | None = None,
    ) -> ProvisaoComFornecedor:
        """Edita a provisão. Se ela já estava casada, enfileira o reprocessamento (E6 em diante)."""
        provisao = self.obter(Provisao, provisao_id)
        self._validar(moeda=moeda, valor=valor, codigo_custo=codigo_custo)
        ja_casada = provisao.status in ("casada", "parcial")
        mudancas = {
            "valor": valor,
            "moeda": moeda,
            "codigo_custo": codigo_custo,
            "status": status,
        }
        alterou = False
        for campo, novo in mudancas.items():
            if novo is not None and getattr(provisao, campo) != novo:
                setattr(provisao, campo, novo)
                alterou = True
        reprocessados = 0
        if alterou and ja_casada:
            documentos = self.db.scalars(
                self._q(Casamento)
                .with_only_columns(Linha.documento_id)
                .select_from(Casamento)
                .join(Linha, Linha.id == Casamento.linha_id)
                .where(Casamento.provisao_id == provisao_id)
                .distinct()
            ).all()
            jobs = JobController(self.db, self.tenant)
            for documento_id in documentos:
                jobs.reprocessar_documento(documento_id, "casado")
            reprocessados = len(documentos)
        self.db.flush()
        fornecedor = self.obter(Fornecedor, provisao.fornecedor_id)
        return ProvisaoComFornecedor(provisao, fornecedor, reprocessados)
