from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.work_acceptance import InternalAcceptance


async def total_internal_accepted_volume(
    session: AsyncSession,
    work_entry_id: uuid.UUID,
) -> Decimal:
    stmt = select(func.coalesce(func.sum(InternalAcceptance.delta_volume), 0)).where(
        InternalAcceptance.work_entry_id == work_entry_id,
        InternalAcceptance.is_active.is_(True),
    )
    total = await session.scalar(stmt)
    return Decimal(total)
