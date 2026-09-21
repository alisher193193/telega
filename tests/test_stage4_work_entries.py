from app.core.enums import WorkEntryStatus
from app.models import WorkAllocation, WorkEntry, WorkStatusHistory


def test_work_entry_statuses_are_defined():
    assert WorkEntryStatus.DONE.value == "done"
    assert WorkEntryStatus.ACCEPTED_INTERNAL.value == "accepted_internal"
    assert WorkEntryStatus.REQUIRES_FIX.value == "requires_fix"
    assert WorkEntryStatus.SUBMITTED_CUSTOMER.value == "submitted_customer"
    assert WorkEntryStatus.ACCEPTED_CUSTOMER.value == "accepted_customer"
    assert WorkEntryStatus.CANCELLED.value == "cancelled"


def test_work_entry_models_are_registered():
    assert WorkEntry.__tablename__ == "work_entries"
    assert WorkAllocation.__tablename__ == "work_entry_allocations"
    assert WorkStatusHistory.__tablename__ == "work_status_history"

    assert set(WorkEntry.__table__.columns.keys()) >= {
        "id",
        "entry_date",
        "project_id",
        "contract_id",
        "work_section_id",
        "work_type_id",
        "unit_id",
        "worker_id",
        "crew_id",
        "status",
        "claimed_volume",
        "worker_rate_snapshot",
        "customer_rate_snapshot",
        "is_additional",
        "idempotency_key",
    }
