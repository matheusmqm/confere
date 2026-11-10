"""Núcleo: empresa, usuário, fornecedor, processo, custos, sinônimos e provisões (CF-101).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10
"""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import sqlalchemy as sa
import yaml
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POLITICA_PADRAO = Path(__file__).resolve().parents[4] / "config" / "politica_padrao.yaml"


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
    tabela: str, coluna: str, valores: tuple[str, ...], tamanho: int = 20
) -> tuple[sa.String, sa.CheckConstraint]:
    """(coluna VARCHAR, CHECK) equivalentes a `enum_texto` dos models."""
    lista = ", ".join(f"'{v}'" for v in valores)
    check = sa.CheckConstraint(f"{coluna} IN ({lista})", name=op.f(f"ck_{tabela}_{coluna}"))
    return sa.String(tamanho), check


def _indice_empresa(tabela: str) -> None:
    op.create_index(op.f(f"ix_{tabela}_empresa_id"), tabela, ["empresa_id"])


def upgrade() -> None:
    with open(POLITICA_PADRAO, encoding="utf-8") as arquivo:
        politica = json.dumps(yaml.safe_load(arquivo))

    op.create_table(
        "empresa",
        _uuid_pk(),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("cnpj_ficticio", sa.String(18), nullable=False),
        sa.Column("politica_json", pg.JSONB, nullable=False, server_default=politica),
        _criado_em(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_empresa")),
    )

    papel, ck_papel = _enum("usuario", "papel", ("ap", "operacional", "gestor"))
    op.create_table(
        "usuario",
        _uuid_pk(),
        _empresa_fk(),
        sa.Column("email", sa.String(200), nullable=False),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("papel", papel, nullable=False),
        _criado_em(),
        ck_papel,
        sa.UniqueConstraint("empresa_id", "email", name=op.f("uq_usuario_empresa_email")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuario")),
    )
    _indice_empresa("usuario")

    tipo_forn, ck_tipo_forn = _enum(
        "fornecedor",
        "tipo",
        ("armador", "agente_exterior", "terminal", "armazem", "transportadora", "despachante"),
    )
    op.create_table(
        "fornecedor",
        _uuid_pk(),
        _empresa_fk(),
        sa.Column("nome", sa.String(200), nullable=False),
        sa.Column("tipo", tipo_forn, nullable=False),
        sa.Column("pais", sa.CHAR(2), nullable=False),
        sa.Column("moeda_padrao", sa.CHAR(3), nullable=False),
        sa.Column("dominio_email", sa.String(200), nullable=False),
        sa.Column("idioma", sa.CHAR(2), nullable=False),
        _criado_em(),
        ck_tipo_forn,
        sa.UniqueConstraint("empresa_id", "nome", name=op.f("uq_fornecedor_empresa_nome")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fornecedor")),
    )
    _indice_empresa("fornecedor")

    op.create_table(
        "fornecedor_alias",
        _uuid_pk(),
        _empresa_fk(),
        sa.Column(
            "fornecedor_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("fornecedor.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("alias", sa.String(200), nullable=False),
        sa.Column("alias_normalizado", sa.String(200), nullable=False),
        _criado_em(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fornecedor_alias")),
    )
    _indice_empresa("fornecedor_alias")
    op.create_index(
        op.f("ix_fornecedor_alias_fornecedor_id"), "fornecedor_alias", ["fornecedor_id"]
    )
    op.create_index(
        op.f("ix_fornecedor_alias_alias_normalizado"), "fornecedor_alias", ["alias_normalizado"]
    )

    modal, ck_modal = _enum("processo", "modal", ("maritimo", "aereo", "rodoviario"))
    status_proc, ck_status_proc = _enum("processo", "status", ("aberto", "faturado", "encerrado"))
    op.create_table(
        "processo",
        _uuid_pk(),
        _empresa_fk(),
        sa.Column("codigo", sa.String(40), nullable=False),
        sa.Column("cliente", sa.String(200), nullable=False),
        sa.Column("modal", modal, nullable=False),
        sa.Column("origem", sa.String(100), nullable=False),
        sa.Column("destino", sa.String(100), nullable=False),
        sa.Column("navio", sa.String(100)),
        sa.Column("viagem", sa.String(40)),
        sa.Column("etd", sa.Date),
        sa.Column("eta", sa.Date),
        sa.Column("status", status_proc, nullable=False, server_default="aberto"),
        _criado_em(),
        ck_modal,
        ck_status_proc,
        sa.UniqueConstraint("empresa_id", "codigo", name=op.f("uq_processo_empresa_codigo")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processo")),
    )
    _indice_empresa("processo")

    tipo_ref, ck_tipo_ref = _enum(
        "processo_referencia",
        "tipo",
        ("bl_master", "bl_house", "conteiner", "ref_cliente", "ref_agente"),
    )
    origem_ref, ck_origem_ref = _enum("processo_referencia", "origem", ("cadastro", "correcao"))
    op.create_table(
        "processo_referencia",
        _uuid_pk(),
        _empresa_fk(),
        sa.Column(
            "processo_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey("processo.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tipo", tipo_ref, nullable=False),
        sa.Column("valor", sa.String(100), nullable=False),
        sa.Column("valor_normalizado", sa.String(100), nullable=False),
        sa.Column("origem", origem_ref, nullable=False, server_default="cadastro"),
        _criado_em(),
        ck_tipo_ref,
        ck_origem_ref,
        sa.PrimaryKeyConstraint("id", name=op.f("pk_processo_referencia")),
    )
    _indice_empresa("processo_referencia")
    op.create_index(
        op.f("ix_processo_referencia_processo_id"), "processo_referencia", ["processo_id"]
    )
    op.create_index(
        "ix_processo_referencia_empresa_valor",
        "processo_referencia",
        ["empresa_id", "valor_normalizado"],
    )
    op.create_index(
        "ix_processo_referencia_valor_trgm",
        "processo_referencia",
        ["valor_normalizado"],
        postgresql_using="gin",
        postgresql_ops={"valor_normalizado": "gin_trgm_ops"},
    )

    op.create_table(
        "codigo_custo",
        sa.Column("codigo", sa.String(40), nullable=False),
        sa.Column("descricao", sa.Text, nullable=False),
        sa.Column("grupo", sa.String(40), nullable=False),
        sa.Column("unidade", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("codigo", name=op.f("pk_codigo_custo")),
    )

    origem_sin, ck_origem_sin = _enum(
        "sinonimo_custo", "origem", ("catalogo", "treino", "correcao")
    )
    op.create_table(
        "sinonimo_custo",
        _uuid_pk(),
        _empresa_fk(),
        sa.Column("fornecedor_id", pg.UUID(as_uuid=True), sa.ForeignKey("fornecedor.id")),
        sa.Column("texto_normalizado", sa.Text, nullable=False),
        sa.Column(
            "codigo_custo", sa.String(40), sa.ForeignKey("codigo_custo.codigo"), nullable=False
        ),
        sa.Column("origem", origem_sin, nullable=False),
        _criado_em(),
        ck_origem_sin,
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sinonimo_custo")),
    )
    _indice_empresa("sinonimo_custo")
    op.create_index(
        "uq_sinonimo_custo_empresa_fornecedor_texto",
        "sinonimo_custo",
        ["empresa_id", "fornecedor_id", "texto_normalizado"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )

    status_prov, ck_status_prov = _enum(
        "provisao", "status", ("aberta", "casada", "parcial", "cancelada")
    )
    op.create_table(
        "provisao",
        _uuid_pk(),
        _empresa_fk(),
        sa.Column(
            "processo_id", pg.UUID(as_uuid=True), sa.ForeignKey("processo.id"), nullable=False
        ),
        sa.Column(
            "fornecedor_id", pg.UUID(as_uuid=True), sa.ForeignKey("fornecedor.id"), nullable=False
        ),
        sa.Column(
            "codigo_custo", sa.String(40), sa.ForeignKey("codigo_custo.codigo"), nullable=False
        ),
        sa.Column("moeda", sa.CHAR(3), nullable=False),
        sa.Column("valor", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", status_prov, nullable=False, server_default="aberta"),
        _criado_em(),
        ck_status_prov,
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provisao")),
    )
    _indice_empresa("provisao")
    op.create_index(
        "ix_provisao_empresa_processo_fornecedor",
        "provisao",
        ["empresa_id", "processo_id", "fornecedor_id"],
    )


def downgrade() -> None:
    for tabela in (
        "provisao",
        "sinonimo_custo",
        "codigo_custo",
        "processo_referencia",
        "processo",
        "fornecedor_alias",
        "fornecedor",
        "usuario",
        "empresa",
    ):
        op.drop_table(tabela)
