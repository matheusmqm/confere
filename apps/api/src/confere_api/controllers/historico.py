"""CONTROLLER: histórico de documentos da empresa para a regra de duplicidade (CF-82, SQL).

Implementa o `HistoricoDocumentos` do core. Só conta documentos já DECIDIDOS: assim o primeiro a
ser processado é o original e o segundo, a duplicata.
"""

import uuid
from decimal import Decimal

from confere_api.controllers.base import RepositorioBase
from confere_api.models.documento import Documento, Linha

STATUS_DECIDIDOS = ("aprovado_auto", "aprovado_manual", "em_revisao", "bloqueado")
STATUS_APROVADOS = ("aprovado_auto", "aprovado_manual")


class HistoricoDocumentosSQL(RepositorioBase):
    def existe_sha256(
        self, empresa_id: uuid.UUID, sha256: str, excluir_id: uuid.UUID | None
    ) -> uuid.UUID | None:
        consulta = (
            self._q(Documento)
            .where(Documento.sha256 == sha256, Documento.status.in_(STATUS_DECIDIDOS))
            .order_by(Documento.criado_em)
            .limit(1)
        )
        if excluir_id is not None:
            consulta = consulta.where(Documento.id != excluir_id)
        achado = self.db.scalars(consulta).first()
        return achado.id if achado else None

    def existe_numero(
        self, empresa_id: uuid.UUID, fornecedor_id: str, numero: str, excluir_id: uuid.UUID | None
    ) -> uuid.UUID | None:
        consulta = (
            self._q(Documento)
            .where(
                Documento.fornecedor_id == uuid.UUID(fornecedor_id),
                Documento.numero_normalizado == numero,
                Documento.status.in_(STATUS_DECIDIDOS),
            )
            .order_by(Documento.criado_em)
            .limit(1)
        )
        if excluir_id is not None:
            consulta = consulta.where(Documento.id != excluir_id)
        achado = self.db.scalars(consulta).first()
        return achado.id if achado else None

    def linha_aprovada_igual(
        self,
        empresa_id: uuid.UUID,
        fornecedor_id: str,
        processo_id: uuid.UUID,
        codigo: str,
        valor: Decimal,
        moeda: str,
        excluir_documento_id: uuid.UUID | None,
    ) -> uuid.UUID | None:
        consulta = (
            self._q(Linha)
            .join(Documento, Documento.id == Linha.documento_id)
            .where(
                Documento.fornecedor_id == uuid.UUID(fornecedor_id),
                Documento.status.in_(STATUS_APROVADOS),
                Linha.processo_id == processo_id,
                Linha.codigo_custo == codigo,
                Linha.valor == valor,
                Linha.moeda == moeda,
            )
            .limit(1)
        )
        if excluir_documento_id is not None:
            consulta = consulta.where(Linha.documento_id != excluir_documento_id)
        achada = self.db.scalars(consulta).first()
        return achada.documento_id if achada else None
