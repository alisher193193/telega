from app.core.enums import CrewStatus, WorkerStatus
from app.models import Crew, CrewMember, Worker


def test_people_enums_are_available():
    assert WorkerStatus.WORKING.value == "working"
    assert WorkerStatus.TERMINATED.value == "terminated"
    assert WorkerStatus.ON_LEAVE.value == "on_leave"

    assert CrewStatus.ACTIVE.value == "active"
    assert CrewStatus.ARCHIVED.value == "archived"


def test_people_models_are_registered():
    assert Worker.__tablename__ == "workers"
    assert Crew.__tablename__ == "crews"
    assert CrewMember.__tablename__ == "crew_members"

    assert set(Worker.__table__.columns.keys()) >= {
        "id",
        "full_name",
        "phone",
        "specialty",
        "payment_type",
        "base_rate",
        "current_project_id",
        "status",
        "hire_date",
        "termination_date",
        "comment",
        "is_archived",
    }
