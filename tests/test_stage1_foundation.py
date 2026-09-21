from app.core.config import Settings, get_settings
from app.core.enums import PermissionCode


def test_settings_have_required_fields(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/app")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("TZ", "Asia/Almaty")

    settings = Settings()

    assert settings.bot_token == "test-token"
    assert settings.database_url.endswith("app")
    assert settings.app_env == "development"
    assert settings.timezone == "Asia/Almaty"


def test_required_permission_codes_are_available():
    required = {
        "admin.access",
        "users.manage",
        "directories.manage",
        "workers.view",
        "workers.manage",
        "projects.view",
        "projects.manage",
        "works.view",
        "works.create",
        "works.edit",
        "works.cancel",
        "works.accept_internal",
        "works.accept_customer",
        "payments.view",
        "payments.manage",
        "cash.view",
        "cash.manage",
        "reports.view",
        "acts.view",
        "acts.manage",
        "extra_works.manage",
        "audit.view",
    }

    assert required.issubset({code.value for code in PermissionCode})


def test_get_settings_returns_singleton_like_instance(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "token-1")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/app")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("TZ", "UTC")

    first = get_settings()
    second = get_settings()

    assert first is second
    assert first.bot_token == "token-1"
