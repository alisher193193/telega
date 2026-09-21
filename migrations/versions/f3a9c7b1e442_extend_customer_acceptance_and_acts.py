"""extend customer acceptance and act lines with volume/snapshot fields

Revision ID: f3a9c7b1e442
Revises: ab12c4d1d9ef
Create Date: 2026-09-21

"""

from alembic import op
import sqlalchemy as sa


revision = "f3a9c7b1e442"
down_revision = "ab12c4d1d9ef"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customer_acceptances",
        sa.Column("accepted_volume", sa.Numeric(18, 3), nullable=False, server_default="0"),
    )
    op.add_column(
        "customer_acceptances",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="accept"),
    )
    op.add_column(
        "customer_acceptances",
        sa.Column("accepted_by_user_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_customer_acceptances_accepted_by_user_id_users"),
        "customer_acceptances",
        "users",
        ["accepted_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_customer_acceptances_accepted_by_user_id"),
        "customer_acceptances",
        ["accepted_by_user_id"],
        unique=False,
    )

    op.add_column(
        "acts",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "acts",
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
    )

    op.add_column(
        "act_lines",
        sa.Column("unit_price", sa.Numeric(18, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "act_lines",
        sa.Column("work_type_name", sa.String(length=200), nullable=False, server_default=""),
    )
    op.add_column(
        "act_lines",
        sa.Column("unit_name", sa.String(length=50), nullable=False, server_default=""),
    )
    op.add_column(
        "act_lines",
        sa.Column("location_snapshot", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("act_lines", "location_snapshot")
    op.drop_column("act_lines", "unit_name")
    op.drop_column("act_lines", "work_type_name")
    op.drop_column("act_lines", "unit_price")

    op.drop_column("acts", "cancellation_reason")
    op.drop_column("acts", "cancelled_at")

    op.drop_index(op.f("ix_customer_acceptances_accepted_by_user_id"), table_name="customer_acceptances")
    op.drop_constraint(
        op.f("fk_customer_acceptances_accepted_by_user_id_users"),
        "customer_acceptances",
        type_="foreignkey",
    )
    op.drop_column("customer_acceptances", "accepted_by_user_id")
    op.drop_column("customer_acceptances", "kind")
    op.drop_column("customer_acceptances", "accepted_volume")
