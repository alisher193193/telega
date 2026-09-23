"""Explicit operator command. Never called by pytest or application startup."""
import asyncio
import os

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.db_safety import validate_test_database_url

REVISION = "d91f6a20b843"


async def verify_database(target):
    engine = create_async_engine(target)
    try:
        async with engine.connect() as conn:
            if await conn.scalar(text("SELECT current_database()")) != "work_accounting_test":
                raise ValueError("Фактическая БД не work_accounting_test; миграция запрещена")
    finally:
        await engine.dispose()


def main():
    try:
        target = validate_test_database_url(os.getenv("TEST_DATABASE_URL"), os.getenv("DATABASE_URL"))
        if target.database != "work_accounting_test":
            raise ValueError("Разрешена только work_accounting_test")
        if ScriptDirectory.from_config(Config("alembic.ini")).get_heads() != [REVISION]:
            raise ValueError("Head изменился; требуется повторная проверка миграций")
        asyncio.run(verify_database(target))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    # The child process gets the test URL only. Neither the file nor the production service changes.
    os.environ["DATABASE_URL"] = target.render_as_string(hide_password=False).replace("%", "%%")
    os.execvp("alembic", ["alembic", "upgrade", "head"])


if __name__ == "__main__":
    main()
