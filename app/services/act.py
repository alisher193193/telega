from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ActStatus, WorkEntryStatus
from app.core.exceptions import ValidationError
from app.db.repositories import act as act_repo
from app.db.repositories import customer_acceptance as ca_repo
from app.db.repositories.work_entries import lock_work_entry
from app.models.acts import Act, ActLine
from app.models.directories import Unit, WorkType, Contract, Project
from app.services import audit
from app.services.access import require_permission
from app.services.work_status import synchronize
from app.core.numbers import volume, money, line_amount
from app.core.operations import operation
from app.core.exceptions import ConflictError
from app.db.repositories.idempotency import lock_key
from app.db.repositories import available_work


@operation
async def create_draft(
    session: AsyncSession,
    *,
    project_id: uuid.UUID,
    contract_id: uuid.UUID | None,
    act_number: str,
    act_date: date,
    created_by: uuid.UUID | None,
    comment: str | None = None,
) -> Act:
    await require_permission(session, created_by, "acts.manage")
    project = await session.get(Project, project_id)
    if project is None or project.is_archived:
        raise ValidationError("Объект не найден или архивирован")
    if contract_id is not None:
        contract = await session.get(Contract, contract_id)
        if contract is None or contract.project_id != project_id:
            raise ValidationError("Договор не принадлежит объекту")
    if len(act_number.strip()) > 100:
        raise ValidationError("Номер акта слишком длинный")
    if not act_number.strip():
        raise ValidationError("Номер акта не может быть пустым")

    act = Act(
        project_id=project_id,
        contract_id=contract_id,
        act_number=act_number.strip(),
        act_date=act_date,
        status=ActStatus.DRAFT.value,
        comment=comment,
        created_by=created_by,
    )
    session.add(act)
    await session.flush()

    await audit.record(
        session,
        user_id=created_by,
        action="act.create_draft",
        entity_type="act",
        entity_id=str(act.id),
        new_values={"project_id": project_id, "act_number": act_number},
    )
    await session.flush()
    return act


async def available_volume_for_act(
    session: AsyncSession,
    work_entry_id: uuid.UUID,
    *,
    exclude_act_id: uuid.UUID | None = None,
) -> Decimal:
    customer_accepted = await ca_repo.total_accepted_volume(session, work_entry_id)
    already_in_acts = await act_repo.volume_in_active_acts(
        session, work_entry_id, exclude_act_id=exclude_act_id
    )
    return customer_accepted - already_in_acts


async def _recalculate_total(session: AsyncSession, act: Act) -> None:
    lines = await act_repo.list_lines(session, act.id)
    act.total_amount = money(sum((line.amount for line in lines), Decimal("0")))


def _build_location_snapshot(work_entry) -> str | None:
    parts = [
        work_entry.floor and f"этаж {work_entry.floor}",
        work_entry.room and f"пом. {work_entry.room}",
        work_entry.item_number and f"№ {work_entry.item_number}",
        work_entry.axes and f"оси {work_entry.axes}",
        work_entry.location_note,
    ]
    text = ", ".join(part for part in parts if part)
    return text or None


@operation
async def add_line(
    session: AsyncSession,
    *,
    act_id: uuid.UUID,
    work_entry_id: uuid.UUID,
    quantity: Decimal,
    idempotency_key: uuid.UUID,
    user_id: uuid.UUID | None,
    comment: str | None = None,
) -> ActLine:
    """Add a line to a draft act, protected against concurrent double-inclusion."""
    await require_permission(session, user_id, "acts.manage")
    quantity = volume(quantity)
    await lock_key(session, "act_line", idempotency_key)
    existing = await session.scalar(select(ActLine).where(ActLine.idempotency_key == idempotency_key))
    if existing is not None:
        if existing.act_id != act_id or existing.work_entry_id != work_entry_id or existing.accepted_volume != quantity:
            raise ConflictError("Ключ уже использован для другой строки")
        return existing
    if quantity <= 0:
        raise ValidationError("Объём строки акта должен быть больше нуля")

    act = await act_repo.get_for_update(session, act_id)

    if act.status != ActStatus.DRAFT.value:
        raise ValidationError("Редактировать можно только черновик акта")

    work_entry = await lock_work_entry(session, work_entry_id)

    if work_entry.status == WorkEntryStatus.CANCELLED.value:
        raise ValidationError("Работа отменена")
    if work_entry.project_id != act.project_id or work_entry.contract_id != act.contract_id:
        raise ValidationError("Работа должна принадлежать объекту и договору акта")
    available = await available_volume_for_act(session, work_entry_id)

    if quantity > available:
        raise ValidationError(
            f"Нельзя включить {quantity}: доступно к включению в акты только {available}"
        )

    unit_price = money(work_entry.customer_rate_snapshot or Decimal("0"))
    if unit_price < 0:
        raise ValidationError("Цена не может быть отрицательной")
    amount = line_amount(quantity, unit_price)

    work_type = await session.get(WorkType, work_entry.work_type_id)
    unit = await session.get(Unit, work_entry.unit_id) if work_entry.unit_id else None

    line = ActLine(
        idempotency_key=idempotency_key,
        act_id=act.id,
        work_entry_id=work_entry_id,
        accepted_volume=quantity,
        unit_price=unit_price,
        amount=amount,
        work_type_name=work_type.name if work_type else "",
        unit_name=unit.name if unit else "",
        location_snapshot=_build_location_snapshot(work_entry),
        comment=comment,
    )
    session.add(line)
    await session.flush()

    await _recalculate_total(session, act)

    await synchronize(session, work_entry, user_id, "Включение в акт")

    await audit.record(
        session,
        user_id=user_id,
        action="act.add_line",
        entity_type="act_line",
        entity_id=str(line.id),
        new_values={
            "act_id": act.id,
            "work_entry_id": work_entry_id,
            "quantity": quantity,
            "unit_price": unit_price,
            "amount": amount,
        },
    )

    await session.flush()
    return line


@operation
async def remove_line(
    session: AsyncSession,
    *,
    act_id: uuid.UUID,
    line_id: uuid.UUID,
    reason: str,
    user_id: uuid.UUID | None,
) -> None:
    await require_permission(session, user_id, "acts.manage")
    if not reason or not reason.strip():
        raise ValidationError("Укажите причину отмены строки")
    act = await act_repo.get_for_update(session, act_id)

    if act.status != ActStatus.DRAFT.value:
        raise ValidationError("Отменять строки можно только в черновике акта")

    line = await act_repo.get_line(session, line_id)

    if line is None or line.act_id != act_id:
        raise ValidationError("Строка акта не найдена")

    if line.cancelled_at is not None:
        return
    work = await lock_work_entry(session, line.work_entry_id)
    old_values = {
        "work_entry_id": line.work_entry_id,
        "accepted_volume": line.accepted_volume,
        "amount": line.amount,
    }

    line.cancelled_at = datetime.now(timezone.utc)
    line.cancelled_by = user_id
    line.cancellation_reason = reason.strip()
    await session.flush()

    await _recalculate_total(session, act)
    await synchronize(session, work, user_id, "Отмена строки акта")

    await audit.record(
        session,
        user_id=user_id,
        action="act.cancel_line",
        entity_type="act_line",
        entity_id=str(line_id),
        old_values=old_values,
        new_values={"cancelled_at": line.cancelled_at, "reason": reason.strip()},
    )

    await session.flush()


@operation
async def finalize(session: AsyncSession, *, act_id: uuid.UUID, user_id: uuid.UUID | None) -> Act:
    await require_permission(session, user_id, "acts.manage")
    act = await act_repo.get_for_update(session, act_id)

    if act.status != ActStatus.DRAFT.value:
        raise ValidationError("Завершить можно только черновик акта")

    lines = await act_repo.list_lines(session, act_id)
    if not lines:
        raise ValidationError("Нельзя завершить акт без строк")

    act.status = ActStatus.FINALIZED.value

    await audit.record(
        session,
        user_id=user_id,
        action="act.finalize",
        entity_type="act",
        entity_id=str(act.id),
        new_values={"status": act.status, "total_amount": act.total_amount},
    )

    await session.flush()
    return act


@operation
async def cancel(
    session: AsyncSession,
    *,
    act_id: uuid.UUID,
    reason: str,
    user_id: uuid.UUID | None,
) -> Act:
    await require_permission(session, user_id, "acts.manage")
    if not reason or not reason.strip():
        raise ValidationError("Для отмены акта необходимо указать причину")

    act = await act_repo.get_for_update(session, act_id)

    if act.status == ActStatus.CANCELLED.value:
        raise ValidationError("Акт уже отменён")
    if act.status not in {ActStatus.DRAFT.value, ActStatus.FINALIZED.value}:
        raise ValidationError("Акт находится в недопустимом для отмены статусе")

    lines = await act_repo.list_lines(session, act.id)
    works = [await lock_work_entry(session, wid) for wid in sorted({line.work_entry_id for line in lines}, key=str)]
    old_status = act.status
    act.status = ActStatus.CANCELLED.value
    act.cancelled_at = datetime.now(timezone.utc)
    act.cancellation_reason = reason.strip()
    await session.flush()
    for work in works:
        await synchronize(session, work, user_id, "Отмена акта")

    await audit.record(
        session,
        user_id=user_id,
        action="act.cancel",
        entity_type="act",
        entity_id=str(act.id),
        old_values={"status": old_status},
        new_values={"status": act.status, "reason": act.cancellation_reason},
    )

    await session.flush()
    return act


async def list_available_work(session, act_id, *, user_id, limit=10, offset=0):
    await require_permission(session, user_id, "acts.manage")
    act = await act_repo.get_or_raise(session, act_id)
    if act.status != ActStatus.DRAFT.value:
        raise ValidationError("Редактировать можно только черновик")
    return await available_work.for_act(session, act, limit=limit, offset=offset)


@operation
async def prepare_export(session, *, act_id, user_id):
    await require_permission(session, user_id, "acts.view")
    # Serialize snapshot against edits/finalization/cancellation.
    act = await act_repo.get_for_update(session, act_id)
    lines = await act_repo.list_lines(session, act_id)
    project = await session.get(Project, act.project_id)
    contract = await session.get(Contract, act.contract_id) if act.contract_id else None
    await audit.record(session, user_id=user_id, action="act.export", entity_type="act",
                       entity_id=str(act_id), new_values={"format": "xlsx", "lines": len(lines)})
    return act, lines, project, contract
