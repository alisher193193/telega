from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AcceptanceKind, WorkEntryStatus
from app.core.exceptions import ValidationError
from app.db.repositories import customer_acceptance as ca_repo
from app.db.repositories import internal_acceptance as ia_repo
from app.db.repositories.work_entries import get_work_entry, lock_work_entry
from app.models.acts import CustomerAcceptance
from app.models.work_entries import WorkEntry, WorkStatusHistory
from app.services import audit

# Statuses from which a customer acceptance operation is still allowed.
_ACCEPTABLE_STATUSES = {
    WorkEntryStatus.DONE.value,
    WorkEntryStatus.ACCEPTED_INTERNAL.value,
    WorkEntryStatus.REQUIRES_FIX.value,
    WorkEntryStatus.SUBMITTED_CUSTOMER.value,
    WorkEntryStatus.ACCEPTED_CUSTOMER.value,
}


class AcceptanceSummary:
    def __init__(
        self,
        claimed_volume: Decimal,
        internal_accepted: Decimal,
        customer_accepted: Decimal,
    ) -> None:
        self.claimed_volume = claimed_volume
        self.internal_accepted = internal_accepted
        self.customer_accepted = customer_accepted

    @property
    def remaining_for_customer(self) -> Decimal:
        return self.internal_accepted - self.customer_accepted


async def get_summary(session: AsyncSession, work_entry_id: uuid.UUID) -> AcceptanceSummary:
    """Read-only snapshot used to render the acceptance card in Telegram."""
    work_entry = await get_work_entry(session, work_entry_id)
    internal_accepted = await ia_repo.total_internal_accepted_volume(session, work_entry_id)
    customer_accepted = await ca_repo.total_accepted_volume(session, work_entry_id)
    return AcceptanceSummary(
        claimed_volume=work_entry.claimed_volume,
        internal_accepted=internal_accepted,
        customer_accepted=customer_accepted,
    )


async def list_available_for_project(
    session: AsyncSession,
    project_id: uuid.UUID,
    *,
    limit: int = 30,
) -> list[tuple[WorkEntry, AcceptanceSummary]]:
    """Work entries of a project that still have volume available for customer acceptance."""
    stmt = (
        select(WorkEntry)
        .where(
            WorkEntry.project_id == project_id,
            WorkEntry.status != WorkEntryStatus.CANCELLED.value,
        )
        .order_by(WorkEntry.entry_date.desc())
        .limit(limit)
    )
    entries = (await session.scalars(stmt)).all()

    result: list[tuple[WorkEntry, AcceptanceSummary]] = []
    for entry in entries:
        internal_accepted = await ia_repo.total_internal_accepted_volume(session, entry.id)
        customer_accepted = await ca_repo.total_accepted_volume(session, entry.id)
        summary = AcceptanceSummary(
            claimed_volume=entry.claimed_volume,
            internal_accepted=internal_accepted,
            customer_accepted=customer_accepted,
        )
        if summary.remaining_for_customer > 0:
            result.append((entry, summary))

    return result


async def accept(
    session: AsyncSession,
    *,
    work_entry_id: uuid.UUID,
    volume: Decimal,
    user_id: uuid.UUID | None,
    comment: str | None = None,
) -> CustomerAcceptance:
    """Register a (partial) customer acceptance for a work entry.

    Locks the work entry row FOR UPDATE so concurrent acceptance attempts are
    serialized and the accumulated volume check stays consistent.
    """
    if volume <= 0:
        raise ValidationError("Объём приёмки должен быть больше нуля")

    work_entry = await lock_work_entry(session, work_entry_id)

    if work_entry.status == WorkEntryStatus.CANCELLED.value:
        raise ValidationError("Работа отменена, приёмка невозможна")

    if work_entry.status not in _ACCEPTABLE_STATUSES:
        raise ValidationError("Работа находится в статусе, недоступном для приёмки заказчиком")

    internal_accepted = await ia_repo.total_internal_accepted_volume(session, work_entry_id)
    customer_accepted = await ca_repo.total_accepted_volume(session, work_entry_id)
    remaining = internal_accepted - customer_accepted

    if volume > remaining:
        raise ValidationError(
            f"Нельзя принять {volume}: доступно только {remaining} "
            f"(принято нами {internal_accepted}, уже принято заказчиком {customer_accepted})"
        )

    acceptance = ca_repo.create(
        work_entry_id=work_entry_id,
        project_id=work_entry.project_id,
        contract_id=work_entry.contract_id,
        accepted_volume=volume,
        kind=AcceptanceKind.ACCEPT.value,
        accepted_by_user_id=user_id,
        comment=comment,
    )
    session.add(acceptance)
    await session.flush()

    old_status = work_entry.status
    if old_status != WorkEntryStatus.ACCEPTED_CUSTOMER.value:
        work_entry.status = WorkEntryStatus.ACCEPTED_CUSTOMER.value
        session.add(
            WorkStatusHistory(
                work_entry_id=work_entry_id,
                old_status=old_status,
                new_status=work_entry.status,
                changed_by=user_id,
                comment="Приёмка заказчиком",
            )
        )

    await audit.record(
        session,
        user_id=user_id,
        action="customer_acceptance.accept",
        entity_type="customer_acceptance",
        entity_id=str(acceptance.id),
        new_values={
            "work_entry_id": work_entry_id,
            "accepted_volume": volume,
            "comment": comment,
        },
    )

    await session.flush()
    return acceptance


async def correct(
    session: AsyncSession,
    *,
    work_entry_id: uuid.UUID,
    delta_volume: Decimal,
    user_id: uuid.UUID | None,
    reason: str,
) -> CustomerAcceptance:
    """Record a negative correction without deleting previous acceptance rows."""
    if delta_volume >= 0:
        raise ValidationError("Корректировка должна уменьшать принятый объём (значение < 0)")

    if not reason:
        raise ValidationError("Для корректировки необходимо указать причину")

    work_entry = await lock_work_entry(session, work_entry_id)
    customer_accepted = await ca_repo.total_accepted_volume(session, work_entry_id)

    if customer_accepted + delta_volume < 0:
        raise ValidationError("Корректировка превышает уже принятый заказчиком объём")

    correction = ca_repo.create(
        work_entry_id=work_entry_id,
        project_id=work_entry.project_id,
        contract_id=work_entry.contract_id,
        accepted_volume=delta_volume,
        kind=AcceptanceKind.CORRECTION.value,
        accepted_by_user_id=user_id,
        comment=reason,
    )
    session.add(correction)
    await session.flush()

    await audit.record(
        session,
        user_id=user_id,
        action="customer_acceptance.correct",
        entity_type="customer_acceptance",
        entity_id=str(correction.id),
        new_values={
            "work_entry_id": work_entry_id,
            "delta_volume": delta_volume,
            "reason": reason,
        },
    )

    await session.flush()
    return correction

