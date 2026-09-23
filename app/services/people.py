"""People business operations; caller owns the outer transaction.

All people writes lock the same transaction advisory key before row locks.
This keeps archive/termination/membership races in one consistent lock order.
"""
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.core.exceptions import AccessDeniedError, ConflictError, ValidationError
from app.core.operations import operation
from app.db.repositories import people as repo
from app.db.repositories.idempotency import lock_key
from app.models.people import CrewMember, Specialty
from app.models.directory_mutations import DirectoryMutation
from app.schemas.people import PERMISSIONS, fields, validate, normalized_name, wire
from app.services.access import require_permission
from app.services.catalog import digest
from app.services import audit

TZ = ZoneInfo("Asia/Almaty")


async def require(session, kind, user_id, action="view"):
    fields(kind)
    await require_permission(session, user_id, f"{PERMISSIONS[kind]}.{action}")


async def capabilities(session, user_id):
    result = set()
    for kind in PERMISSIONS:
        for action in ("view", "manage"):
            try:
                await require(session, kind, user_id, action)
                result.add(f"{kind}.{action}")
            except AccessDeniedError:
                pass
    return result


async def get(session, kind, entity_id, *, user_id):
    await require(session, kind, user_id)
    return await repo.get(session, kind, entity_id)


async def list_page(session, kind, *, user_id, **filters):
    await require(session, kind, user_id)
    return await repo.list_page(session, kind, **filters)


async def choices(session, relation, *, user_id, purpose, **filters):
    # Selecting references is part of an authorized mutation, not arbitrary browsing.
    await require(session, "crew" if purpose == "member" else "worker", user_id,
                  "view" if purpose == "filter" else "manage")
    allowed = {"member": {"worker"}, "filter": {"project"}, "form": {"specialty", "project"}}
    if relation not in allowed.get(purpose, set()):
        raise ValidationError("Недопустимый справочник выбора")
    filters["status"] = "active"
    return await repo.list_page(session, relation, **filters)


def snapshot(kind, row):
    result = {field.name: wire(getattr(row, field.name)) for field in fields(kind)}
    for key in ("status", "is_archived", "is_active", "terminated_at", "termination_date", "specialty"):
        if hasattr(row, key):
            value = getattr(row, key)
            result[key] = value.isoformat() if isinstance(value, datetime) else wire(value)
    return result


def version(kind, row):
    return digest(snapshot(kind, row))


def archived(kind, row):
    return (row.status == "terminated" or row.is_archived) if kind == "worker" else (
        not row.is_active if kind == "specialty" else row.status != "active")


async def detail(session, kind, entity_id, *, user_id):
    row = await get(session, kind, entity_id, user_id=user_id)
    result = snapshot(kind, row)
    result.update(id=str(row.id), version=version(kind, row), archived=archived(kind, row),
                  created_at=row.created_at.isoformat())
    if kind == "worker":
        result["specialty_label"] = ((await repo.get(session, "specialty", row.specialty_id)).name
                                    if row.specialty_id else row.specialty or "Не указана")
        result["project_label"] = ((await repo.get(session, "project", row.current_project_id)).name
                                  if row.current_project_id else "Без объекта")
        member = await repo.current_membership(session, row.id)
        result["crew_label"] = (await repo.get(session, "crew", member.crew_id)).name if member else "Без бригады"
    return result


async def members(session, crew_id, *, user_id, **filters):
    await require(session, "crew", user_id)
    await repo.get(session, "crew", crew_id)
    return await repo.members(session, crew_id, **filters)


async def _receipt(session, key, payload):
    if not isinstance(key, uuid.UUID):
        raise ValidationError("Некорректный ключ сохранения")
    await lock_key(session, "people-writes", uuid.UUID(int=0))
    row = await session.get(DirectoryMutation, key)
    if row:
        if row.payload_hash != payload:
            raise ConflictError("Ключ сохранения уже использован для другой операции")
        return await repo.get(session, row.kind, row.entity_id)
    return None


async def _record(session, kind, row, user_id, key, payload, action, old, extra=None):
    new = snapshot(kind, row) if kind != "member" else member_snapshot(row)
    if extra:
        new.update(extra)
    await audit.record(session, user_id=user_id, action=f"people.{action}", entity_type=kind,
                       entity_id=str(row.id), old_values=old, new_values=new)
    session.add(DirectoryMutation(idempotency_key=key, user_id=user_id, kind=kind,
                                 entity_id=row.id, payload_hash=payload))
    await session.flush()


def member_snapshot(row):
    return {key: wire(getattr(row, key)) for key in
            ("worker_id", "crew_id", "joined_at", "left_at", "joined_on", "left_on")}


def check_version(kind, row, expected):
    if not expected or version(kind, row) != expected:
        raise ConflictError("Запись изменена. Откройте карточку заново")


@operation
async def save(session, kind, values, *, user_id, idempotency_key, entity_id=None, expected_version=None):
    await require(session, kind, user_id, "manage")
    values = validate(kind, values)
    payload = digest(dict(action="save", kind=kind, values=values, entity_id=entity_id,
                          expected=expected_version, user=user_id))
    replay = await _receipt(session, idempotency_key, payload)
    if replay:
        return replay
    row = await repo.get(session, kind, entity_id, lock=True) if entity_id else None
    old = snapshot(kind, row) if row else None
    if row:
        check_version(kind, row, expected_version)
        if archived(kind, row):
            raise ValidationError("Сначала восстановите запись")
    if kind == "worker":
        specialty = await repo.get(session, "specialty", values["specialty_id"], lock=True)
        if not specialty.is_active and (row is None or row.specialty_id != specialty.id):
            raise ValidationError("Архивную специальность нельзя выбирать")
        project_id = values["current_project_id"]
        if project_id:
            project = await repo.get(session, "project", project_id, lock=True)
            if (project.is_archived or project.status == "archived") and (row is None or row.current_project_id != project_id):
                raise ValidationError("Архивный объект нельзя выбирать")
    if kind == "specialty":
        normalized = normalized_name(values["name"])
        duplicate = await session.scalar(select(Specialty.id).where(Specialty.normalized_name == normalized))
        if duplicate and duplicate != entity_id:
            raise ValidationError("Такая специальность уже существует, включая архив")
        values["normalized_name"] = normalized
    try:
        async with session.begin_nested():
            if row is None:
                row = repo.MODELS[kind](**values)
                session.add(row)
                if kind == "worker":
                    row.created_by = user_id
            else:
                for key, value in values.items():
                    setattr(row, key, value)
            if kind == "worker":
                row.updated_by = user_id
                row.specialty = specialty.name  # Preserve legacy text; linked name is authoritative.
            await session.flush()
            await _record(session, kind, row, user_id, idempotency_key, payload,
                          "update" if entity_id else "create", old)
    except IntegrityError:
        raise ValidationError("Данные конфликтуют с существующей записью") from None
    return row


async def _close_member(session, member, user_id, now):
    old = member_snapshot(member)
    # Do not invent an exact legacy joining time.
    member.left_at = now.astimezone(TZ).date()
    if member.joined_on:
        member.left_on = now
    await audit.record(session, user_id=user_id, action="people.membership.end", entity_type="member",
                       entity_id=str(member.id), old_values=old, new_values=member_snapshot(member))


@operation
async def change_status(session, kind, entity_id, *, inactive, reason=None, user_id, idempotency_key, expected_version):
    await require(session, kind, user_id, "manage")
    if type(inactive) is not bool or (reason is not None and (not isinstance(reason, str) or len(reason) > 1000)):
        raise ValidationError("Некорректное действие или слишком длинная причина")
    payload = digest(dict(action="status", kind=kind, entity=entity_id, inactive=inactive,
                          reason=reason, user=user_id, expected=expected_version))
    replay = await _receipt(session, idempotency_key, payload)
    if replay:
        return replay
    row = await repo.get(session, kind, entity_id, lock=True)
    check_version(kind, row, expected_version)
    old = snapshot(kind, row)
    now = datetime.now(timezone.utc)
    if kind == "worker":
        row.status = "terminated" if inactive else "working"
        row.is_archived = False
        row.terminated_at = now if inactive else None
        row.termination_date = now.astimezone(TZ).date() if inactive else None
        row.updated_by = user_id
        member = await repo.current_membership(session, row.id, lock=True)
        if inactive and member:
            await _close_member(session, member, user_id, now)
    elif kind == "specialty":
        row.is_active = not inactive
    else:
        row.status = "archived" if inactive else "active"
        if inactive:
            for member in await repo.open_members(session, row.id):
                await _close_member(session, member, user_id, now)
    await _record(session, kind, row, user_id, idempotency_key, payload,
                  ("terminate" if kind == "worker" else "archive") if inactive else "restore",
                  old, {"reason": reason})
    return row


def ensure_joinable(worker, crew, existing):
    if worker.status != "working" or worker.is_archived:
        raise ValidationError("Добавить можно только работающего человека")
    if crew.status != "active":
        raise ValidationError("Бригада находится в архиве")
    if existing and existing.crew_id != crew.id:
        raise ConflictError("Работник уже состоит в другой бригаде")


@operation
async def membership(session, crew_id, worker_id, *, joining, user_id, idempotency_key, membership_id=None):
    await require(session, "crew", user_id, "manage")
    if type(joining) is not bool:
        raise ValidationError("Некорректное действие")
    payload = digest(dict(action="membership", crew=crew_id, worker=worker_id, joining=joining,
                          membership=membership_id, user=user_id))
    replay = await _receipt(session, idempotency_key, payload)
    if replay:
        return replay
    crew = await repo.get(session, "crew", crew_id, lock=True)
    worker = await repo.get(session, "worker", worker_id, lock=True)
    current = await repo.current_membership(session, worker_id, lock=True)
    now = datetime.now(timezone.utc)
    if joining:
        ensure_joinable(worker, crew, current)
        if current:
            row = current
        else:
            row = CrewMember(crew_id=crew_id, worker_id=worker_id, joined_on=now,
                             joined_at=now.astimezone(TZ).date())
            session.add(row)
            await session.flush()
        old = None
    else:
        row = await repo.get(session, "member", membership_id, lock=True)
        if row.crew_id != crew_id or row.worker_id != worker_id:
            raise ValidationError("Участие не относится к выбранной бригаде и работнику")
        old = member_snapshot(row)
        if row.left_at is None:
            await _close_member(session, row, user_id, now)
    await _record(session, "member", row, user_id, idempotency_key, payload,
                  "membership.join" if joining else "membership.leave", old)
    return row


async def choice(session, relation, entity_id, *, user_id, purpose, existing_id=None):
    await require(session, "crew" if purpose == "member" else "worker", user_id,
                  "view" if purpose == "filter" else "manage")
    if relation not in {"member": {"worker"}, "filter": {"project"}, "form": {"specialty", "project"}}.get(purpose, set()):
        raise ValidationError("Недопустимый выбор")
    row = await repo.get(session, relation, entity_id)
    inactive = (row.is_archived or row.status != "working") if relation == "worker" else (
        not row.is_active if relation == "specialty" else row.is_archived or row.status == "archived")
    if inactive and row.id != existing_id:
        raise ValidationError("Нельзя выбирать архивную или неработающую запись")
    return row
