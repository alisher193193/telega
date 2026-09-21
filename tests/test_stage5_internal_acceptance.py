from app.core.enums import AcceptanceKind, InternalAcceptanceStatus
from app.models import InternalAcceptance


def test_internal_acceptance_enums_are_defined():
    assert InternalAcceptanceStatus.APPROVED.value == "approved"
    assert InternalAcceptanceStatus.REJECTED.value == "rejected"
    assert InternalAcceptanceStatus.CORRECTED.value == "corrected"

    assert AcceptanceKind.ACCEPT.value == "accept"
    assert AcceptanceKind.CORRECTION.value == "correction"


def test_internal_acceptance_model_registered():
    assert InternalAcceptance.__tablename__ == "internal_acceptances"
    assert set(InternalAcceptance.__table__.columns.keys()) >= {
        "id",
        "work_entry_id",
        "delta_volume",
        "accepted_at",
        "result_comment",
        "accepted_by_user_id",
        "correction_reason",
        "is_active",
    }
