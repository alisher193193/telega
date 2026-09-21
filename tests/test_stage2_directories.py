from app.core.enums import ContractStatus, ProjectStatus
from app.models import Contract, Project, Unit, WorkRate, WorkSection, WorkType


def test_directory_enums_match_stage2_contract():
    assert ProjectStatus.DRAFT.value == "draft"
    assert ProjectStatus.ACTIVE.value == "active"
    assert ProjectStatus.ARCHIVED.value == "archived"

    assert ContractStatus.DRAFT.value == "draft"
    assert ContractStatus.ACTIVE.value == "active"
    assert ContractStatus.CLOSED.value == "closed"


def test_directory_model_names_are_registered():
    assert Project.__tablename__ == "projects"
    assert Contract.__tablename__ == "contracts"
    assert WorkSection.__tablename__ == "work_sections"
    assert WorkType.__tablename__ == "work_types"
    assert Unit.__tablename__ == "units"
    assert WorkRate.__tablename__ == "work_rates"

    assert set(Project.__table__.columns.keys()) >= {
        "id",
        "code",
        "name",
        "address",
        "customer",
        "start_date",
        "planned_end_date",
        "actual_end_date",
        "status",
        "contract_amount",
        "currency",
        "comment",
        "is_archived",
    }
