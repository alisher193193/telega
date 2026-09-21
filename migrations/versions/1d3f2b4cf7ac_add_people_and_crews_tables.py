"""add people and crews tables

Revision ID: 1d3f2b4cf7ac
Revises: 5cced8f6e4e6
Create Date: 2026-09-21

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision = "1d3f2b4cf7ac"
down_revision = "5cced8f6e4e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("specialty", sa.String(length=200), nullable=True),
        sa.Column("payment_type", sa.String(length=50), nullable=False, server_default="piecework"),
        sa.Column("base_rate", sa.Numeric(precision=18, scale=2), nullable=True),
        sa.Column("current_project_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="working"),
        sa.Column("hire_date", sa.Date(), nullable=True),
        sa.Column("termination_date", sa.Date(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["current_project_id"],
            ["projects.id"],
            name=op.f("fk_workers_current_project_id_projects"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workers")),
    )
    op.create_index(op.f("ix_workers_current_project_id"), "workers", ["current_project_id"], unique=False)

    op.create_table(
        "crews",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("leader_worker_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["leader_worker_id"],
            ["workers.id"],
            name=op.f("fk_crews_leader_worker_id_workers"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crews")),
    )
    op.create_index(op.f("ix_crews_leader_worker_id"), "crews", ["leader_worker_id"], unique=False)

    op.create_table(
        "crew_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("crew_id", sa.UUID(), nullable=False),
        sa.Column("worker_id", sa.UUID(), nullable=False),
        sa.Column("joined_at", sa.Date(), nullable=False),
        sa.Column("left_at", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["crew_id"],
            ["crews.id"],
            name=op.f("fk_crew_members_crew_id_crews"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["worker_id"],
            ["workers.id"],
            name=op.f("fk_crew_members_worker_id_workers"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_crew_members")),
    )
    op.create_index(op.f("ix_crew_members_crew_id"), "crew_members", ["crew_id"], unique=False)
    op.create_index(op.f("ix_crew_members_worker_id"), "crew_members", ["worker_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_crew_members_worker_id"), table_name="crew_members")
    op.drop_index(op.f("ix_crew_members_crew_id"), table_name="crew_members")
    op.drop_table("crew_members")

    op.drop_index(op.f("ix_crews_leader_worker_id"), table_name="crews")
    op.drop_table("crews")

    op.drop_index(op.f("ix_workers_current_project_id"), table_name="workers")
    op.drop_table("workers")
