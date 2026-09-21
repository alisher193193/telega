"""add cash and payroll tables

Revision ID: 6d2f18a83d8f
Revises: 76526c9f5b18
Create Date: 2026-09-21

"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision = "6d2f18a83d8f"
down_revision = "76526c9f5b18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cash_accounts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("account_type", sa.String(length=50), nullable=False),
        sa.Column("owner", sa.String(length=100), nullable=True),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KZT"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("opening_balance", sa.Numeric(precision=18, scale=2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cash_accounts")),
    )

    op.create_table(
        "cash_transactions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("transaction_date", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("transaction_type", sa.String(length=50), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False, server_default="KZT"),
        sa.Column("source_account_id", sa.UUID(), nullable=True),
        sa.Column("target_account_id", sa.UUID(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("worker_id", sa.UUID(), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("document_reference", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="posted"),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_account_id"], ["cash_accounts.id"], name=op.f("fk_cash_transactions_source_account_id_cash_accounts"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_account_id"], ["cash_accounts.id"], name=op.f("fk_cash_transactions_target_account_id_cash_accounts"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_cash_transactions_project_id_projects"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], name=op.f("fk_cash_transactions_worker_id_workers"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cash_transactions")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_cash_transactions_idempotency_key")),
    )
    op.create_index(op.f("ix_cash_transactions_transaction_date"), "cash_transactions", ["transaction_date"], unique=False)
    op.create_index(op.f("ix_cash_transactions_transaction_type"), "cash_transactions", ["transaction_type"], unique=False)
    op.create_index(op.f("ix_cash_transactions_source_account_id"), "cash_transactions", ["source_account_id"], unique=False)
    op.create_index(op.f("ix_cash_transactions_target_account_id"), "cash_transactions", ["target_account_id"], unique=False)
    op.create_index(op.f("ix_cash_transactions_project_id"), "cash_transactions", ["project_id"], unique=False)
    op.create_index(op.f("ix_cash_transactions_worker_id"), "cash_transactions", ["worker_id"], unique=False)

    op.create_table(
        "worker_accruals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("worker_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("accrual_date", sa.Date(), nullable=False),
        sa.Column("accrual_type", sa.String(length=50), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("related_work_entry_id", sa.UUID(), nullable=True),
        sa.Column("basis", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="posted"),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], name=op.f("fk_worker_accruals_worker_id_workers"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_worker_accruals_project_id_projects"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_work_entry_id"], ["work_entries.id"], name=op.f("fk_worker_accruals_related_work_entry_id_work_entries"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_accruals")),
    )
    op.create_index(op.f("ix_worker_accruals_worker_id"), "worker_accruals", ["worker_id"], unique=False)
    op.create_index(op.f("ix_worker_accruals_project_id"), "worker_accruals", ["project_id"], unique=False)
    op.create_index(op.f("ix_worker_accruals_related_work_entry_id"), "worker_accruals", ["related_work_entry_id"], unique=False)

    op.create_table(
        "worker_payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("worker_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("payment_date", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("payment_type", sa.String(length=50), nullable=False),
        sa.Column("wallet_name", sa.String(length=100), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("related_cash_transaction_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="posted"),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["worker_id"], ["workers.id"], name=op.f("fk_worker_payments_worker_id_workers"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], name=op.f("fk_worker_payments_project_id_projects"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["related_cash_transaction_id"], ["cash_transactions.id"], name=op.f("fk_worker_payments_related_cash_transaction_id_cash_transactions"), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_worker_payments")),
    )
    op.create_index(op.f("ix_worker_payments_worker_id"), "worker_payments", ["worker_id"], unique=False)
    op.create_index(op.f("ix_worker_payments_project_id"), "worker_payments", ["project_id"], unique=False)
    op.create_index(op.f("ix_worker_payments_related_cash_transaction_id"), "worker_payments", ["related_cash_transaction_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_worker_payments_related_cash_transaction_id"), table_name="worker_payments")
    op.drop_index(op.f("ix_worker_payments_project_id"), table_name="worker_payments")
    op.drop_index(op.f("ix_worker_payments_worker_id"), table_name="worker_payments")
    op.drop_table("worker_payments")

    op.drop_index(op.f("ix_worker_accruals_related_work_entry_id"), table_name="worker_accruals")
    op.drop_index(op.f("ix_worker_accruals_project_id"), table_name="worker_accruals")
    op.drop_index(op.f("ix_worker_accruals_worker_id"), table_name="worker_accruals")
    op.drop_table("worker_accruals")

    op.drop_index(op.f("ix_cash_transactions_worker_id"), table_name="cash_transactions")
    op.drop_index(op.f("ix_cash_transactions_project_id"), table_name="cash_transactions")
    op.drop_index(op.f("ix_cash_transactions_target_account_id"), table_name="cash_transactions")
    op.drop_index(op.f("ix_cash_transactions_source_account_id"), table_name="cash_transactions")
    op.drop_index(op.f("ix_cash_transactions_transaction_type"), table_name="cash_transactions")
    op.drop_index(op.f("ix_cash_transactions_transaction_date"), table_name="cash_transactions")
    op.drop_table("cash_transactions")
    op.drop_table("cash_accounts")
