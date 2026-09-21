from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundError
from app.models.acts import Act, ActLine
from app.core.enums import ActStatus


async def get(session: AsyncSession, act_id: uuid.UUID) -> Act | None:
    stmt = select(Act).where(Act.id == act_id).options(selectinload(Act.lines))
    return await session.scalar(stmt)


async def get_or_raise(session: AsyncSession, act_id: uuid.UUID) -> Act:
    act = await get(session, act_id)

    if act is None:
        raise NotFoundError(f"Акт {act_id} не найден")

    return act


async def get_for_update(session: AsyncSession, act_id: uuid.UUID) -> Act:
    """Lock the act row to serialize concurrent line additions/removals."""
    stmt = select(Act).where(Act.id == act_id).with_for_update().execution_options(populate_existing=True)
    act = await session.scalar(stmt)

    if act is None:
        raise NotFoundError(f"Акт {act_id} не найден")

    return act


async def list_lines(session: AsyncSession, act_id: uuid.UUID, *, limit: int | None = None, offset: int = 0) -> list[ActLine]:
    stmt = select(ActLine).where(ActLine.act_id == act_id, ActLine.cancelled_at.is_(None)).order_by(ActLine.created_at, ActLine.id)
    if limit is not None:
        stmt = stmt.limit(limit).offset(offset)
    result = await session.scalars(stmt)
    return list(result.all())


async def list_acts(
    session: AsyncSession,
    project_id: uuid.UUID | None = None,
    *, limit: int = 10, offset: int = 0,
) -> list[Act]:
    stmt = select(Act).order_by(Act.created_at.desc(), Act.id).limit(limit).offset(offset)

    if project_id is not None:
        stmt = stmt.where(Act.project_id == project_id)

    result = await session.scalars(stmt)
    return list(result.all())


async def get_line(session: AsyncSession, line_id: uuid.UUID) -> ActLine | None:
    return await session.get(ActLine, line_id, populate_existing=True)


async def volume_in_active_acts(
    session: AsyncSession,
    work_entry_id: uuid.UUID,
    exclude_act_id: uuid.UUID | None = None,
) -> Decimal:
    """Sum of accepted volumes already placed into non-cancelled acts for a work entry."""
    stmt = (
        select(func.coalesce(func.sum(ActLine.accepted_volume), 0))
        .join(Act, Act.id == ActLine.act_id)
        .where(
            ActLine.work_entry_id == work_entry_id,
            ActLine.cancelled_at.is_(None),
            Act.status != ActStatus.CANCELLED.value,
        )
    )

    if exclude_act_id is not None:
        stmt = stmt.where(Act.id != exclude_act_id)

    total = await session.scalar(stmt)
    return Decimal(total)
