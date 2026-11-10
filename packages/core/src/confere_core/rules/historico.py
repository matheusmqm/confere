"""Histórico de documentos em memória, para o eval (CF-82).

Processe os documentos em ordem de emissão: avalie o documento (`aplicar_regras`) e só DEPOIS
registre-o (`registrar_documento` e, para as linhas aprovadas, `registrar_linha_aprovada`). Assim o
primeiro recebido é o original e o segundo, a duplicata. O `numero` informado em
`registrar_documento` e em `existe_numero` já deve estar normalizado (`normalizar_numero`).
"""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from confere_core.rules.duplicidade import normalizar_numero


@dataclass(frozen=True)
class _Documento:
    empresa_id: uuid.UUID
    id: uuid.UUID
    fornecedor_id: str
    numero: str  # normalizado
    sha256: str | None
    cancelado: bool


@dataclass(frozen=True)
class _LinhaAprovada:
    empresa_id: uuid.UUID
    documento_id: uuid.UUID
    fornecedor_id: str
    processo_id: uuid.UUID
    codigo: str
    valor: Decimal
    moeda: str


class HistoricoMemoria:
    def __init__(self) -> None:
        self._documentos: list[_Documento] = []
        self._linhas: list[_LinhaAprovada] = []

    def registrar_documento(
        self,
        empresa_id: uuid.UUID,
        documento_id: uuid.UUID,
        fornecedor_id: str,
        numero: str,
        sha256: str | None,
        cancelado: bool = False,
    ) -> None:
        self._documentos.append(
            _Documento(
                empresa_id,
                documento_id,
                fornecedor_id,
                normalizar_numero(numero),
                sha256,
                cancelado,
            )
        )

    def registrar_linha_aprovada(
        self,
        empresa_id: uuid.UUID,
        documento_id: uuid.UUID,
        fornecedor_id: str,
        processo_id: uuid.UUID,
        codigo: str,
        valor: Decimal,
        moeda: str,
    ) -> None:
        self._linhas.append(
            _LinhaAprovada(
                empresa_id, documento_id, fornecedor_id, processo_id, codigo, valor, moeda
            )
        )

    def existe_sha256(
        self, empresa_id: uuid.UUID, sha256: str, excluir_id: uuid.UUID | None
    ) -> uuid.UUID | None:
        for d in self._documentos:  # na ordem de chegada: o primeiro é o original
            if (
                d.empresa_id == empresa_id
                and d.sha256 == sha256
                and not d.cancelado
                and d.id != excluir_id
            ):
                return d.id
        return None

    def existe_numero(
        self, empresa_id: uuid.UUID, fornecedor_id: str, numero: str, excluir_id: uuid.UUID | None
    ) -> uuid.UUID | None:
        for d in self._documentos:
            if (
                d.empresa_id == empresa_id
                and d.fornecedor_id == fornecedor_id
                and d.numero == numero
                and not d.cancelado
                and d.id != excluir_id
            ):
                return d.id
        return None

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
        for ln in self._linhas:
            if (
                ln.empresa_id == empresa_id
                and ln.fornecedor_id == fornecedor_id
                and ln.processo_id == processo_id
                and ln.codigo == codigo
                and ln.valor == valor
                and ln.moeda == moeda
                and ln.documento_id != excluir_documento_id
            ):
                return ln.documento_id
        return None
