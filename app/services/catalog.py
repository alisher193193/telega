"""Directory business operations. Call mutations within session.begin()."""
import hashlib
import json
import uuid
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from app.core.exceptions import AccessDeniedError, ConflictError, ValidationError
from app.core.operations import operation
from app.db.repositories import catalog as repo
from app.db.repositories.idempotency import lock_key
from app.models.directory_mutations import DirectoryMutation
from app.schemas.directories import fields, validate, wire
from app.services import audit
from app.services.access import require_permission


async def require_change(session, user_id):
    for code in ("projects.manage", "directories.manage"):
        try:
            await require_permission(session, user_id, code)
            return
        except AccessDeniedError:
            pass
    raise AccessDeniedError("Для изменения нужны projects.manage или directories.manage")


def snapshot(kind, row):
    values = {field.name: wire(getattr(row, field.name)) for field in fields(kind)}
    values["archived"] = bool(repo.is_archived(kind, row))
    return values


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=wire).encode()).hexdigest()


def version(kind, row):
    return digest(snapshot(kind, row))


async def list_page(session, kind, *, user_id, **filters):
    await require_permission(session, user_id, "projects.view")
    return await repo.list_page(session, kind, **filters)


async def get(session, kind, entity_id, *, user_id):
    await require_permission(session, user_id, "projects.view")
    return await repo.get(session, kind, entity_id)


async def _references(session, kind, values):
    linked = {}
    for field in fields(kind):
        value = values.get(field.name)
        if field.relation and value is not None:
            parent = await repo.get(session, field.relation, value)
            if repo.is_archived(field.relation, parent):
                raise ValidationError(f"{field.label}: запись в архиве")
            linked[field.name] = parent
    contract = linked.get("contract_id")
    if contract and contract.project_id != values.get("project_id"):
        raise ValidationError("Договор должен принадлежать выбранному объекту")
    if kind == "rate":
        work_type = linked["work_type_id"]
        if work_type.work_section_id:
            section = await repo.get(session, "section", work_type.work_section_id)
            if repo.is_archived("section", section):
                raise ValidationError("Раздел вида работ находится в архиве")
            if values.get("project_id") and section.project_id and section.project_id != values["project_id"]:
                raise ValidationError("Вид работы относится к другому объекту")
            if values.get("contract_id") and section.contract_id and section.contract_id != values["contract_id"]:
                raise ValidationError("Вид работы относится к другому договору")


def _overlaps(first, second):
    return ((first.valid_to is None or second["valid_from"] <= first.valid_to)
            and (second["valid_to"] is None or first.valid_from <= second["valid_to"]))


async def _new_rate(session, values, previous, user_id):
    family = await repo.rate_family(session, values)
    if previous:
        if any(getattr(previous, key) != values[key] for key in ("project_id", "contract_id", "work_type_id", "unit_id")):
            raise ValidationError("Объект, договор, вид работы и единицу версии менять нельзя; создайте отдельную расценку")
        if values["valid_from"] <= previous.valid_from:
            raise ValidationError("Начало новой версии должно быть позже начала предыдущей")
        if any(row.id != previous.id and row.valid_from >= previous.valid_from for row in family):
            raise ConflictError("Можно изменить только последнюю версию расценки")
        if previous.valid_to and values["valid_from"] - timedelta(days=1) > previous.valid_to:
            raise ValidationError("Предыдущий период уже закрыт; создайте отдельный период")
    for row in family:
        if previous and row.id == previous.id:
            continue
        if _overlaps(row, values):
            raise ValidationError("Период пересекается с существующей исторической расценкой")
    if previous:
        old = snapshot("rate", previous)
        previous.valid_to = values["valid_from"] - timedelta(days=1)
        await audit.record(session, user_id=user_id, action="directory.rate.close", entity_type="rate",
                           entity_id=str(previous.id), old_values=old, new_values=snapshot("rate", previous))
    row = repo.model("rate")(**values, created_by=user_id)
    session.add(row)
    return row


@operation
async def save(session, kind, values, *, user_id, idempotency_key, entity_id=None, expected_version=None):
    await require_change(session, user_id)
    values = validate(kind, values)
    payload = digest({"kind": kind, "values": values, "entity": entity_id,
                      "version": expected_version, "user": user_id, "action": "save"})
    # A single lock order serializes low-volume directory mutations, including period checks.
    await lock_key(session, "directory-writes", uuid.UUID(int=0))
    await lock_key(session, "directory-request", idempotency_key)
    receipt = await session.get(DirectoryMutation, idempotency_key)
    if receipt:
        if receipt.payload_hash != payload:
            raise ConflictError("Ключ сохранения уже использован для другой операции")
        return await repo.get(session, receipt.kind, receipt.entity_id)
    row = await repo.get(session, kind, entity_id, lock=True) if entity_id else None
    old = snapshot(kind, row) if row else None
    if row:
        if expected_version is None or expected_version != version(kind, row):
            raise ConflictError("Запись изменена другим пользователем. Откройте карточку заново")
        if repo.is_archived(kind, row):
            raise ValidationError("Сначала восстановите запись из архива")
        if kind in {"contract", "section"}:
            for key in ("project_id", "contract_id"):
                if key in values and values[key] != getattr(row, key):
                    raise ValidationError("Принадлежность существующей записи менять нельзя; создайте новую")
    await _references(session, kind, values)
    if "code" in values and await repo.same_code(session, kind, values["code"], entity_id):
        raise ValidationError("Такой код или обозначение уже существует, в том числе в архиве")
    try:
        async with session.begin_nested():
            if kind == "rate":
                row = await _new_rate(session, values, row, user_id)
            elif row is None:
                row = repo.model(kind)(**values)
                if kind == "project":
                    row.created_by = user_id
                    row.updated_by = user_id
                session.add(row)
            else:
                for key, value in values.items():
                    setattr(row, key, value)
                if kind == "project":
                    row.updated_by = user_id
            await session.flush()
            await audit.record(session, user_id=user_id, action="directory.update" if entity_id else "directory.create",
                               entity_type=kind, entity_id=str(row.id), old_values=old, new_values=snapshot(kind, row))
            session.add(DirectoryMutation(idempotency_key=idempotency_key, user_id=user_id,
                                         kind=kind, entity_id=row.id, payload_hash=payload))
            await session.flush()
    except IntegrityError:
        raise ValidationError("Запись конфликтует с существующими данными. Проверьте код и связи") from None
    return row


@operation
async def set_archived(session, kind, entity_id, archived, *, user_id, idempotency_key, expected_version):
    await require_change(session, user_id)
    fields(kind)
    if type(archived) is not bool:
        raise ValidationError("Некорректное действие")
    payload = digest({"kind": kind, "entity": entity_id, "archived": archived,
                      "user": user_id, "version": expected_version, "action": "archive"})
    await lock_key(session, "directory-writes", uuid.UUID(int=0))
    await lock_key(session, "directory-request", idempotency_key)
    receipt = await session.get(DirectoryMutation, idempotency_key)
    if receipt:
        if receipt.payload_hash != payload:
            raise ConflictError("Ключ сохранения уже использован")
        return await repo.get(session, receipt.kind, receipt.entity_id)
    row = await repo.get(session, kind, entity_id, lock=True)
    if expected_version != version(kind, row):
        raise ConflictError("Запись изменилась. Откройте карточку заново")
    old = snapshot(kind, row)
    if not archived:
        # Restoring does not rewrite historical fields or require filling legacy nullable codes.
        await _references(session, kind, {f.name: getattr(row, f.name) for f in fields(kind)})
    if kind == "project":
        row.is_archived = archived
        if not archived and row.status == "archived":
            row.status = "draft"
        row.updated_by = user_id
    elif kind == "contract":
        row.status = "archived" if archived else "draft"
    else:
        row.is_active = not archived
    await audit.record(session, user_id=user_id, action="directory.archive" if archived else "directory.restore",
                       entity_type=kind, entity_id=str(row.id), old_values=old, new_values=snapshot(kind, row))
    session.add(DirectoryMutation(idempotency_key=idempotency_key, user_id=user_id, kind=kind,
                                 entity_id=row.id, payload_hash=payload))
    await session.flush()
    return row


def title(kind, row):
    if kind == "contract":
        return f"{row.number} · {row.name or 'Договор'}"
    if kind == "rate":
        return f"{row.worker_rate} / {row.customer_rate} ₸ · с {row.valid_from:%d.%m.%Y}"
    return f"{getattr(row, 'code', None) or 'Без кода'} · {row.name}"


async def reference_labels(session, kind, rows, *, user_id):
    await require_permission(session, user_id, "projects.view")
    result = {}
    for field in fields(kind):
        if field.relation:
            ids = {getattr(row, field.name) for row in rows if getattr(row, field.name) is not None}
            parents = await repo.reference_rows(session, field.relation, ids)
            result[field.name] = {str(row.id): title(field.relation, row) for row in parents}
    return result
