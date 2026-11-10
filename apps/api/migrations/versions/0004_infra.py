"""Infra: job, evento, llm_call, ptax_cache e waitlist (CF-103).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-10
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0004"
down_revision: str | None = "0003"
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


def _enum(
    tabela: str, coluna: str, valores: tuple[str, ...]
) -> tuple[sa.String, sa.CheckConstraint]:
    lista = ", ".join(f"'{v}'" for v in valores)
    check = sa.CheckConstraint(f"{coluna} IN ({lista})", name=op.f(f"ck_{tabela}_{coluna}"))
    return sa.String(20), check


def upgrade() -> None:
    tipo_job, ck_tipo_job = _enum("job", "tipo", ("processar", "reprocessar", "reset_demo"))
    status_job, ck_status_job = _enum(
        "job", "status", ("pendente", "executando", "feito", "falhou")
    )
    op.create_table(
        "job",
        _uuid_pk(),
        _empresa_fk(),
        sa.Column("tipo", tipo_job, nullable=False),
        sa.Column("payload_json", pg.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", status_job, nullable=False, server_default="pendente"),
        sa.Column("tentativas", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_tentativas", sa.Integer, nullable=False, server_default="3"),
        sa.Column(
            "executar_apos",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("erro", sa.Text),
        sa.Column("iniciado_em", sa.DateTime(timezone=True)),
        sa.Column("terminado_em", sa.DateTime(timezone=True)),
        _criado_em(),
        ck_tipo_job,
        ck_status_job,
        sa.PrimaryKeyConstraint("id", name=op.f("pk_job")),
    )
    op.create_index(op.f("ix_job_empresa_id"), "job", ["empresa_id"])
    op.create_index(
        "ix_job_pendente_executar_apos",
        "job",
        ["executar_apos"],
        postgresql_where=sa.text("status = 'pendente'"),
    )

    etapa, ck_etapa = _enum(
        "evento",
        "etapa",
        (
            "recebido",
            "lido",
            "extraido",
            "processo",
            "codigos",
            "casado",
            "decidido",
            "reconferido",
            "erro",
        ),
    )
    status_ev, ck_status_ev = _enum("evento", "status", ("ok", "aviso", "erro"))
    op.create_table(
        "evento",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        _empresa_fk(),
        sa.Column("job_id", pg.UUID(as_uuid=True), sa.ForeignKey("job.id", ondelete="SET NULL")),
        sa.Column(
            "documento_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("documento.id", ondelete="SET NULL"),
        ),
        sa.Column("etapa", etapa, nullable=False),
        sa.Column("status", status_ev, nullable=False),
        sa.Column("mensagem", sa.Text, nullable=False),
        sa.Column("dados_json", pg.JSONB),
        _criado_em(),
        ck_etapa,
        ck_status_ev,
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evento")),
    )
    op.create_index(op.f("ix_evento_empresa_id"), "evento", ["empresa_id"])
    op.create_index("ix_evento_empresa_id_id", "evento", ["empresa_id", "id"])

    op.create_table(
        "llm_call",
        _uuid_pk(),
        _empresa_fk(),
        sa.Column(
            "documento_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("documento.id", ondelete="SET NULL"),
        ),
        sa.Column("etapa", sa.String(30), nullable=False),
        sa.Column("modelo", sa.String(80), nullable=False),
        sa.Column("prompt_id", sa.String(80), nullable=False),
        sa.Column("prompt_versao", sa.Integer, nullable=False),
        sa.Column("tokens_in", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_out", sa.Integer, nullable=False, server_default="0"),
        sa.Column("custo_usd", sa.Numeric(12, 6), nullable=False, server_default="0"),
        sa.Column("latencia_ms", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cache_hit", sa.Boolean, nullable=False, server_default="false"),
        _criado_em(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_llm_call")),
    )
    op.create_index(op.f("ix_llm_call_empresa_id"), "llm_call", ["empresa_id"])

    op.create_table(
        "ptax_cache",
        sa.Column("moeda", sa.CHAR(3), nullable=False),
        sa.Column("data", sa.Date, nullable=False),
        sa.Column("compra", sa.Numeric(12, 6), nullable=False),
        sa.Column("venda", sa.Numeric(12, 6), nullable=False),
        sa.Column("fonte", sa.String(20), nullable=False),
        sa.Column("boletim", sa.String(40)),
        _criado_em(),
        sa.PrimaryKeyConstraint("moeda", "data", name=op.f("pk_ptax_cache")),
    )

    op.create_table(
        "waitlist",
        _uuid_pk(),
        sa.Column("email", sa.String(200), nullable=False),
        sa.Column("empresa", sa.String(200), nullable=False),
        sa.Column("cargo", sa.String(100)),
        sa.Column("origem", sa.String(100)),
        _criado_em(),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_waitlist_email_minusculo")),
        sa.UniqueConstraint("email", name=op.f("uq_waitlist_email")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_waitlist")),
    )


def downgrade() -> None:
    for tabela in ("waitlist", "ptax_cache", "llm_call", "evento", "job"):
        op.drop_table(tabela)
