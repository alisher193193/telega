from enum import Enum


class PermissionCode(str, Enum):
    ADMIN_ACCESS = "admin.access"
    USERS_MANAGE = "users.manage"
    DIRECTORIES_MANAGE = "directories.manage"
    WORKERS_VIEW = "workers.view"
    WORKERS_MANAGE = "workers.manage"
    PROJECTS_VIEW = "projects.view"
    PROJECTS_MANAGE = "projects.manage"
    WORKS_VIEW = "works.view"
    WORKS_CREATE = "works.create"
    WORKS_EDIT = "works.edit"
    WORKS_CANCEL = "works.cancel"
    WORKS_ACCEPT_INTERNAL = "works.accept_internal"
    WORKS_ACCEPT_CUSTOMER = "works.accept_customer"
    PAYMENTS_VIEW = "payments.view"
    PAYMENTS_MANAGE = "payments.manage"
    CASH_VIEW = "cash.view"
    CASH_MANAGE = "cash.manage"
    REPORTS_VIEW = "reports.view"
    ACTS_VIEW = "acts.view"
    ACTS_MANAGE = "acts.manage"
    EXTRA_WORKS_MANAGE = "extra_works.manage"
    AUDIT_VIEW = "audit.view"


class AppEnv(str, Enum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class ContractStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"
    CLOSED = "closed"


class WorkerStatus(str, Enum):
    WORKING = "working"
    TERMINATED = "terminated"
    ON_LEAVE = "on_leave"


class CrewStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class WorkEntryStatus(str, Enum):
    DONE = "done"
    ACCEPTED_INTERNAL = "accepted_internal"
    REQUIRES_FIX = "requires_fix"
    SUBMITTED_CUSTOMER = "submitted_customer"
    ACCEPTED_CUSTOMER = "accepted_customer"
    INCLUDED_IN_ACT = "included_in_act"
    INVOICED = "invoiced"
    PAID = "paid"
    CANCELLED = "cancelled"


class InternalAcceptanceStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTED = "corrected"


class AcceptanceKind(str, Enum):
    ACCEPT = "accept"
    CORRECTION = "correction"


class CashTransactionType(str, Enum):
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    ADJUSTMENT = "adjustment"


class WorkerAccrualType(str, Enum):
    PIECEWORK = "piecework"
    SALARY = "salary"
    DAILY_RATE = "daily_rate"
    PREMIUM = "premium"
    DEDUCTION = "deduction"
    ADJUSTMENT = "adjustment"


class WorkerPaymentType(str, Enum):
    ADVANCE = "advance"
    SALARY = "salary"
    FINAL_SETTLEMENT = "final_settlement"
    PREMIUM = "premium"
    RETURN_TO_WORKER = "return_to_worker"
    OTHER = "other"
