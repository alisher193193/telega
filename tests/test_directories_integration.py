"""Requires the prepared migration on the manually provisioned test database.

These tests never apply migrations, create schemas or change a working database.
"""
import datetime as dt
import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select, func, text
from app.core.exceptions import ValidationError, ConflictError, AccessDeniedError
from app.models import Permission, Role, User, Project, WorkRate, AuditLog, DirectoryMutation
from app.models.access import user_roles, role_permissions
from app.services import catalog
from tests.test_directories_unit import project_values


@pytest_asyncio.fixture
async def catalog_session(db_session):
    available = await db_session.scalar(text("SELECT to_regclass('public.directory_mutations') IS NOT NULL AND EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='work_sections' AND column_name='code')"))
    if not available:
        pytest.fail("Тестовая схема не готова: нужна c62d4e91b705 в work_accounting_test. Автоматическое применение запрещено.")
    role = Role(name='directory-tests-' + uuid.uuid4().hex)
    db_session.add(role)
    await db_session.flush()
    for code in ('projects.view', 'projects.manage', 'directories.manage'):
        permission = await db_session.scalar(select(Permission).where(Permission.code == code))
        if permission is None:
            permission = Permission(code=code)
            db_session.add(permission)
            await db_session.flush()
        await db_session.execute(role_permissions.insert().values(role_id=role.id, permission_id=permission.id))
    await db_session.execute(user_roles.insert().values(user_id=db_session.info['actor_id'], role_id=role.id))
    return db_session


async def save(session, kind, values, **kwargs):
    return await catalog.save(session, kind, values, user_id=session.info['actor_id'],
                              idempotency_key=kwargs.pop('idempotency_key', uuid.uuid4()), **kwargs)


async def prepare(session):
    suffix = uuid.uuid4().hex[:8]
    project = await save(session, 'project', project_values(code='P-' + suffix))
    contract = await save(session, 'contract', dict(project_id=str(project.id), number='C-' + suffix, status='draft'))
    section = await save(session, 'section', dict(project_id=str(project.id), contract_id=str(contract.id), name='Отделка', code='S-' + suffix))
    unit = await save(session, 'unit', dict(name='Квадратный метр', code='м²-' + suffix))
    work = await save(session, 'work_type', dict(work_section_id=str(section.id), name='Штукатурка', code='W-' + suffix, unit_id=str(unit.id)))
    return project, contract, section, unit, work


async def test_create_read_update_archive_restore(catalog_session):
    session = catalog_session
    row = await save(session, 'project', project_values(code=uuid.uuid4().hex))
    values = {key: value for key, value in catalog.snapshot('project', row).items() if key != 'archived'}
    values['name'] = 'Изменённый'
    row = await save(session, 'project', values, entity_id=row.id, expected_version=catalog.version('project', row))
    assert row.name == 'Изменённый'
    for archived in (True, False):
        await catalog.set_archived(session, 'project', row.id, archived, user_id=session.info['actor_id'],
            idempotency_key=uuid.uuid4(), expected_version=catalog.version('project', row))
        assert row.is_archived is archived
        assert await session.get(Project, row.id) is row
    actions = list((await session.scalars(select(AuditLog.action).where(AuditLog.entity_id == str(row.id)))).all())
    assert actions == ['directory.create', 'directory.update', 'directory.archive', 'directory.restore']


async def test_idempotent_create_and_payload_conflict(catalog_session):
    session = catalog_session
    key = uuid.uuid4()
    values = project_values(code=uuid.uuid4().hex)
    first = await save(session, 'project', values, idempotency_key=key)
    second = await save(session, 'project', values, idempotency_key=key)
    assert first.id == second.id
    assert await session.scalar(select(func.count()).select_from(DirectoryMutation).where(DirectoryMutation.idempotency_key == key)) == 1
    with pytest.raises(ConflictError):
        await save(session, 'project', dict(values, name='Different'), idempotency_key=key)


async def test_unique_codes_and_unit_symbols(catalog_session):
    session = catalog_session
    project, contract, section, unit, work = await prepare(session)
    for kind, row in [('project', project), ('section', section), ('unit', unit), ('work_type', work)]:
        values = {key: value for key, value in catalog.snapshot(kind, row).items() if key != 'archived'}
        values['code'] = values['code'].swapcase()
        with pytest.raises(ValidationError, match='уже существует'):
            await save(session, kind, values)


async def test_contract_project_validation(catalog_session):
    session = catalog_session
    project, contract, section, unit, work = await prepare(session)
    other = await save(session, 'project', project_values(code=uuid.uuid4().hex))
    with pytest.raises(ValidationError, match='Договор'):
        await save(session, 'section', dict(project_id=str(other.id), contract_id=str(contract.id), name='Wrong', code=uuid.uuid4().hex))


async def test_rate_history_and_replay(catalog_session):
    session = catalog_session
    project, contract, section, unit, work = await prepare(session)
    values = dict(project_id=str(project.id), contract_id=str(contract.id), work_type_id=str(work.id), unit_id=str(unit.id),
                  worker_rate='100.00', customer_rate='200.00', valid_from='2026-01-01', valid_to=None, is_active=True)
    first = await save(session, 'rate', values)
    expected = catalog.version('rate', first)
    key = uuid.uuid4()
    new_values = dict(values, worker_rate='150.00', customer_rate='250.00', valid_from='2026-02-01')
    second = await save(session, 'rate', new_values, entity_id=first.id, expected_version=expected, idempotency_key=key)
    replay = await save(session, 'rate', new_values, entity_id=first.id, expected_version=expected, idempotency_key=key)
    assert first.id != second.id == replay.id
    assert first.worker_rate == Decimal('100') and first.valid_to == dt.date(2026, 1, 31)
    assert second.worker_rate == Decimal('150')
    with pytest.raises(ValidationError, match='пересекается'):
        await save(session, 'rate', dict(values, valid_from='2026-01-15'))


async def test_search_filter_before_pagination(catalog_session):
    session = catalog_session
    code = uuid.uuid4().hex[:8]
    for i in range(11):
        await save(session, 'project', project_values(code=f'{code}-{i}', name=f'{code} Объект {i:02}'))
    first, more = await catalog.list_page(session, 'project', user_id=session.info['actor_id'], query=code, page=0, size=8)
    second, more_second = await catalog.list_page(session, 'project', user_id=session.info['actor_id'], query=code, page=1, size=8)
    assert len(first) == 8 and more and len(second) == 3 and not more_second
    found, _ = await catalog.list_page(session, 'project', user_id=session.info['actor_id'], query=f'{code} Объект 10', size=1)
    assert len(found) == 1 and found[0].name.endswith('10')


async def test_stale_update_rejected(catalog_session):
    session = catalog_session
    values = project_values(code=uuid.uuid4().hex)
    row = await save(session, 'project', values)
    old_version = catalog.version('project', row)
    await save(session, 'project', dict(values, name='Changed'), entity_id=row.id, expected_version=old_version)
    with pytest.raises(ConflictError):
        await save(session, 'project', dict(values, name='Stale'), entity_id=row.id, expected_version=old_version)


async def test_permissions_checked_for_read_and_write(catalog_session):
    session = catalog_session
    user = User(telegram_id=uuid.uuid4().int % (2**62), full_name='No rights')
    session.add(user)
    await session.flush()
    with pytest.raises(AccessDeniedError):
        await catalog.list_page(session, 'project', user_id=user.id)
    with pytest.raises(AccessDeniedError):
        await catalog.save(session, 'unit', dict(name='Метр', code=uuid.uuid4().hex), user_id=user.id, idempotency_key=uuid.uuid4())


async def test_contract_archive_and_restore(catalog_session):
    session = catalog_session
    _, contract, _, _, _ = await prepare(session)
    for flag in (True, False):
        await catalog.set_archived(session, 'contract', contract.id, flag, user_id=session.info['actor_id'],
            idempotency_key=uuid.uuid4(), expected_version=catalog.version('contract', contract))
        assert contract.status == ('archived' if flag else 'draft')


@pytest.mark.parametrize("name,role_index", [("Илья", 0), ("Асан", 0), ("Alisher", 1)])
async def test_bootstrap_roles_allow_directory_access(db_session, name, role_index):
    from sqlalchemy.dialects.postgresql import insert
    from app.models.access import user_roles
    from app.scripts.bootstrap_access import ensure_role_permissions, get_or_create_user
    from app.services.access import require_permission

    roles = await ensure_role_permissions(db_session)
    await ensure_role_permissions(db_session)
    user = await get_or_create_user(
        db_session, uuid.uuid4().int % (2**62), name,
    )
    await db_session.execute(insert(user_roles).values(
        user_id=user.id, role_id=roles[role_index].id,
    ).on_conflict_do_nothing())
    assert user.is_active
    for code in ("projects.view", "projects.manage", "directories.manage"):
        await require_permission(db_session, user.id, code)
    await catalog.list_page(db_session, "project", user_id=user.id)
    row = await catalog.save(
        db_session, "project", project_values(code=uuid.uuid4().hex),
        user_id=user.id, idempotency_key=uuid.uuid4(),
    )
    assert (await catalog.get(db_session, "project", row.id, user_id=user.id)).id == row.id
    values = {key: value for key, value in catalog.snapshot("project", row).items() if key != "archived"}
    values["name"] = "Изменённый объект"
    updated = await catalog.save(
        db_session, "project", values, user_id=user.id,
        idempotency_key=uuid.uuid4(), entity_id=row.id,
        expected_version=catalog.version("project", row),
    )
    assert updated.name == values["name"]
