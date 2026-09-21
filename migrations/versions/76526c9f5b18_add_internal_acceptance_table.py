"""add internal acceptance table

Revision ID: 76526c9f5b18
Revises: 9d65d7bbf1a2
Create Date: 2026-09-21

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision = "76526c9f5b18"
down_revision = "9d65d7bbf1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "internal_acceptances",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("work_entry_id", sa.UUID(), nullable=False),
        sa.Column("delta_volume", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("result_comment", sa.Text(), nullable=True),
        sa.Column("accepted_by_user_id", sa.UUID(), nullable=True),
        sa.Column("correction_reason", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["work_entry_id"], ["work_entries.id"], name=op.f("fk_internal_acceptances_work_entry_id_work_entries"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["accepted_by_user_id"], ["users.id"], name=op.f("fk_internal_acceptances_accepted_by_user_id_users"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_internal_acceptances")),
    )
    op.create_index(op.f("ix_internal_acceptances_work_entry_id"), "internal_acceptances", ["work_entry_id"], unique=False)
    op.create_index(op.f("ix_internal_acceptances_accepted_by_user_id"), "internal_acceptances", ["accepted_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_internal_acceptances_accepted_by_user_id"), table_name="internal_acceptances")
    op.drop_index(op.f("ix_internal_acceptances_work_entry_id"), table_name="internal_acceptances")
    op.drop_table("internal_acceptances")
