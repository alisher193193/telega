"""Add section codes and idempotent directory operation receipts.

Revision ID: c62d4e91b705
Revises: a84e2d71c903
"""
from alembic import op
import sqlalchemy as sa

revision = "c62d4e91b705"
down_revision = "a84e2d71c903"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable for existing sections; all new/edited sections require a code in the service.
    op.add_column("work_sections", sa.Column("code", sa.String(100), nullable=True))
    op.create_unique_constraint(op.f("uq_work_sections_code"), "work_sections", ["code"])
    op.create_table(
        "directory_mutations",
        sa.Column("idempotency_key", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("idempotency_key", name=op.f("pk_directory_mutations")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL",
                                name=op.f("fk_directory_mutations_user_id_users")),
    )


def downgrade() -> None:
    op.drop_table("directory_mutations")
    op.drop_constraint(op.f("uq_work_sections_code"), "work_sections", type_="unique")
    op.drop_column("work_sections", "code")
