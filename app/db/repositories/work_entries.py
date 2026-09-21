from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.work_entries import WorkEntry


async def lock_work_entry(session: AsyncSession, work_entry_id: uuid.UUID) -> WorkEntry:
    """Select the work entry FOR UPDATE to serialize concurrent acceptance/act operations."""
    stmt = select(WorkEntry).where(WorkEntry.id == work_entry_id).with_for_update()
    work_entry = await session.scalar(stmt)

    if work_entry is None:
        raise NotFoundError(f"Работа {work_entry_id} не найдена")

    return work_entry


async def get_work_entry(session: AsyncSession, work_entry_id: uuid.UUID) -> WorkEntry:
    work_entry = await session.get(WorkEntry, work_entry_id)

    if work_entry is None:
        raise NotFoundError(f"Работа {work_entry_id} не найдена")

    return work_entry


async def list_work_entries_for_project(
    session: AsyncSession,
    project_id: uuid.UUID,
) -> list[WorkEntry]:
    stmt = (
        select(WorkEntry)
        .where(WorkEntry.project_id == project_id)
        .order_by(WorkEntry.entry_date.desc())
    )
    result = await session.scalars(stmt)
    return list(result.all())
