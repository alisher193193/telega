from app.core.enums import AcceptanceKind, WorkEntryStatus
from app.models import Act, ActLine, CustomerAcceptance


def test_customer_acceptance_and_acts_are_defined():
    assert AcceptanceKind.ACCEPT.value == "accept"
    assert AcceptanceKind.CORRECTION.value == "correction"

    assert WorkEntryStatus.SUBMITTED_CUSTOMER.value == "submitted_customer"
    assert WorkEntryStatus.ACCEPTED_CUSTOMER.value == "accepted_customer"
    assert WorkEntryStatus.INCLUDED_IN_ACT.value == "included_in_act"

    assert CustomerAcceptance.__tablename__ == "customer_acceptances"
    assert Act.__tablename__ == "acts"
    assert ActLine.__tablename__ == "act_lines"

    assert set(CustomerAcceptance.__table__.columns.keys()) >= {
        "id",
        "work_entry_id",
        "project_id",
        "contract_id",
        "accepted_by_customer",
        "accepted_at",
        "status",
        "comment",
    }

    assert set(Act.__table__.columns.keys()) >= {
        "id",
        "project_id",
        "contract_id",
        "act_number",
        "act_date",
        "status",
        "total_amount",
        "created_by",
    }

    assert set(ActLine.__table__.columns.keys()) >= {
        "id",
        "act_id",
        "work_entry_id",
        "accepted_volume",
        "amount",
        "comment",
    }
