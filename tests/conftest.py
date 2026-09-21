from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest_asyncio


@pytest_asyncio.fixture
async def db_session():
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.config import get_settings

    # Some unrelated tests monkeypatch env vars and call get_settings(), which
    # is lru_cache'd; make sure we build the engine from the real container env.
    get_settings.cache_clear()

    from app.db.session import engine

    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest_asyncio.fixture
async def work_entry_factory(db_session):
    from app.models.directories import Contract, Project, Unit, WorkType
    from app.models.work_entries import WorkEntry

    async def _create(
        *,
        claimed_volume: Decimal = Decimal("100"),
        customer_rate_snapshot: Decimal = Decimal("500"),
        status: str = "accepted_internal",
    ):
        suffix = uuid.uuid4().hex[:8]
        unit = Unit(code=f"unit-{suffix}", name="м2")
        work_type = WorkType(code=f"wt-{suffix}", name="Штукатурка стен", unit=unit)
        project = Project(code=f"proj-{suffix}", name="Тестовый объект")
        contract = Contract(project=project, number=f"contract-{suffix}")

        db_session.add_all([unit, work_type, project, contract])
        await db_session.flush()

        entry = WorkEntry(
            entry_date=dt.date.today(),
            project_id=project.id,
            contract_id=contract.id,
            work_type_id=work_type.id,
            unit_id=unit.id,
            floor="3",
            room="301",
            claimed_volume=claimed_volume,
            customer_rate_snapshot=customer_rate_snapshot,
            status=status,
            idempotency_key=f"key-{uuid.uuid4().hex}",
        )
        db_session.add(entry)
        await db_session.flush()
        return entry, project, contract

    return _create


@pytest_asyncio.fixture
async def internal_acceptance_factory(db_session):
    from app.models.work_acceptance import InternalAcceptance

    async def _create(work_entry_id, delta_volume: Decimal, is_active: bool = True):
        acceptance = InternalAcceptance(
            work_entry_id=work_entry_id,
            delta_volume=delta_volume,
            is_active=is_active,
        )
        db_session.add(acceptance)
        await db_session.flush()
        return acceptance

    return _create
