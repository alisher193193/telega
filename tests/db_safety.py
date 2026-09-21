"""Validate test targets without opening a connection or exposing credentials."""
from sqlalchemy.engine import make_url


def validate_test_database_url(test_url: str | None, application_url: str | None = None):
    if not test_url:
        raise ValueError("Интеграционные тесты требуют TEST_DATABASE_URL; рабочая БД запрещена")
    try:
        target = make_url(test_url)
        application = make_url(application_url) if application_url else None
    except Exception:
        raise ValueError("Некорректный URL базы; значения подключения скрыты") from None
    if target.get_backend_name() != "postgresql" or target.drivername != "postgresql+asyncpg":
        raise ValueError("TEST_DATABASE_URL должен использовать postgresql+asyncpg")
    name = target.database or ""
    if name.lower() == "work_accounting" or not name.endswith("_test"):
        raise ValueError("Тестовая БД должна оканчиваться на _test; work_accounting запрещена")
    # Query parameters can override dbname/host in driver-specific ways.
    if target.query:
        raise ValueError("Параметры query в TEST_DATABASE_URL запрещены")
    if application:
        same_database = (target.host, target.port or 5432, target.database) == (
            application.host, application.port or 5432, application.database
        )
        if target == application or same_database:
            raise ValueError("TEST_DATABASE_URL указывает на DATABASE_URL; запуск запрещён")
    return target
