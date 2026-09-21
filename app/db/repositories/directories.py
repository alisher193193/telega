from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.directories import Contract, Project


async def list_active_projects(session: AsyncSession, *, limit: int = 30) -> list[Project]:
    stmt = (
        select(Project)
        .where(Project.is_archived.is_(False))
        .order_by(Project.name)
        .limit(limit)
    )
    result = await session.scalars(stmt)
    return list(result.all())


async def list_contracts_for_project(session: AsyncSession, project_id: uuid.UUID) -> list[Contract]:
    stmt = select(Contract).where(Contract.project_id == project_id).order_by(Contract.number)
    result = await session.scalars(stmt)
    return list(result.all())
