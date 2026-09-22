from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.directories import Contract, Project


async def list_active_projects(session: AsyncSession, *, limit: int = 10, offset: int = 0) -> list[Project]:
    stmt = (
        select(Project)
        .where(Project.is_archived.is_(False))
        .order_by(Project.name, Project.id)
        .limit(limit).offset(offset)
    )
    result = await session.scalars(stmt)
    return list(result.all())


async def list_contracts_for_project(session: AsyncSession, project_id: uuid.UUID, *, limit: int = 10, offset: int = 0) -> list[Contract]:
    stmt = select(Contract).where(Contract.project_id == project_id, Contract.status != "archived").order_by(Contract.number, Contract.id).limit(limit).offset(offset)
    result = await session.scalars(stmt)
    return list(result.all())
