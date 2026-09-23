"""Requires explicitly approved d91f6a20b843 on work_accounting_test; never migrates."""
import uuid
from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy import select, text, func
from app.models import Worker, Crew, CrewMember, Specialty, AuditLog
from app.models.access import user_roles
from app.scripts.bootstrap_access import ensure_role_permissions
from app.services import people
from app.core.exceptions import ValidationError, ConflictError
from tests.db_safety import validate_test_database_url

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def people_session(db_session):
    actual = await db_session.scalar(text("SELECT current_database()"))
    assert actual == "work_accounting_test", "Only work_accounting_test is authorized"
    ready = await db_session.scalar(text("SELECT to_regclass('public.specialties')"))
    if ready is None:
        pytest.fail("Нужна согласованная миграция d91f6a20b843 только в work_accounting_test; автоматическое применение запрещено")
    roles = await ensure_role_permissions(db_session)
    from sqlalchemy.dialects.postgresql import insert
    await db_session.execute(insert(user_roles).values(
        user_id=db_session.info["actor_id"], role_id=roles[0].id).on_conflict_do_nothing())
    return db_session


async def save(session, kind, values, **kwargs):
    return await people.save(session, kind, values, user_id=session.info["actor_id"],
                             idempotency_key=kwargs.pop("idempotency_key", uuid.uuid4()), **kwargs)


async def prepare(session):
    specialty = await save(session, "specialty", {"name": "Маляр " + uuid.uuid4().hex})
    worker = await save(session, "worker", dict(full_name="Иван Тест", specialty_id=specialty.id,
        payment_type="piecework", base_rate="1250.50", current_project_id=None))
    crew = await save(session, "crew", {"name": "Бригада тест"})
    return specialty, worker, crew


async def status(session, kind, row, inactive):
    return await people.change_status(session, kind, row.id, inactive=inactive, reason="тест",
        user_id=session.info["actor_id"], idempotency_key=uuid.uuid4(), expected_version=people.version(kind, row))


async def member(session, crew, worker, joining=True, **kwargs):
    return await people.membership(session, crew.id, worker.id, joining=joining,
        user_id=session.info["actor_id"], idempotency_key=kwargs.pop("idempotency_key", uuid.uuid4()), **kwargs)


async def test_worker_create_edit_replay_and_audit(people_session):
    s = people_session
    specialty, worker, _ = await prepare(s)
    values = dict(full_name="Новое имя", specialty_id=specialty.id, payment_type="daily",
                  base_rate="3000", current_project_id=None)
    key, version = uuid.uuid4(), people.version("worker", worker)
    edited = await save(s, "worker", values, entity_id=worker.id, expected_version=version, idempotency_key=key)
    replay = await save(s, "worker", values, entity_id=worker.id, expected_version=version, idempotency_key=key)
    assert edited.id == replay.id and edited.base_rate == Decimal("3000")
    logs = list((await s.scalars(select(AuditLog).where(AuditLog.entity_id == str(worker.id)))).all())
    assert len(logs) == 2 and all(log.request_id and log.user_id for log in logs)
    assert any(log.old_values and log.new_values["full_name"] == "Новое имя" for log in logs)


async def test_termination_restoration_preserves_membership(people_session):
    s = people_session
    _, worker, crew = await prepare(s)
    participation = await member(s, crew, worker)
    await status(s, "worker", worker, True)
    assert worker.terminated_at.tzinfo and participation.left_at
    with pytest.raises(ValidationError):
        await member(s, crew, worker)
    await status(s, "worker", worker, False)
    assert worker.status == "working" and worker.terminated_at is None
    newer = await member(s, crew, worker)
    assert newer.id != participation.id
    assert await s.get(CrewMember, participation.id) is participation


async def test_specialty_unique_archive_rename_and_restore(people_session):
    s = people_session
    specialty, worker, _ = await prepare(s)
    with pytest.raises(ValidationError):
        await save(s, "specialty", {"name": "  " + specialty.name.upper() + "  "})
    await status(s, "specialty", specialty, True)
    assert (await people.detail(s, "worker", worker.id, user_id=s.info["actor_id"]))["specialty_label"] == specialty.name
    with pytest.raises(ValidationError):
        await save(s, "worker", dict(full_name="Другой", specialty_id=specialty.id,
            payment_type="salary", base_rate="1", current_project_id=None))
    await status(s, "specialty", specialty, False)
    await save(s, "specialty", {"name": "Новое " + uuid.uuid4().hex},
               entity_id=specialty.id, expected_version=people.version("specialty", specialty))
    assert await s.get(Specialty, specialty.id)


async def test_crew_membership_idempotency_end_archive_restore(people_session):
    s = people_session
    _, worker, crew = await prepare(s)
    key = uuid.uuid4()
    first = await member(s, crew, worker, idempotency_key=key)
    assert (await member(s, crew, worker, idempotency_key=key)).id == first.id
    assert (await member(s, crew, worker)).id == first.id
    other = await save(s, "crew", {"name": "Другая"})
    with pytest.raises(ConflictError):
        await member(s, other, worker)
    await member(s, crew, worker, joining=False, membership_id=first.id)
    second = await member(s, other, worker)
    await status(s, "crew", other, True)
    assert second.left_at and first.left_at
    await status(s, "crew", other, False)
    assert other.status == "active"
    assert await s.scalar(select(func.count()).select_from(CrewMember).where(CrewMember.worker_id == worker.id)) == 2


async def test_failure_rolls_back_all_writes(people_session, monkeypatch):
    s = people_session
    before = await s.scalar(select(func.count()).select_from(Crew))
    async def fail(*args, **kwargs):
        raise RuntimeError("simulated audit failure")
    monkeypatch.setattr(people.audit, "record", fail)
    with pytest.raises(RuntimeError):
        async with s.begin_nested():
            await save(s, "crew", {"name": "Не сохранится"})
    assert await s.scalar(select(func.count()).select_from(Crew)) == before


async def test_database_rejects_two_open_memberships(people_session):
    from sqlalchemy.exc import IntegrityError
    from datetime import date
    s = people_session
    _, worker, crew = await prepare(s)
    await member(s, crew, worker)
    with pytest.raises(IntegrityError):
        async with s.begin_nested():
            s.add(CrewMember(worker_id=worker.id, crew_id=crew.id, joined_at=date.today()))
            await s.flush()


async def test_concurrent_additions_use_one_current_membership(db_session):
    """Two real connections, committed setup in test DB, archived cleanup (no deletes)."""
    import asyncio
    import os
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy.pool import NullPool
    from app.models import User, Role, Permission

    target = validate_test_database_url(os.getenv("TEST_DATABASE_URL"), os.getenv("DATABASE_URL"))
    assert target.database == "work_accounting_test"
    assert await db_session.scalar(text("SELECT current_database()")) == "work_accounting_test"
    if await db_session.scalar(text("SELECT to_regclass('public.specialties')")) is None:
        pytest.fail("Сначала согласуйте миграцию d91f6a20b843 на work_accounting_test")
    engine = create_async_engine(target, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    actor_id = worker_id = None
    crew_ids = []
    try:
        async with factory() as s, s.begin():
            assert await s.scalar(text("SELECT current_database()")) == "work_accounting_test"
            permissions = []
            for scope in ("people", "specialties", "crews"):
                for action in ("view", "manage"):
                    code = f"{scope}.{action}"
                    permission = await s.scalar(select(Permission).where(Permission.code == code))
                    if permission is None:
                        permission = Permission(code=code)
                        s.add(permission)
                    permissions.append(permission)
            actor = User(telegram_id=uuid.uuid4().int % (2**62), full_name="Concurrent test actor",
                         roles=[Role(name="concurrent-" + uuid.uuid4().hex, permissions=permissions)])
            s.add(actor)
            await s.flush()
            actor_id = actor.id
            s.info["actor_id"] = actor_id
            specialty, worker, first = await prepare(s)
            second = await save(s, "crew", {"name": "Concurrent second"})
            worker_id, specialty_id = worker.id, specialty.id
            crew_ids = [first.id, second.id]

        gate = asyncio.Event()
        async def join(crew_id):
            async with factory() as s:
                try:
                    async with s.begin():
                        await gate.wait()
                        return await people.membership(s, crew_id, worker_id, joining=True,
                            user_id=actor_id, idempotency_key=uuid.uuid4())
                except ConflictError:
                    return None
        tasks = [asyncio.create_task(join(crew_id)) for crew_id in crew_ids]
        gate.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), timeout=20)
        assert sum(row is not None for row in results) == 1
        async with factory() as s:
            count = await s.scalar(select(func.count()).select_from(CrewMember).where(
                CrewMember.worker_id == worker_id, CrewMember.left_at.is_(None)))
            assert count == 1
    finally:
        if worker_id:
            async with factory() as s, s.begin():
                s.info["actor_id"] = actor_id
                worker = await s.get(Worker, worker_id)
                await status(s, "worker", worker, True)
                for crew_id in crew_ids:
                    await status(s, "crew", await s.get(Crew, crew_id), True)
                await status(s, "specialty", await s.get(Specialty, specialty_id), True)
                (await s.get(User, actor_id)).is_active = False
        await engine.dispose()


async def test_ungranted_permissions_deny_all_mutations(people_session):
    from app.models import User
    from app.core.exceptions import AccessDeniedError
    s = people_session
    outsider = User(telegram_id=uuid.uuid4().int % (2**62), full_name="Без прав")
    s.add(outsider)
    await s.flush()
    _, worker, crew = await prepare(s)
    for kind, row in (("worker", worker), ("crew", crew)):
        with pytest.raises(AccessDeniedError):
            await people.get(s, kind, row.id, user_id=outsider.id)
        with pytest.raises(AccessDeniedError):
            await people.change_status(s, kind, row.id, inactive=True, user_id=outsider.id,
                idempotency_key=uuid.uuid4(), expected_version=people.version(kind, row))
    with pytest.raises(AccessDeniedError):
        await people.save(s, "specialty", {"name": "Запрещено"}, user_id=outsider.id, idempotency_key=uuid.uuid4())
    with pytest.raises(AccessDeniedError):
        await people.membership(s, crew.id, worker.id, joining=True, user_id=outsider.id, idempotency_key=uuid.uuid4())
