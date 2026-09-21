from __future__ import annotations

import datetime as dt
import uuid
from decimal import Decimal

import pytest_asyncio


import os
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from tests.db_safety import validate_test_database_url


def _test_url():
    try:
        return validate_test_database_url(os.getenv("TEST_DATABASE_URL"), os.getenv("DATABASE_URL"))
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from None


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    for item in items:
        if "db_session" in item.fixturenames:
            item.add_marker(pytest.mark.integration)


def pytest_collection_finish(session):
    if any(item.get_closest_marker("integration") for item in session.items):
        _test_url()


@pytest_asyncio.fixture
async def db_session():
    # Never import the application's engine. Never create/drop databases or schema.
    target = _test_url()
    engine = create_async_engine(target, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            actual = await conn.scalar(text("SELECT current_database()"))
            if actual != target.database or actual == "work_accounting" or not actual.endswith("_test"):
                raise pytest.UsageError("Сервер подключил не к разрешённой тестовой БД")
            await conn.rollback()
            trans = await conn.begin()
            session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
            try:
                from app.models.access import User, Role, Permission
                permissions = [Permission(code=code) for code in ("acts.manage", "acts.view", "works.accept_customer")]
                role = Role(name=f"test-{uuid.uuid4().hex}", permissions=permissions)
                actor = User(telegram_id=-uuid.uuid4().int % (2**62), full_name="Test actor", roles=[role])
                session.add(actor)
                # Reuse seeded permissions, if present in the manually provisioned test database.
                from sqlalchemy import select
                with session.no_autoflush:
                    for permission in list(role.permissions):
                        existing = await session.scalar(select(Permission).where(Permission.code == permission.code))
                        if existing is not None:
                            role.permissions.remove(permission)
                            session.expunge(permission)
                            role.permissions.append(existing)
                await session.flush()
                session.info["actor_id"] = actor.id
                yield session
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


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


@pytest.fixture(autouse=True)
def clear_settings_cache():
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
