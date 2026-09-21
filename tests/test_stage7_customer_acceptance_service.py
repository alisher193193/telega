from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.exceptions import ValidationError
from app.services import customer_acceptance as ca_service


async def test_partial_customer_acceptance(db_session, work_entry_factory, internal_acceptance_factory):
    entry, _project, _contract = await work_entry_factory()
    await internal_acceptance_factory(entry.id, Decimal("60"))

    acceptance = await ca_service.accept(
        db_session,
        work_entry_id=entry.id,
        volume=Decimal("20"),
        user_id=None,
        comment="Первая частичная приёмка",
    )

    assert acceptance.accepted_volume == Decimal("20")

    summary = await ca_service.get_summary(db_session, entry.id)
    assert summary.internal_accepted == Decimal("60")
    assert summary.customer_accepted == Decimal("20")
    assert summary.remaining_for_customer == Decimal("40")


async def test_cannot_exceed_internal_accepted_volume(
    db_session, work_entry_factory, internal_acceptance_factory
):
    entry, _project, _contract = await work_entry_factory()
    await internal_acceptance_factory(entry.id, Decimal("30"))

    with pytest.raises(ValidationError):
        await ca_service.accept(
            db_session,
            work_entry_id=entry.id,
            volume=Decimal("31"),
            user_id=None,
        )


async def test_multiple_acceptance_operations_accumulate(
    db_session, work_entry_factory, internal_acceptance_factory
):
    entry, _project, _contract = await work_entry_factory()
    await internal_acceptance_factory(entry.id, Decimal("50"))

    await ca_service.accept(db_session, work_entry_id=entry.id, volume=Decimal("10"), user_id=None)
    await ca_service.accept(db_session, work_entry_id=entry.id, volume=Decimal("15"), user_id=None)

    summary = await ca_service.get_summary(db_session, entry.id)
    assert summary.customer_accepted == Decimal("25")
    assert summary.remaining_for_customer == Decimal("25")

    # Exactly exhausting the remaining volume must succeed once...
    await ca_service.accept(db_session, work_entry_id=entry.id, volume=Decimal("25"), user_id=None)

    # ...and any further acceptance of the same (already consumed) volume must fail,
    # which is how duplicate/double-submitted operations are protected against.
    with pytest.raises(ValidationError):
        await ca_service.accept(db_session, work_entry_id=entry.id, volume=Decimal("25"), user_id=None)


async def test_correction_reduces_accepted_volume_without_deleting_rows(
    db_session, work_entry_factory, internal_acceptance_factory
):
    entry, _project, _contract = await work_entry_factory()
    await internal_acceptance_factory(entry.id, Decimal("50"))

    accepted = await ca_service.accept(
        db_session, work_entry_id=entry.id, volume=Decimal("30"), user_id=None
    )
    correction = await ca_service.correct(
        db_session,
        work_entry_id=entry.id,
        delta_volume=Decimal("-10"),
        user_id=None,
        reason="Ошибка в объёме",
    )

    assert accepted.id is not None
    assert correction.accepted_volume == Decimal("-10")

    summary = await ca_service.get_summary(db_session, entry.id)
    assert summary.customer_accepted == Decimal("20")


async def test_cancelled_work_entry_cannot_be_accepted(db_session, work_entry_factory):
    entry, _project, _contract = await work_entry_factory(status="cancelled")

    with pytest.raises(ValidationError):
        await ca_service.accept(db_session, work_entry_id=entry.id, volume=Decimal("1"), user_id=None)
