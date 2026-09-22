from sqlalchemy import select, func
from app.models.acts import Act, ActLine, CustomerAcceptance
from app.models.work_acceptance import InternalAcceptance
from app.models.work_entries import WorkEntry


def accepted_expression():
    return (select(func.coalesce(func.sum(CustomerAcceptance.accepted_volume), 0))
            .where(CustomerAcceptance.work_entry_id == WorkEntry.id,
                   CustomerAcceptance.status == "accepted").correlate(WorkEntry).scalar_subquery())


def occupied_expression():
    return (select(func.coalesce(func.sum(ActLine.accepted_volume), 0))
            .join(Act, Act.id == ActLine.act_id)
            .where(ActLine.work_entry_id == WorkEntry.id, ActLine.cancelled_at.is_(None),
                   Act.status != "cancelled").correlate(WorkEntry).scalar_subquery())


async def for_act(session, act, *, limit=10, offset=0):
    available = accepted_expression() - occupied_expression()
    statement = (select(WorkEntry, available.label("available"))
                 .where(WorkEntry.project_id == act.project_id,
                        WorkEntry.contract_id == act.contract_id,
                        WorkEntry.status != "cancelled", available > 0)
                 .order_by(WorkEntry.entry_date.desc(), WorkEntry.id).limit(limit).offset(offset))
    return list((await session.execute(statement)).all())


async def for_acceptance(session, project_id, *, statuses, limit=10, offset=0):
    internal = (select(func.coalesce(func.sum(InternalAcceptance.delta_volume), 0))
                .where(InternalAcceptance.work_entry_id == WorkEntry.id,
                       InternalAcceptance.is_active.is_(True)).correlate(WorkEntry).scalar_subquery())
    accepted = accepted_expression()
    statement = (select(WorkEntry, internal.label("internal"), accepted.label("accepted"))
                 .where(WorkEntry.project_id == project_id, WorkEntry.status.in_(statuses), internal > accepted)
                 .order_by(WorkEntry.entry_date.desc(), WorkEntry.id).limit(limit).offset(offset))
    return list((await session.execute(statement)).all())
