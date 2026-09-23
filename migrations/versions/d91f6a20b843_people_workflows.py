"""People workflows, specialties and single current crew membership.

Revision ID: d91f6a20b843
Revises: c62d4e91b705
"""
from alembic import op
import sqlalchemy as sa

revision = "d91f6a20b843"
down_revision = "c62d4e91b705"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "specialties",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_specialties")),
        sa.UniqueConstraint("normalized_name", name=op.f("uq_specialties_normalized_name")),
    )
    op.add_column("workers", sa.Column("specialty_id", sa.UUID(), nullable=True))
    op.create_foreign_key(op.f("fk_workers_specialty_id_specialties"), "workers", "specialties",
                          ["specialty_id"], ["id"], ondelete="RESTRICT")
    op.create_index(op.f("ix_workers_specialty_id"), "workers", ["specialty_id"])
    op.add_column("workers", sa.Column("terminated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("crew_members", sa.Column("joined_on", sa.DateTime(timezone=True), nullable=True))
    op.add_column("crew_members", sa.Column("left_on", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint(op.f("ck_workers_worker_rate"), "workers",
                               "base_rate IS NULL OR (base_rate >= 0 AND base_rate <> 'NaN'::numeric)")
    # Abort atomically if legacy data violates invariants; never silently repair history.
    op.create_index("uq_crew_members_open_worker", "crew_members", ["worker_id"],
                    unique=True, postgresql_where=sa.text("left_at IS NULL"))
    op.create_check_constraint(op.f("ck_crew_members_membership_dates"), "crew_members",
                               "left_at IS NULL OR left_at >= joined_at")
    op.create_check_constraint(op.f("ck_crew_members_membership_times"), "crew_members",
                               "left_on IS NULL OR (joined_on IS NOT NULL AND left_on >= joined_on)")


def downgrade():
    op.drop_constraint(op.f("ck_workers_worker_rate"), "workers", type_="check")
    # Removes new specialty links and exact timestamps. Historical DATE fields remain.
    op.drop_constraint(op.f("ck_crew_members_membership_times"), "crew_members", type_="check")
    op.drop_constraint(op.f("ck_crew_members_membership_dates"), "crew_members", type_="check")
    op.drop_index("uq_crew_members_open_worker", table_name="crew_members")
    op.drop_column("crew_members", "left_on")
    op.drop_column("crew_members", "joined_on")
    op.drop_column("workers", "terminated_at")
    op.drop_index(op.f("ix_workers_specialty_id"), table_name="workers")
    op.drop_constraint(op.f("fk_workers_specialty_id_specialties"), "workers", type_="foreignkey")
    op.drop_column("workers", "specialty_id")
    op.drop_table("specialties")
