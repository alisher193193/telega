"""add customer acceptance and act tables

Revision ID: ab12c4d1d9ef
Revises: 6d2f18a83d8f
Create Date: 2026-09-21

"""

from alembic import op
import sqlalchemy as sa


revision = "ab12c4d1d9ef"
down_revision = "6d2f18a83d8f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_acceptances",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("work_entry_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("contract_id", sa.UUID(), nullable=True),
        sa.Column("accepted_by_customer", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="accepted"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["work_entry_id"], ["work_entries.id"], name=op.f("fk_customer_acceptances_work_entry_id_work_entries"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_customer_acceptances_project_id_projects"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], name=op.f("fk_customer_acceptances_contract_id_contracts"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customer_acceptances")),
    )
    op.create_index(op.f("ix_customer_acceptances_work_entry_id"), "customer_acceptances", ["work_entry_id"], unique=False)
    op.create_index(op.f("ix_customer_acceptances_project_id"), "customer_acceptances", ["project_id"], unique=False)
    op.create_index(op.f("ix_customer_acceptances_contract_id"), "customer_acceptances", ["contract_id"], unique=False)

    op.create_table(
        "acts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("contract_id", sa.UUID(), nullable=True),
        sa.Column("act_number", sa.String(length=100), nullable=False),
        sa.Column("act_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_acts_project_id_projects"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], name=op.f("fk_acts_contract_id_contracts"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_acts")),
        sa.UniqueConstraint("act_number", name=op.f("uq_acts_act_number")),
    )
    op.create_index(op.f("ix_acts_project_id"), "acts", ["project_id"], unique=False)
    op.create_index(op.f("ix_acts_contract_id"), "acts", ["contract_id"], unique=False)

    op.create_table(
        "act_lines",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("act_id", sa.UUID(), nullable=False),
        sa.Column("work_entry_id", sa.UUID(), nullable=False),
        sa.Column("accepted_volume", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["act_id"], ["acts.id"], name=op.f("fk_act_lines_act_id_acts"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_entry_id"], ["work_entries.id"], name=op.f("fk_act_lines_work_entry_id_work_entries"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_act_lines")),
    )
    op.create_index(op.f("ix_act_lines_act_id"), "act_lines", ["act_id"], unique=False)
    op.create_index(op.f("ix_act_lines_work_entry_id"), "act_lines", ["work_entry_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_act_lines_work_entry_id"), table_name="act_lines")
    op.drop_index(op.f("ix_act_lines_act_id"), table_name="act_lines")
    op.drop_table("act_lines")

    op.drop_index(op.f("ix_acts_contract_id"), table_name="acts")
    op.drop_index(op.f("ix_acts_project_id"), table_name="acts")
    op.drop_table("acts")

    op.drop_index(op.f("ix_customer_acceptances_contract_id"), table_name="customer_acceptances")
    op.drop_index(op.f("ix_customer_acceptances_project_id"), table_name="customer_acceptances")
    op.drop_index(op.f("ix_customer_acceptances_work_entry_id"), table_name="customer_acceptances")
    op.drop_table("customer_acceptances")
