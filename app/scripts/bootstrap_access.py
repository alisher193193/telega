import asyncio
import os
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import engine, session_factory
from app.models import Permission, Role, User
from app.models.access import role_permissions, user_roles


PERMISSIONS = {
    "admin.access": "Полный административный доступ",
    "users.manage": "Управление пользователями",
    "directories.manage": "Управление справочниками",
    "works.create": "Внесение выполненных работ",
    "works.accept_internal": "Внутренняя приёмка работ",
    "works.accept_customer": "Приёмка заказчиком",
    "payments.manage": "Начисления и выплаты людям",
    "cash.manage": "Управление общей кассой",
    "reports.view": "Просмотр отчётов",
    "acts.manage": "Формирование актов",
    "audit.view": "Просмотр журнала изменений",
}


async def get_or_create_role(
    session,
    name: str,
    description: str,
) -> Role:
    role = await session.scalar(
        select(Role).where(Role.name == name)
    )

    if role is None:
        role = Role(
            name=name,
            description=description,
        )
        session.add(role)
        await session.flush()

    return role


async def get_or_create_permissions(session) -> list[Permission]:
    result: list[Permission] = []

    for code, description in PERMISSIONS.items():
        permission = await session.scalar(
            select(Permission).where(Permission.code == code)
        )

        if permission is None:
            permission = Permission(
                code=code,
                description=description,
            )
            session.add(permission)
            await session.flush()

        result.append(permission)

    return result


async def get_or_create_user(
    session,
    telegram_id: int,
    full_name: str,
) -> User:
    user = await session.scalar(
        select(User).where(User.telegram_id == telegram_id)
    )

    if user is None:
        user = User(
            telegram_id=telegram_id,
            full_name=full_name,
            is_active=True,
        )
        session.add(user)
        await session.flush()
    else:
        user.full_name = full_name
        user.is_active = True

    return user


async def main() -> None:
    async with session_factory() as session:
        async with session.begin():
            admin_role = await get_or_create_role(
                session,
                name="admin",
                description="Полный административный доступ",
            )
            developer_role = await get_or_create_role(
                session,
                name="developer",
                description="Разработчик системы",
            )

            permissions = await get_or_create_permissions(session)

            # В пилоте обе роли получают полный набор прав.
            for role in (admin_role, developer_role):
                for permission in permissions:
                    statement = (
                        insert(role_permissions)
                        .values(
                            role_id=role.id,
                            permission_id=permission.id,
                        )
                        .on_conflict_do_nothing()
                    )
                    await session.execute(statement)

            users_data = [
                (
                    int(os.environ["ILYA_TELEGRAM_ID"]),
                    os.getenv("ILYA_FULL_NAME", "Илья"),
                    admin_role,
                ),
                (
                    int(os.environ["ASAN_TELEGRAM_ID"]),
                    os.getenv("ASAN_FULL_NAME", "Асан"),
                    admin_role,
                ),
                (
                    int(os.environ["ALISHER_TELEGRAM_ID"]),
                    os.getenv("ALISHER_FULL_NAME", "Alisher"),
                    developer_role,
                ),
            ]

            for telegram_id, full_name, role in users_data:
                user = await get_or_create_user(
                    session,
                    telegram_id,
                    full_name,
                )

                statement = (
                    insert(user_roles)
                    .values(
                        user_id=user.id,
                        role_id=role.id,
                    )
                    .on_conflict_do_nothing()
                )
                await session.execute(statement)

                print(
                    f"Пользователь настроен: "
                    f"{full_name} — {role.name}"
                )

    await engine.dispose()
    print("Начальная настройка доступа завершена")


if __name__ == "__main__":
    asyncio.run(main())
