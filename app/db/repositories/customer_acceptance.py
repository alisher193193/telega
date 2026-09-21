from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.acts import CustomerAcceptance


async def list_by_work_entry(
    session: AsyncSession,
    work_entry_id: uuid.UUID,
) -> list[CustomerAcceptance]:
    stmt = (
        select(CustomerAcceptance)
        .where(CustomerAcceptance.work_entry_id == work_entry_id)
        .order_by(CustomerAcceptance.accepted_at)
    )
    result = await session.scalars(stmt)
    return list(result.all())


async def total_accepted_volume(
    session: AsyncSession,
    work_entry_id: uuid.UUID,
) -> Decimal:
    """Net customer-accepted volume: sum of acceptances plus (negative) corrections."""
    stmt = select(func.coalesce(func.sum(CustomerAcceptance.accepted_volume), 0)).where(
        CustomerAcceptance.work_entry_id == work_entry_id,
        CustomerAcceptance.status == "accepted",
    )
    total = await session.scalar(stmt)
    return Decimal(total)


def create(
    *,
    work_entry_id: uuid.UUID,
    project_id: uuid.UUID | None,
    contract_id: uuid.UUID | None,
    accepted_volume: Decimal,
    kind: str,
    accepted_by_user_id: uuid.UUID | None,
    comment: str | None,
    idempotency_key: uuid.UUID | None = None,
) -> CustomerAcceptance:
    return CustomerAcceptance(
        idempotency_key=idempotency_key,
        work_entry_id=work_entry_id,
        project_id=project_id,
        contract_id=contract_id,
        accepted_volume=accepted_volume,
        kind=kind,
        accepted_by_customer=True,
        accepted_by_user_id=accepted_by_user_id,
        comment=comment,
    )
