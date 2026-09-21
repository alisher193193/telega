"""add directory tables

Revision ID: 5cced8f6e4e6
Revises: 20c175ae33ff
Create Date: 2026-09-21

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision = "5cced8f6e4e6"
down_revision = "20c175ae33ff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("customer", sa.String(length=255), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("planned_end_date", sa.Date(), nullable=True),
        sa.Column("actual_end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("contract_amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KZT"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
        sa.UniqueConstraint("code", name=op.f("uq_projects_code")),
    )

    op.create_table(
        "contracts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("number", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("contract_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("customer", sa.String(length=255), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="draft"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_contracts_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_contracts")),
    )
    op.create_index(op.f("ix_contracts_project_id"), "contracts", ["project_id"], unique=False)

    op.create_table(
        "work_sections",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("contract_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_work_sections_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contracts.id"],
            name=op.f("fk_work_sections_contract_id_contracts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_sections")),
    )
    op.create_index(op.f("ix_work_sections_project_id"), "work_sections", ["project_id"], unique=False)
    op.create_index(op.f("ix_work_sections_contract_id"), "work_sections", ["contract_id"], unique=False)

    op.create_table(
        "units",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_units")),
        sa.UniqueConstraint("code", name=op.f("uq_units_code")),
    )

    op.create_table(
        "work_types",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("work_section_id", sa.UUID(), nullable=True),
        sa.Column("unit_id", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_extra_work_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["work_section_id"],
            ["work_sections.id"],
            name=op.f("fk_work_types_work_section_id_work_sections"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["units.id"],
            name=op.f("fk_work_types_unit_id_units"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_types")),
        sa.UniqueConstraint("code", name=op.f("uq_work_types_code")),
    )
    op.create_index(op.f("ix_work_types_work_section_id"), "work_types", ["work_section_id"], unique=False)
    op.create_index(op.f("ix_work_types_unit_id"), "work_types", ["unit_id"], unique=False)

    op.create_table(
        "work_rates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("contract_id", sa.UUID(), nullable=True),
        sa.Column("work_type_id", sa.UUID(), nullable=False),
        sa.Column("unit_id", sa.UUID(), nullable=False),
        sa.Column("worker_rate", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("customer_rate", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_work_rates_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"],
            ["contracts.id"],
            name=op.f("fk_work_rates_contract_id_contracts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["work_type_id"],
            ["work_types.id"],
            name=op.f("fk_work_rates_work_type_id_work_types"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["unit_id"],
            ["units.id"],
            name=op.f("fk_work_rates_unit_id_units"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_work_rates")),
    )
    op.create_index(op.f("ix_work_rates_project_id"), "work_rates", ["project_id"], unique=False)
    op.create_index(op.f("ix_work_rates_contract_id"), "work_rates", ["contract_id"], unique=False)
    op.create_index(op.f("ix_work_rates_work_type_id"), "work_rates", ["work_type_id"], unique=False)
    op.create_index(op.f("ix_work_rates_unit_id"), "work_rates", ["unit_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_work_rates_unit_id"), table_name="work_rates")
    op.drop_index(op.f("ix_work_rates_work_type_id"), table_name="work_rates")
    op.drop_index(op.f("ix_work_rates_contract_id"), table_name="work_rates")
    op.drop_index(op.f("ix_work_rates_project_id"), table_name="work_rates")
    op.drop_table("work_rates")

    op.drop_index(op.f("ix_work_types_unit_id"), table_name="work_types")
    op.drop_index(op.f("ix_work_types_work_section_id"), table_name="work_types")
    op.drop_table("work_types")

    op.drop_table("units")

    op.drop_index(op.f("ix_work_sections_contract_id"), table_name="work_sections")
    op.drop_index(op.f("ix_work_sections_project_id"), table_name="work_sections")
    op.drop_table("work_sections")

    op.drop_index(op.f("ix_contracts_project_id"), table_name="contracts")
    op.drop_table("contracts")
    op.drop_table("projects")
