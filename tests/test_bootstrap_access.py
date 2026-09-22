from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
import uuid

from sqlalchemy import select, func

from app.scripts import bootstrap_access
from app.models import Permission
from app.models.access import role_permissions


async def test_missing_acts_view_created_once(monkeypatch):
    assert 'acts.view' in bootstrap_access.PERMISSIONS
    monkeypatch.setattr(bootstrap_access, 'PERMISSIONS', {'acts.view': 'Просмотр актов'})
    session = SimpleNamespace(scalar=AsyncMock(return_value=None), add=MagicMock(), flush=AsyncMock())
    first = await bootstrap_access.get_or_create_permissions(session)
    assert first[0].code == 'acts.view'
    session.scalar.return_value = first[0]
    second = await bootstrap_access.get_or_create_permissions(session)
    assert second[0] is first[0]
    session.add.assert_called_once_with(first[0])
    session.flush.assert_awaited_once()


async def test_bootstrap_restores_missing_permission_and_grants_idempotently(db_session):
    # Temporarily rename the fixture's permission inside its rollback transaction.
    existing = await db_session.scalar(select(Permission).where(Permission.code == 'acts.view'))
    existing.code = f'fixture.old.{uuid.uuid4().hex}'
    await db_session.flush()

    roles = await bootstrap_access.ensure_role_permissions(db_session)
    permission = await db_session.scalar(select(Permission).where(Permission.code == 'acts.view'))
    assert permission is not None
    assert {role.name for role in roles} == {'admin', 'developer'}
    before = await db_session.scalar(select(func.count()).select_from(role_permissions))

    repeated = await bootstrap_access.ensure_role_permissions(db_session)
    assert [role.id for role in repeated] == [role.id for role in roles]
    assert await db_session.scalar(select(func.count()).select_from(role_permissions)) == before
    assert await db_session.scalar(select(func.count()).select_from(Permission).where(Permission.code == 'acts.view')) == 1
    for role in roles:
        count = await db_session.scalar(select(func.count()).select_from(role_permissions).where(
            role_permissions.c.role_id == role.id,
            role_permissions.c.permission_id == permission.id,
        ))
        assert count == 1
