from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.services import act as act_service
from app.services import customer_acceptance as ca_service


async def _prepare_accepted_entry(
    work_entry_factory,
    internal_acceptance_factory,
    accepted_volume: Decimal,
    db_session,
):
    entry, project, contract = await work_entry_factory()
    await internal_acceptance_factory(entry.id, accepted_volume)
    await ca_service.accept(
        db_session, work_entry_id=entry.id, volume=accepted_volume, user_id=None
    )
    return entry, project, contract


async def test_available_volume_for_act_matches_customer_accepted(
    db_session, work_entry_factory, internal_acceptance_factory
):
    entry, _project, _contract = await _prepare_accepted_entry(
        work_entry_factory, internal_acceptance_factory, Decimal("40"), db_session
    )

    available = await act_service.available_volume_for_act(db_session, entry.id)
    assert available == Decimal("40")


async def test_partial_inclusion_into_two_different_acts(
    db_session, work_entry_factory, internal_acceptance_factory
):
    entry, project, contract = await _prepare_accepted_entry(
        work_entry_factory, internal_acceptance_factory, Decimal("40"), db_session
    )

    act1 = await act_service.create_draft(
        db_session,
        project_id=project.id,
        contract_id=contract.id,
        act_number=f"A-{entry.id.hex[:6]}-1",
        act_date=dt.date.today(),
        created_by=None,
    )
    act2 = await act_service.create_draft(
        db_session,
        project_id=project.id,
        contract_id=contract.id,
        act_number=f"A-{entry.id.hex[:6]}-2",
        act_date=dt.date.today(),
        created_by=None,
    )

    line1 = await act_service.add_line(
        db_session, act_id=act1.id, work_entry_id=entry.id, quantity=Decimal("25"), user_id=None
    )
    line2 = await act_service.add_line(
        db_session, act_id=act2.id, work_entry_id=entry.id, quantity=Decimal("15"), user_id=None
    )

    assert line1.amount == Decimal("12500.00")
    assert line2.amount == Decimal("7500.00")

    remaining = await act_service.available_volume_for_act(db_session, entry.id)
    assert remaining == Decimal("0")


async def test_cannot_double_include_beyond_available_volume(
    db_session, work_entry_factory, internal_acceptance_factory
):
    entry, project, contract = await _prepare_accepted_entry(
        work_entry_factory, internal_acceptance_factory, Decimal("20"), db_session
    )

    act = await act_service.create_draft(
        db_session,
        project_id=project.id,
        contract_id=contract.id,
        act_number=f"A-{entry.id.hex[:6]}",
        act_date=dt.date.today(),
        created_by=None,
    )

    await act_service.add_line(
        db_session, act_id=act.id, work_entry_id=entry.id, quantity=Decimal("20"), user_id=None
    )

    with pytest.raises(ValidationError):
        await act_service.add_line(
            db_session, act_id=act.id, work_entry_id=entry.id, quantity=Decimal("1"), user_id=None
        )


async def test_act_total_amount_is_sum_of_lines(
    db_session, work_entry_factory, internal_acceptance_factory
):
    entry, project, contract = await _prepare_accepted_entry(
        work_entry_factory, internal_acceptance_factory, Decimal("30"), db_session
    )

    act = await act_service.create_draft(
        db_session,
        project_id=project.id,
        contract_id=contract.id,
        act_number=f"A-{entry.id.hex[:6]}",
        act_date=dt.date.today(),
        created_by=None,
    )

    await act_service.add_line(
        db_session, act_id=act.id, work_entry_id=entry.id, quantity=Decimal("10"), user_id=None
    )
    await act_service.add_line(
        db_session, act_id=act.id, work_entry_id=entry.id, quantity=Decimal("20"), user_id=None
    )

    assert act.total_amount == Decimal("15000.00")


async def test_cancelled_act_releases_volume_for_new_act(
    db_session, work_entry_factory, internal_acceptance_factory
):
    entry, project, contract = await _prepare_accepted_entry(
        work_entry_factory, internal_acceptance_factory, Decimal("10"), db_session
    )

    act = await act_service.create_draft(
        db_session,
        project_id=project.id,
        contract_id=contract.id,
        act_number=f"A-{entry.id.hex[:6]}",
        act_date=dt.date.today(),
        created_by=None,
    )
    await act_service.add_line(
        db_session, act_id=act.id, work_entry_id=entry.id, quantity=Decimal("10"), user_id=None
    )

    assert await act_service.available_volume_for_act(db_session, entry.id) == Decimal("0")

    await act_service.cancel(db_session, act_id=act.id, reason="Ошибка в акте", user_id=None)

    assert await act_service.available_volume_for_act(db_session, entry.id) == Decimal("10")


async def test_cannot_edit_finalized_act(
    db_session, work_entry_factory, internal_acceptance_factory
):
    entry, project, contract = await _prepare_accepted_entry(
        work_entry_factory, internal_acceptance_factory, Decimal("10"), db_session
    )

    act = await act_service.create_draft(
        db_session,
        project_id=project.id,
        contract_id=contract.id,
        act_number=f"A-{entry.id.hex[:6]}",
        act_date=dt.date.today(),
        created_by=None,
    )
    await act_service.add_line(
        db_session, act_id=act.id, work_entry_id=entry.id, quantity=Decimal("10"), user_id=None
    )
    await act_service.finalize(db_session, act_id=act.id, user_id=None)

    with pytest.raises(ValidationError):
        await act_service.add_line(
            db_session, act_id=act.id, work_entry_id=entry.id, quantity=Decimal("1"), user_id=None
        )


async def test_cancel_requires_reason(db_session, work_entry_factory, internal_acceptance_factory):
    entry, project, contract = await _prepare_accepted_entry(
        work_entry_factory, internal_acceptance_factory, Decimal("5"), db_session
    )
    act = await act_service.create_draft(
        db_session,
        project_id=project.id,
        contract_id=contract.id,
        act_number=f"A-{entry.id.hex[:6]}",
        act_date=dt.date.today(),
        created_by=None,
    )

    with pytest.raises(ValidationError):
        await act_service.cancel(db_session, act_id=act.id, reason="  ", user_id=None)
