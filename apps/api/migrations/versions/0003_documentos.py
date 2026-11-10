"""Documentos: documento, linha, embedding, casamento, exceção e decisão (CF-102).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-10
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column[Any]:
    return sa.Column("id", pg.UUID(as_uuid=True), primary_key=True)


def _empresa_fk() -> sa.Column[Any]:
    return sa.Column(
        "empresa_id", pg.UUID(as_uuid=True), sa.ForeignKey("empresa.id"), nullable=False
    )


def _criado_em() -> sa.Column[Any]:
    return sa.Column(
        "criado_em", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
    )


def _fk(coluna: str, alvo: str, *, nulo: bool, cascata: bool = False) -> sa.Column[Any]:
    return sa.Column(
        coluna,
        pg.UUID(as_uuid=True),
        sa.ForeignKey(alvo, ondelete="CASCADE") if cascata else sa.ForeignKey(alvo),
        nullable=nulo,
    )


def _enum(
    tabela: str, coluna: str, valores: tuple[str, ...], tamanho: int = 20
) -> tuple[sa.String, sa.CheckConstraint]:
    lista = ", ".join(f"'{v}'" for v in valores)
    check = sa.CheckConstraint(f"{coluna} IN ({lista})", name=op.f(f"ck_{tabela}_{coluna}"))
    return sa.String(tamanho), check


def _indice_empresa(tabela: str) -> None:
    op.create_index(op.f(f"ix_{tabela}_empresa_id"), tabela, ["empresa_id"])


def upgrade() -> None:
    tipo_doc, ck_tipo_doc = _enum(
        "documento",
        "tipo",
        ("fatura", "nota_debito", "extrato", "cte", "bl", "aviso_chegada", "outro", "desconhecido"),
    )
    tipo_arq, ck_tipo_arq = _enum("documento", "tipo_arquivo", ("pdf", "png", "jpg", "xml"))
    status_doc, ck_status_doc = _enum(
        "documento",
        "status",
        (
            "recebido",
            "processando",
            "aprovado_auto",
            "em_revisao",
            "bloqueado",
            "erro_arquivo",
            "separado",
            "arquivado",
        ),
    )
    op.create_table(
        "documento",
        _uuid_pk(),
        _empresa_fk(),
        sa.Column("tipo", tipo_doc, nullable=False, server_default="desconhecido"),
        sa.Column("arquivo_path", sa.Text),
        sa.Column("nome_original", sa.Text, nullable=False),
        sa.Column("tipo_arquivo", tipo_arq),
        sa.Column("sha256", sa.CHAR(64)),
        sa.Column("remetente", sa.String(200)),
        _fk("fornecedor_id", "fornecedor.id", nulo=True),
        sa.Column("numero", sa.String(80)),
        sa.Column("numero_normalizado", sa.String(80)),
        sa.Column("emissao", sa.Date),
        sa.Column("vencimento", sa.Date),
        sa.Column("moeda", sa.CHAR(3)),
        sa.Column("total", sa.Numeric(14, 2)),
        sa.Column("status", status_doc, nullable=False, server_default="recebido"),
        sa.Column("confianca", sa.Numeric(5, 4)),
        sa.Column("score_decisao", sa.Numeric(5, 4)),
        sa.Column("tau", sa.Numeric(5, 4)),
        sa.Column("extracao_json", pg.JSONB),
        sa.Column("avisos", pg.JSONB),
        _fk("documento_pai_id", "documento.id", nulo=True),
        sa.Column("em_lote_demo", sa.Boolean, nullable=False, server_default="false"),
        _criado_em(),
        sa.Column(
            "atualizado_em",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        ck_tipo_doc,
        ck_tipo_arq,
        ck_status_doc,
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documento")),
    )
    _indice_empresa("documento")
    op.create_index("ix_documento_empresa_sha256", "documento", ["empresa_id", "sha256"])

    estado, ck_estado = _enum(
        "linha",
        "estado",
        (
            "ok",
            "acima_tolerancia",
            "abaixo_previsto",
            "sem_provisao",
            "duplicada",
            "cambio_divergente",
            "pendente",
        ),
    )
    op.create_table(
        "linha",
        _uuid_pk(),
        _empresa_fk(),
        _fk("documento_id", "documento.id", nulo=False, cascata=True),
        sa.Column("ordem", sa.Integer, nullable=False),
        sa.Column("descricao", sa.Text, nullable=False),
        sa.Column("descricao_normalizada", sa.Text),
        sa.Column("qtd", sa.Numeric(14, 4)),
        sa.Column("valor_unit", sa.Numeric(14, 4)),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
        sa.Column("moeda", sa.CHAR(3), nullable=False),
        sa.Column("valor_brl", sa.Numeric(14, 2)),
        sa.Column("refs_json", pg.JSONB),
        _fk("processo_id", "processo.id", nulo=True),
        sa.Column("codigo_custo", sa.String(40), sa.ForeignKey("codigo_custo.codigo")),
        sa.Column("conf_extracao", sa.Numeric(5, 4)),
        sa.Column("conf_processo", sa.Numeric(5, 4)),
        sa.Column("conf_codigo", sa.Numeric(5, 4)),
        sa.Column("metodo_codigo", sa.String(40)),
        sa.Column("estado", estado, nullable=False, server_default="pendente"),
        sa.Column("bbox_json", pg.JSONB),
        _criado_em(),
        ck_estado,
        sa.PrimaryKeyConstraint("id", name=op.f("pk_linha")),
    )
    _indice_empresa("linha")
    op.create_index(op.f("ix_linha_documento_id"), "linha", ["documento_id"])

    origem_emb, ck_origem_emb = _enum("linha_embedding", "origem", ("treino", "correcao", "linha"))
    op.create_table(
        "linha_embedding",
        _uuid_pk(),
        _empresa_fk(),
        _fk("linha_id", "linha.id", nulo=True, cascata=True),
        _fk("fornecedor_id", "fornecedor.id", nulo=True),
        sa.Column("texto_normalizado", sa.Text, nullable=False),
        sa.Column(
            "codigo_custo", sa.String(40), sa.ForeignKey("codigo_custo.codigo"), nullable=False
        ),
        sa.Column("origem", origem_emb, nullable=False),
        sa.Column("vetor", Vector(768), nullable=False),
        _criado_em(),
        ck_origem_emb,
        sa.PrimaryKeyConstraint("id", name=op.f("pk_linha_embedding")),
    )
    _indice_empresa("linha_embedding")
    op.execute(
        "CREATE INDEX ix_linha_embedding_vetor_hnsw ON linha_embedding "
        "USING hnsw (vetor vector_cosine_ops)"
    )

    op.create_table(
        "casamento",
        _uuid_pk(),
        _empresa_fk(),
        _fk("linha_id", "linha.id", nulo=False, cascata=True),
        _fk("provisao_id", "provisao.id", nulo=False),
        sa.Column("custo", sa.Numeric(10, 6), nullable=False),
        sa.Column("diferenca", sa.Numeric(14, 2), nullable=False),
        sa.Column("moeda_comparacao", sa.CHAR(3), nullable=False),
        sa.Column("diferenca_brl", sa.Numeric(14, 2), nullable=False),
        sa.Column("ptax", sa.Numeric(12, 6)),
        sa.Column("ptax_data", sa.Date),
        sa.Column("solver", sa.String(20), nullable=False),
        _criado_em(),
        sa.UniqueConstraint("linha_id", name=op.f("uq_casamento_linha_id")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_casamento")),
    )
    _indice_empresa("casamento")

    tipo_exc, ck_tipo_exc = _enum(
        "excecao",
        "tipo",
        (
            "acima_tolerancia",
            "sem_provisao",
            "duplicada",
            "cambio_divergente",
            "provisao_sem_fatura",
            "sem_processo",
            "confirmar_processo",
            "codigo_incerto",
            "extracao_inconsistente",
            "documento_protegido",
            "moeda_sem_cotacao",
            "possivel_duplicata_exata",
        ),
        tamanho=30,
    )
    sev, ck_sev = _enum("excecao", "severidade", ("info", "revisar", "bloquear"))
    status_exc, ck_status_exc = _enum("excecao", "status", ("aberta", "resolvida", "descartada"))
    op.create_table(
        "excecao",
        _uuid_pk(),
        _empresa_fk(),
        _fk("documento_id", "documento.id", nulo=False, cascata=True),
        _fk("linha_id", "linha.id", nulo=True, cascata=True),
        _fk("provisao_id", "provisao.id", nulo=True),
        sa.Column("tipo", tipo_exc, nullable=False),
        sa.Column("severidade", sev, nullable=False),
        sa.Column("valor_brl_em_risco", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("explicacao", sa.Text),
        sa.Column("explicacao_origem", sa.String(20)),
        sa.Column("acao_sugerida", sa.Text),
        sa.Column("dados_json", pg.JSONB),
        sa.Column("status", status_exc, nullable=False, server_default="aberta"),
        _criado_em(),
        sa.Column("resolvida_em", sa.DateTime(timezone=True)),
        ck_tipo_exc,
        ck_sev,
        ck_status_exc,
        sa.PrimaryKeyConstraint("id", name=op.f("pk_excecao")),
    )
    _indice_empresa("excecao")
    op.create_index(op.f("ix_excecao_documento_id"), "excecao", ["documento_id"])
    op.create_index(
        "ix_excecao_empresa_status_valor",
        "excecao",
        ["empresa_id", "status", sa.text("valor_brl_em_risco DESC")],
    )

    acao, ck_acao = _enum(
        "decisao",
        "acao",
        ("aprovar", "contestar", "corrigir_processo", "corrigir_codigo", "repassar", "bloquear"),
    )
    op.create_table(
        "decisao",
        _uuid_pk(),
        _empresa_fk(),
        _fk("excecao_id", "excecao.id", nulo=True),
        _fk("documento_id", "documento.id", nulo=False),
        _fk("usuario_id", "usuario.id", nulo=False),
        sa.Column("acao", acao, nullable=False),
        sa.Column("comentario", sa.Text),
        sa.Column("dados_json", pg.JSONB),
        _criado_em(),
        ck_acao,
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decisao")),
    )
    _indice_empresa("decisao")
    op.create_index(op.f("ix_decisao_documento_id"), "decisao", ["documento_id"])


def downgrade() -> None:
    for tabela in (
        "decisao",
        "excecao",
        "casamento",
        "linha_embedding",
        "linha",
        "documento",
    ):
        op.drop_table(tabela)
