"""SQL queries for the six directory screens; predicates precede pagination."""
import uuid
from sqlalchemy import select, or_, func
from app.core.exceptions import NotFoundError, ValidationError
from app.models.directories import Project, Contract, WorkSection, WorkType, Unit, WorkRate

MODELS = {"project": Project, "contract": Contract, "section": WorkSection,
          "work_type": WorkType, "unit": Unit, "rate": WorkRate}


def model(kind):
    if kind not in MODELS:
        raise ValidationError("Неизвестный справочник")
    return MODELS[kind]


def active_predicate(kind):
    cls = model(kind)
    if kind == "project":
        return cls.is_archived.is_(False) & (cls.status != "archived")
    if kind == "contract":
        return cls.status != "archived"
    return cls.is_active.is_(True)


def is_archived(kind, row):
    if kind == "project":
        return row.is_archived or row.status == "archived"
    if kind == "contract":
        return row.status == "archived"
    return not row.is_active


async def get(session, kind, entity_id, *, lock=False):
    cls = model(kind)
    stmt = select(cls).where(cls.id == entity_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(stmt)
    if row is None:
        raise NotFoundError("Запись не найдена")
    return row


def listing_statement(kind, *, query="", archived=False, scope=None):
    cls = model(kind)
    stmt = select(cls).where(~active_predicate(kind) if archived else active_predicate(kind))
    for key, value in (scope or {}).items():
        if key not in {"project_id", "contract_id", "work_section_id", "work_type_id", "unit_id"} or not hasattr(cls, key):
            raise ValidationError("Недопустимый фильтр")
        stmt = stmt.where(getattr(cls, key) == value)
    query = query.strip()
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        terms = [getattr(cls, key).ilike(pattern, escape="\\") for key in
                 ("name", "code", "number", "customer", "address", "description", "comment") if hasattr(cls, key)]
        if kind == "rate":
            terms = [WorkRate.work_type_id.in_(select(WorkType.id).where(
                or_(WorkType.name.ilike(pattern, escape="\\"), WorkType.code.ilike(pattern, escape="\\")))),
                WorkRate.project_id.in_(select(Project.id).where(Project.name.ilike(pattern, escape="\\")))]
        stmt = stmt.where(or_(*terms))
    order = cls.valid_from.desc() if kind == "rate" else getattr(cls, "name", cls.id)
    return stmt.order_by(order, cls.id)


async def list_page(session, kind, *, query="", archived=False, scope=None, page=0, size=8):
    if not isinstance(page, int) or page < 0 or page > 100000 or size < 1 or size > 50:
        raise ValidationError("Некорректная страница")
    stmt = listing_statement(kind, query=query, archived=archived, scope=scope)
    rows = list((await session.scalars(stmt.limit(size + 1).offset(page * size))).all())
    return rows[:size], len(rows) > size


async def same_code(session, kind, code, exclude_id=None):
    cls = model(kind)
    stmt = select(cls.id).where(func.lower(cls.code) == code.lower())
    if exclude_id:
        stmt = stmt.where(cls.id != exclude_id)
    return await session.scalar(stmt.limit(1))


async def rate_family(session, values):
    stmt = select(WorkRate).where(*(getattr(WorkRate, key) == values[key] for key in
        ("project_id", "contract_id", "work_type_id", "unit_id"))).order_by(WorkRate.valid_from, WorkRate.id)
    return list((await session.scalars(stmt.with_for_update())).all())


async def reference_rows(session, kind, ids):
    if not ids:
        return []
    cls = model(kind)
    return list((await session.scalars(select(cls).where(cls.id.in_(ids)))).all())
