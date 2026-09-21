"""Run only against a manually provisioned, migrated *_test database."""
import datetime as dt
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select, func
from app.models.acts import ActLine, CustomerAcceptance
from app.models.work_entries import WorkStatusHistory
from app.core.exceptions import ValidationError, AccessDeniedError
from app.services import act, customer_acceptance as ca
from app.db.repositories import act as act_repo
from app.db.repositories.customer_acceptance import total_accepted_volume


async def prepared(session, work_entry_factory, internal_acceptance_factory, accepted='100'):
    entry, project, contract = await work_entry_factory()
    await internal_acceptance_factory(entry.id, Decimal('100'))
    user_id = session.info['actor_id']
    await ca.accept(session, work_entry_id=entry.id, volume=Decimal(accepted), user_id=user_id, idempotency_key=uuid.uuid4())
    draft = await act.create_draft(session, project_id=project.id, contract_id=contract.id,
        act_number=uuid.uuid4().hex, act_date=dt.date.today(), created_by=user_id)
    return entry, draft, user_id


async def test_fully_accepted_100_of_100_is_available_to_act(db_session, work_entry_factory, internal_acceptance_factory):
    entry, draft, user = await prepared(db_session, work_entry_factory, internal_acceptance_factory)
    candidates = await act.list_available_work(db_session, draft.id, user_id=user)
    assert [(work.id, available) for work, available in candidates] == [(entry.id, Decimal('100'))]
    assert await ca.list_available_for_project(db_session, entry.project_id) == []


async def test_idempotent_acceptance_and_line(db_session, work_entry_factory, internal_acceptance_factory):
    entry, draft, user = await prepared(db_session, work_entry_factory, internal_acceptance_factory, accepted='20')
    key = uuid.uuid4()
    first = await ca.accept(db_session, work_entry_id=entry.id, volume=Decimal('10'), user_id=user, idempotency_key=key)
    again = await ca.accept(db_session, work_entry_id=entry.id, volume=Decimal('10'), user_id=user, idempotency_key=key)
    assert first.id == again.id
    assert await total_accepted_volume(db_session, entry.id) == Decimal('30')
    key = uuid.uuid4()
    first_line = await act.add_line(db_session, act_id=draft.id, work_entry_id=entry.id, quantity=Decimal('10'), user_id=user, idempotency_key=key)
    second_line = await act.add_line(db_session, act_id=draft.id, work_entry_id=entry.id, quantity=Decimal('10'), user_id=user, idempotency_key=key)
    assert first_line.id == second_line.id
    assert await act.available_volume_for_act(db_session, entry.id) == Decimal('20')


async def test_correction_below_occupied_volume_rejected(db_session, work_entry_factory, internal_acceptance_factory):
    entry, draft, user = await prepared(db_session, work_entry_factory, internal_acceptance_factory)
    await act.add_line(db_session, act_id=draft.id, work_entry_id=entry.id, quantity=Decimal('90'), user_id=user, idempotency_key=uuid.uuid4())
    with pytest.raises(ValidationError):
        await ca.correct(db_session, work_entry_id=entry.id, delta_volume=Decimal('-20'), user_id=user, reason='fix')
    assert await total_accepted_volume(db_session, entry.id) == Decimal('100')


async def test_cancel_line_keeps_row_releases_volume_and_records_status(db_session, work_entry_factory, internal_acceptance_factory):
    entry, draft, user = await prepared(db_session, work_entry_factory, internal_acceptance_factory)
    line = await act.add_line(db_session, act_id=draft.id, work_entry_id=entry.id, quantity=Decimal('100'), user_id=user, idempotency_key=uuid.uuid4())
    assert entry.status == 'included_in_act'
    await act.remove_line(db_session, act_id=draft.id, line_id=line.id, user_id=user, reason='mistake')
    stored = await db_session.get(ActLine, line.id)
    assert stored is not None and stored.cancelled_by == user and stored.cancelled_at is not None
    assert draft.total_amount == Decimal('0')
    assert await act.available_volume_for_act(db_session, entry.id) == Decimal('100')
    assert entry.status == 'accepted_customer'
    history = (await db_session.scalars(select(WorkStatusHistory).where(WorkStatusHistory.work_entry_id == entry.id))).all()
    assert any(row.old_status == 'included_in_act' and row.new_status == 'accepted_customer' for row in history)


async def test_partial_act_allows_further_acceptance(db_session, work_entry_factory, internal_acceptance_factory):
    entry, draft, user = await prepared(db_session, work_entry_factory, internal_acceptance_factory, accepted='20')
    await act.add_line(db_session, act_id=draft.id, work_entry_id=entry.id, quantity=Decimal('10'), user_id=user, idempotency_key=uuid.uuid4())
    await ca.accept(db_session, work_entry_id=entry.id, volume=Decimal('80'), user_id=user, idempotency_key=uuid.uuid4())
    assert await total_accepted_volume(db_session, entry.id) == Decimal('100')
    assert entry.status == 'included_in_act'
    await act.cancel(db_session, act_id=draft.id, user_id=user, reason='fix')
    assert await act.available_volume_for_act(db_session, entry.id) == Decimal('100')
    assert entry.status == 'accepted_customer'


async def test_cancelled_acceptance_excluded(db_session, work_entry_factory, internal_acceptance_factory):
    entry, draft, user = await prepared(db_session, work_entry_factory, internal_acceptance_factory)
    row = await db_session.scalar(select(CustomerAcceptance).where(CustomerAcceptance.work_entry_id == entry.id))
    row.status = 'cancelled'
    await db_session.flush()
    assert await total_accepted_volume(db_session, entry.id) == Decimal('0')
    assert await act.list_available_work(db_session, draft.id, user_id=user) == []


async def test_cross_project_work_and_contract_rejected(db_session, work_entry_factory, internal_acceptance_factory):
    entry, draft, user = await prepared(db_session, work_entry_factory, internal_acceptance_factory)
    other, other_project, other_contract = await work_entry_factory()
    with pytest.raises(ValidationError):
        await act.create_draft(db_session, project_id=entry.project_id, contract_id=other_contract.id,
                               act_number=uuid.uuid4().hex, act_date=dt.date.today(), created_by=user)
    with pytest.raises(ValidationError):
        await act.add_line(db_session, act_id=draft.id, work_entry_id=other.id, quantity=Decimal('1'), user_id=user, idempotency_key=uuid.uuid4())


async def test_active_user_without_permission_cannot_mutate(db_session, work_entry_factory, internal_acceptance_factory):
    from app.models.access import User
    outsider = User(telegram_id=uuid.uuid4().int % (2**62), full_name='No permissions')
    db_session.add(outsider)
    await db_session.flush()
    entry, draft, user = await prepared(db_session, work_entry_factory, internal_acceptance_factory)
    with pytest.raises(AccessDeniedError):
        await act.finalize(db_session, act_id=draft.id, user_id=outsider.id)
    with pytest.raises(AccessDeniedError):
        await ca.accept(db_session, work_entry_id=entry.id, volume=Decimal('1'), user_id=outsider.id, idempotency_key=uuid.uuid4())
    with pytest.raises(AccessDeniedError):
        await act.prepare_export(db_session, act_id=draft.id, user_id=outsider.id)
