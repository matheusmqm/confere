"""Novo status de documento `aprovado_manual` (aprovação humana, separada da da IA) (CF-111).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ANTIGOS = (
    "recebido",
    "processando",
    "aprovado_auto",
    "em_revisao",
    "bloqueado",
    "erro_arquivo",
    "separado",
    "arquivado",
)
NOVOS = (*ANTIGOS, "aprovado_manual")


def _trocar_check(valores: tuple[str, ...]) -> None:
    lista = ", ".join(f"'{v}'" for v in valores)
    op.drop_constraint(op.f("ck_documento_status"), "documento", type_="check")
    op.create_check_constraint(op.f("ck_documento_status"), "documento", f"status IN ({lista})")


def upgrade() -> None:
    _trocar_check(NOVOS)


def downgrade() -> None:
    # Documentos já aprovados manualmente voltam para a revisão antes de estreitar o CHECK.
    op.execute("UPDATE documento SET status = 'em_revisao' WHERE status = 'aprovado_manual'")
    _trocar_check(ANTIGOS)
