"""CONTROLLER: documentos. Tudo passa pelo tenant."""

import base64
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Row, Select, func, tuple_

from confere_api.controllers.base import RepositorioBase
from confere_api.controllers.evento import EventoController
from confere_api.controllers.job import JobController
from confere_api.erros import ErroNegocio, NaoEncontrado
from confere_api.models.casamento import Casamento
from confere_api.models.documento import Documento, Linha
from confere_api.models.evento import Evento
from confere_api.models.excecao import Excecao
from confere_api.models.fornecedor import Fornecedor
from confere_api.models.processo import Processo
from confere_api.models.provisao import Provisao
from confere_api.storage import Storage
from confere_core.ingest.arquivo import caminho_storage, inspecionar


class CursorInvalido(ErroNegocio):
    codigo = "cursor_invalido"
    status_http = 422
    mensagem_padrao = "Cursor de paginação inválido."


class SemArquivo(ErroNegocio):
    codigo = "sem_arquivo"
    status_http = 404
    mensagem_padrao = "Este documento não tem arquivo armazenado."


TIPOS_DE_CONTEUDO = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "xml": "application/xml",
}
PROBLEMAS_SEM_PROCESSAMENTO = {"tipo_nao_suportado", "vazio", "pdf_corrompido", "muito_grande"}
MENSAGEM_PROBLEMA = {
    "tipo_nao_suportado": "Tipo de arquivo não suportado (envie PDF, PNG, JPG ou XML).",
    "vazio": "O arquivo está vazio.",
    "pdf_corrompido": "Não foi possível abrir o PDF.",
    "muito_grande": "O arquivo passa do limite de tamanho ou de páginas.",
}


@dataclass
class DocumentoRecebido:
    documento: Documento
    aviso: str | None


@dataclass
class LinhaDetalhe:
    linha: Linha
    processo: Processo | None
    casamento: Casamento | None
    provisao: Provisao | None


@dataclass
class DetalheDocumento:
    documento: Documento
    fornecedor: Fornecedor | None
    linhas: list[LinhaDetalhe]
    excecoes: Sequence[Excecao]
    eventos: Sequence[Evento]


def codificar_cursor(criado_em: datetime, id_: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(f"{criado_em.isoformat()}|{id_}".encode()).decode()


def decodificar_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        texto = base64.urlsafe_b64decode(cursor.encode()).decode()
        data, _, id_ = texto.partition("|")
        return datetime.fromisoformat(data), uuid.UUID(id_)
    except (ValueError, UnicodeDecodeError) as erro:
        raise CursorInvalido from erro


class DocumentoController(RepositorioBase):
    def obter_documento(self, documento_id: uuid.UUID) -> Documento:
        return self.obter(Documento, documento_id)

    def _consulta_resumo(self) -> Select[Any]:
        """Documento + `(fornecedor_id, fornecedor_nome, n_excecoes, risco_brl, codigos)`.

        As exceções abertas e os processos entram por subconsultas agregadas (sem N+1).
        """
        abertas = (
            self._q(Excecao)
            .with_only_columns(
                Excecao.documento_id.label("did"),
                func.count().label("n"),
                func.coalesce(func.sum(Excecao.valor_brl_em_risco), 0).label("risco"),
            )
            .where(Excecao.status == "aberta")
            .group_by(Excecao.documento_id)
            .subquery()
        )
        codigos = (
            self._q(Linha)
            .with_only_columns(
                Linha.documento_id.label("did"),
                func.array_agg(func.distinct(Processo.codigo)).label("codigos"),
            )
            .select_from(Linha)
            .join(Processo, Processo.id == Linha.processo_id)
            .group_by(Linha.documento_id)
            .subquery()
        )
        return (
            self._q(Documento)
            .add_columns(
                Fornecedor.id, Fornecedor.nome, abertas.c.n, abertas.c.risco, codigos.c.codigos
            )
            .outerjoin(Fornecedor, Fornecedor.id == Documento.fornecedor_id)
            .outerjoin(abertas, abertas.c.did == Documento.id)
            .outerjoin(codigos, codigos.c.did == Documento.id)
        )

    def resumo(self, documento_id: uuid.UUID) -> Row[Any]:
        """Uma linha no formato de `listar`."""
        linha = self.db.execute(self._consulta_resumo().where(Documento.id == documento_id)).first()
        if linha is None:
            raise NaoEncontrado
        return linha

    def listar(
        self,
        *,
        status: str | None = None,
        fornecedor_id: uuid.UUID | None = None,
        processo_id: uuid.UUID | None = None,
        em_lote_demo: bool | None = None,
        limite: int = 50,
        cursor: str | None = None,
    ) -> tuple[list[Row[Any]], str | None]:
        """Página por cursor `(criado_em, id)`, do mais novo para o mais antigo.

        Cada linha: `(Documento, fornecedor_id, fornecedor_nome, n_excecoes, risco_brl, codigos)`.
        """
        consulta = self._consulta_resumo()
        if status:
            consulta = consulta.where(Documento.status == status)
        if fornecedor_id:
            consulta = consulta.where(Documento.fornecedor_id == fornecedor_id)
        if em_lote_demo is not None:
            consulta = consulta.where(Documento.em_lote_demo == em_lote_demo)
        if processo_id:
            do_processo = (
                self._q(Linha)
                .with_only_columns(Linha.documento_id)
                .where(Linha.processo_id == processo_id)
            )
            consulta = consulta.where(Documento.id.in_(do_processo))
        if cursor:
            criado_em, id_ = decodificar_cursor(cursor)
            consulta = consulta.where(
                tuple_(Documento.criado_em, Documento.id) < tuple_(criado_em, id_)
            )
        linhas = list(
            self.db.execute(
                consulta.order_by(Documento.criado_em.desc(), Documento.id.desc()).limit(limite + 1)
            )
        )
        proximo = None
        if len(linhas) > limite:
            linhas = linhas[:limite]
            ultimo: Documento = linhas[-1][0]
            proximo = codificar_cursor(ultimo.criado_em, ultimo.id)
        return linhas, proximo

    def detalhe(self, documento_id: uuid.UUID) -> DetalheDocumento:
        """Documento completo em 5 consultas (documento, fornecedor, linhas, exceções, eventos)."""
        documento = self.obter(Documento, documento_id)
        fornecedor = None
        if documento.fornecedor_id:
            fornecedor = self.db.scalars(
                self._q(Fornecedor).where(Fornecedor.id == documento.fornecedor_id)
            ).first()
        linhas = [
            LinhaDetalhe(*campos)
            for campos in self.db.execute(
                self._q(Linha)
                .add_columns(Processo, Casamento, Provisao)
                .outerjoin(Processo, Processo.id == Linha.processo_id)
                .outerjoin(Casamento, Casamento.linha_id == Linha.id)
                .outerjoin(Provisao, Provisao.id == Casamento.provisao_id)
                .where(Linha.documento_id == documento_id)
                .order_by(Linha.ordem)
            )
        ]
        excecoes = self.db.scalars(
            self._q(Excecao)
            .where(Excecao.documento_id == documento_id)
            .order_by(Excecao.valor_brl_em_risco.desc(), Excecao.criado_em)
        ).all()
        eventos = self.db.scalars(
            self._q(Evento).where(Evento.documento_id == documento_id).order_by(Evento.id)
        ).all()
        return DetalheDocumento(documento, fornecedor, linhas, excecoes, eventos)

    def caminho_do_arquivo(self, documento_id: uuid.UUID) -> tuple[str, str | None]:
        """(caminho lógico no storage, tipo do arquivo)."""
        documento = self.obter(Documento, documento_id)
        if not documento.arquivo_path:
            raise SemArquivo
        return documento.arquivo_path, documento.tipo_arquivo

    def marcar_status(self, documento_id: uuid.UUID, status: str) -> Documento:
        documento = self.obter(Documento, documento_id)
        documento.status = status
        return documento

    def receber(
        self, storage: Storage, nome: str, conteudo: bytes, remetente: str | None
    ) -> DocumentoRecebido:
        """Recebe um arquivo (CF-105): inspeciona, guarda no storage e enfileira o processamento.

        Arquivo ruim vira documento `erro_arquivo` (sem job); PDF com senha vira `em_revisao` com
        a exceção `documento_protegido`. A transação é de quem chama (uma por arquivo).
        """
        inspecao = inspecionar(nome, conteudo)
        eventos = EventoController(self.db, self.tenant)
        base = {
            "nome_original": nome,
            "tipo_arquivo": inspecao.tipo,
            "sha256": inspecao.sha256,
            "remetente": remetente,
        }
        if inspecao.problema in PROBLEMAS_SEM_PROCESSAMENTO:
            mensagem = MENSAGEM_PROBLEMA[inspecao.problema]
            documento = Documento(**base, status="erro_arquivo", avisos=[inspecao.problema])
            self.adicionar(documento)
            self.db.flush()
            eventos.registrar(
                "erro",
                "erro",
                mensagem,
                documento_id=documento.id,
                dados={"problema": inspecao.problema},
            )
            return DocumentoRecebido(documento, mensagem)

        tipo = inspecao.tipo
        assert tipo is not None  # sem problema de tipo
        caminho = caminho_storage(self.tenant.empresa_id, inspecao.sha256, tipo)
        if not storage.exists(caminho):
            storage.put(caminho, conteudo, TIPOS_DE_CONTEUDO[tipo])

        avisos: list[str] = []
        repetido = self.db.scalars(
            self._q(Documento).where(Documento.sha256 == inspecao.sha256).limit(1)
        ).first()
        if repetido is not None:
            avisos.append("possivel_duplicata_exata")

        if inspecao.problema == "pdf_protegido":
            documento = Documento(
                **base,
                arquivo_path=caminho,
                status="em_revisao",
                avisos=[*avisos, "pdf_protegido"],
            )
            self.adicionar(documento)
            self.db.flush()
            self.adicionar(
                Excecao(
                    documento_id=documento.id,
                    tipo="documento_protegido",
                    severidade="revisar",
                    valor_brl_em_risco=0,
                    explicacao="O PDF pede senha e não pôde ser lido.",
                    explicacao_origem="template",
                    acao_sugerida="Peça ao fornecedor uma versão sem senha.",
                    status="aberta",
                )
            )
            eventos.registrar(
                "recebido",
                "aviso",
                "PDF protegido por senha: enviado para revisão.",
                documento_id=documento.id,
            )
            return DocumentoRecebido(documento, "PDF protegido por senha.")

        documento = Documento(
            **base, arquivo_path=caminho, status="recebido", avisos=avisos or None
        )
        self.adicionar(documento)
        self.db.flush()
        job = JobController(self.db, self.tenant).enfileirar(
            "processar", {"documento_id": str(documento.id)}
        )
        eventos.registrar(
            "recebido",
            "aviso" if avisos else "ok",
            "Documento recebido.",
            documento_id=documento.id,
            job_id=job.id,
            dados={"nome": nome, "possivel_duplicata_exata": bool(avisos)},
        )
        return DocumentoRecebido(
            documento, "Arquivo idêntico a outro já recebido." if avisos else None
        )
