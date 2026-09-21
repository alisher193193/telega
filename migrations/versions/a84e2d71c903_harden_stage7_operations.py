"""Add stage 7 idempotency and line cancellation metadata.

Revision ID: a84e2d71c903
Revises: f3a9c7b1e442
"""
from alembic import op
import sqlalchemy as sa

revision = "a84e2d71c903"
down_revision = "f3a9c7b1e442"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("customer_acceptances", "act_lines"):
        op.add_column(table, sa.Column("idempotency_key", sa.UUID(), nullable=True))
        op.create_unique_constraint(op.f(f"uq_{table}_idempotency_key"), table, ["idempotency_key"])
    op.add_column("act_lines", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("act_lines", sa.Column("cancelled_by", sa.UUID(), nullable=True))
    op.add_column("act_lines", sa.Column("cancellation_reason", sa.Text(), nullable=True))
    op.create_foreign_key(op.f("fk_act_lines_cancelled_by_users"), "act_lines", "users",
                          ["cancelled_by"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    # Rollback destroys operation identity/cancellation history; explicit approval required.
    op.drop_constraint(op.f("fk_act_lines_cancelled_by_users"), "act_lines", type_="foreignkey")
    op.drop_column("act_lines", "cancellation_reason")
    op.drop_column("act_lines", "cancelled_by")
    op.drop_column("act_lines", "cancelled_at")
    for table in ("act_lines", "customer_acceptances"):
        op.drop_constraint(op.f(f"uq_{table}_idempotency_key"), table, type_="unique")
        op.drop_column(table, "idempotency_key")
