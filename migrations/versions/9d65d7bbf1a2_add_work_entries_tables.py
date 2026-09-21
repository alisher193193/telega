"""add work entries tables

Revision ID: 9d65d7bbf1a2
Revises: 1d3f2b4cf7ac
Create Date: 2026-09-21

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision = "9d65d7bbf1a2"
down_revision = "1d3f2b4cf7ac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_entries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("contract_id", sa.UUID(), nullable=True),
        sa.Column("work_section_id", sa.UUID(), nullable=True),
        sa.Column("work_type_id", sa.UUID(), nullable=False),
        sa.Column("unit_id", sa.UUID(), nullable=False),
        sa.Column("worker_id", sa.UUID(), nullable=True),
        sa.Column("crew_id", sa.UUID(), nullable=True),
        sa.Column("floor", sa.String(length=50), nullable=True),
        sa.Column("room", sa.String(length=100), nullable=True),
        sa.Column("item_number", sa.String(length=100), nullable=True),
        sa.Column("axes", sa.String(length=200), nullable=True),
        sa.Column("location_note", sa.Text(), nullable=True),
        sa.Column("claimed_volume", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("worker_rate_snapshot", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("customer_rate_snapshot", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_additional", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="done"),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_work_entries_project_id_projects"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], name=op.f("fk_work_entries_contract_id_contracts"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_section_id"], ["work_sections.id"], name=op.f("fk_work_entries_work_section_id_work_sections"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["work_type_id"], ["work_types.id"], name=op.f("fk_work_entries_work_type_id_work_types"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["unit_id"], ["units.id"], name=op.f("fk_work_entries_unit_id_units"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], name=op.f("fk_work_entries_worker_id_workers"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["crew_id"], ["crews.id"], name=op.f("fk_work_entries_crew_id_crews"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_entries")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_work_entries_idempotency_key")),
    )
    op.create_index(op.f("ix_work_entries_entry_date"), "work_entries", ["entry_date"], unique=False)
    op.create_index(op.f("ix_work_entries_project_id"), "work_entries", ["project_id"], unique=False)
    op.create_index(op.f("ix_work_entries_contract_id"), "work_entries", ["contract_id"], unique=False)
    op.create_index(op.f("ix_work_entries_work_section_id"), "work_entries", ["work_section_id"], unique=False)
    op.create_index(op.f("ix_work_entries_work_type_id"), "work_entries", ["work_type_id"], unique=False)
    op.create_index(op.f("ix_work_entries_unit_id"), "work_entries", ["unit_id"], unique=False)
    op.create_index(op.f("ix_work_entries_worker_id"), "work_entries", ["worker_id"], unique=False)
    op.create_index(op.f("ix_work_entries_crew_id"), "work_entries", ["crew_id"], unique=False)

    op.create_table(
        "work_entry_allocations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("work_entry_id", sa.UUID(), nullable=False),
        sa.Column("worker_id", sa.UUID(), nullable=False),
        sa.Column("allocated_volume", sa.Numeric(precision=18, scale=3), nullable=False),
        sa.Column("individual_rate", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("rate_source", sa.String(length=50), nullable=False, server_default="worker_rate"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["work_entry_id"], ["work_entries.id"], name=op.f("fk_work_entry_allocations_work_entry_id_work_entries"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], name=op.f("fk_work_entry_allocations_worker_id_workers"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_entry_allocations")),
    )
    op.create_index(op.f("ix_work_entry_allocations_work_entry_id"), "work_entry_allocations", ["work_entry_id"], unique=False)
    op.create_index(op.f("ix_work_entry_allocations_worker_id"), "work_entry_allocations", ["worker_id"], unique=False)

    op.create_table(
        "work_status_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("work_entry_id", sa.UUID(), nullable=False),
        sa.Column("old_status", sa.String(length=50), nullable=True),
        sa.Column("new_status", sa.String(length=50), nullable=False),
        sa.Column("changed_by", sa.UUID(), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["work_entry_id"], ["work_entries.id"], name=op.f("fk_work_status_history_work_entry_id_work_entries"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_status_history")),
    )
    op.create_index(op.f("ix_work_status_history_work_entry_id"), "work_status_history", ["work_entry_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_work_status_history_work_entry_id"), table_name="work_status_history")
    op.drop_table("work_status_history")

    op.drop_index(op.f("ix_work_entry_allocations_worker_id"), table_name="work_entry_allocations")
    op.drop_index(op.f("ix_work_entry_allocations_work_entry_id"), table_name="work_entry_allocations")
    op.drop_table("work_entry_allocations")

    op.drop_index(op.f("ix_work_entries_crew_id"), table_name="work_entries")
    op.drop_index(op.f("ix_work_entries_worker_id"), table_name="work_entries")
    op.drop_index(op.f("ix_work_entries_unit_id"), table_name="work_entries")
    op.drop_index(op.f("ix_work_entries_work_type_id"), table_name="work_entries")
    op.drop_index(op.f("ix_work_entries_work_section_id"), table_name="work_entries")
    op.drop_index(op.f("ix_work_entries_contract_id"), table_name="work_entries")
    op.drop_index(op.f("ix_work_entries_project_id"), table_name="work_entries")
    op.drop_index(op.f("ix_work_entries_entry_date"), table_name="work_entries")
    op.drop_table("work_entries")
