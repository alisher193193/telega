from app.core.enums import CashTransactionType, WorkerAccrualType, WorkerPaymentType
from app.models import CashAccount, CashTransaction, WorkerAccrual, WorkerPayment


def test_cash_and_people_enums_are_defined():
    assert CashTransactionType.INCOME.value == "income"
    assert CashTransactionType.EXPENSE.value == "expense"
    assert CashTransactionType.TRANSFER.value == "transfer"

    assert WorkerAccrualType.PIECEWORK.value == "piecework"
    assert WorkerAccrualType.SALARY.value == "salary"
    assert WorkerAccrualType.PREMIUM.value == "premium"

    assert WorkerPaymentType.ADVANCE.value == "advance"
    assert WorkerPaymentType.SALARY.value == "salary"
    assert WorkerPaymentType.OTHER.value == "other"


def test_cash_and_people_models_are_registered():
    assert CashAccount.__tablename__ == "cash_accounts"
    assert CashTransaction.__tablename__ == "cash_transactions"
    assert WorkerAccrual.__tablename__ == "worker_accruals"
    assert WorkerPayment.__tablename__ == "worker_payments"

    assert set(CashAccount.__table__.columns.keys()) >= {
        "id",
        "name",
        "account_type",
        "owner",
        "currency",
        "is_active",
        "opening_balance",
    }

    assert set(WorkerAccrual.__table__.columns.keys()) >= {
        "id",
        "worker_id",
        "project_id",
        "accrual_date",
        "accrual_type",
        "amount",
        "status",
    }
