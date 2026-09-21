from decimal import Decimal
from app.core.enums import WorkEntryStatus
from app.models.work_entries import WorkStatusHistory
from app.db.repositories import act as act_repo, customer_acceptance as ca_repo
from app.db.repositories.internal_acceptance import total_internal_accepted_volume


async def synchronize(session, work, user_id, comment):
    if work.status in {"cancelled", "invoiced", "paid"}:
        return
    included = await act_repo.volume_in_active_acts(session, work.id)
    accepted = await ca_repo.total_accepted_volume(session, work.id)
    internal = await total_internal_accepted_volume(session, work.id)
    status = (WorkEntryStatus.INCLUDED_IN_ACT.value if included > Decimal(0) else
              WorkEntryStatus.ACCEPTED_CUSTOMER.value if accepted > Decimal(0) else
              WorkEntryStatus.ACCEPTED_INTERNAL.value if internal > Decimal(0) else
              WorkEntryStatus.DONE.value)
    if status != work.status:
        session.add(WorkStatusHistory(work_entry_id=work.id, old_status=work.status,
                    new_status=status, changed_by=user_id, comment=comment))
        work.status = status
