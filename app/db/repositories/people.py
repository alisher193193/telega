"""People queries: filter before pagination; locks are requested by services."""
from sqlalchemy import select, case
from app.models.people import Worker, Specialty, Crew, CrewMember
from app.models.directories import Project
from app.core.exceptions import NotFoundError, ValidationError

MODELS = {"worker": Worker, "specialty": Specialty, "crew": Crew, "member": CrewMember, "project": Project}


async def get(session, kind, entity_id, *, lock=False):
    model = MODELS[kind]
    stmt = select(model).where(model.id == entity_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    row = await session.scalar(stmt)
    if row is None:
        raise NotFoundError("Запись не найдена")
    return row


def listing(kind, *, query="", status="active", project_id=None):
    if kind not in {"worker", "specialty", "crew", "project"}:
        raise ValidationError("Неизвестный список")
    model = MODELS[kind]
    stmt = select(model)
    if kind == "worker":
        if status == "active":
            stmt = stmt.where(Worker.is_archived.is_(False), Worker.status != "terminated")
        elif status == "inactive":
            stmt = stmt.where((Worker.status == "terminated") | Worker.is_archived.is_(True))
        elif status != "all":
            raise ValidationError("Неизвестный статус")
        if project_id:
            stmt = stmt.where(Worker.current_project_id == project_id)
        stmt = stmt.order_by(case((Worker.status == "working", 0), else_=1))
    else:
        active = (Specialty.is_active.is_(True) if kind == "specialty" else
                  Crew.status == "active" if kind == "crew" else
                  Project.is_archived.is_(False) & (Project.status != "archived"))
        stmt = stmt.where(~active if status == "inactive" else active)
    name = model.full_name if kind == "worker" else model.name
    if query.strip():
        pattern = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(name.ilike(f"%{pattern}%", escape="\\"))
    return stmt.order_by(name, model.id)


async def list_page(session, kind, *, page=0, size=8, **filters):
    if type(page) is not int or not 0 <= page <= 100000 or not 1 <= size <= 20:
        raise ValidationError("Некорректная страница")
    rows = list((await session.scalars(listing(kind, **filters).offset(page * size).limit(size + 1))).all())
    return rows[:size], len(rows) > size


async def current_membership(session, worker_id, *, lock=False):
    stmt = select(CrewMember).where(CrewMember.worker_id == worker_id, CrewMember.left_at.is_(None))
    if lock:
        stmt = stmt.with_for_update()
    return await session.scalar(stmt)


async def members(session, crew_id, *, ended=False, page=0):
    if type(page) is not int or not 0 <= page <= 100000:
        raise ValidationError("Некорректная страница")
    stmt = (select(CrewMember, Worker.full_name).join(Worker, Worker.id == CrewMember.worker_id)
            .where(CrewMember.crew_id == crew_id,
                   CrewMember.left_at.is_not(None) if ended else CrewMember.left_at.is_(None))
            .order_by(CrewMember.joined_at.desc(), CrewMember.id).offset(page * 8).limit(9))
    rows = list((await session.execute(stmt)).all())
    return rows[:8], len(rows) > 8


async def open_members(session, crew_id):
    return list((await session.scalars(select(CrewMember).where(
        CrewMember.crew_id == crew_id, CrewMember.left_at.is_(None)).with_for_update())).all())
