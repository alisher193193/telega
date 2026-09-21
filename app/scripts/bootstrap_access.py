import asyncio

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.core.enums import PermissionCode
from app.db.session import engine, session_factory
from app.models import Permission, Role, User
from app.models.access import role_permissions, user_roles

settings = get_settings()

PERMISSIONS = {
    PermissionCode.ADMIN_ACCESS.value: "Полный административный доступ",
    PermissionCode.USERS_MANAGE.value: "Управление пользователями",
    PermissionCode.DIRECTORIES_MANAGE.value: "Управление справочниками",
    PermissionCode.WORKERS_VIEW.value: "Просмотр списка работников",
    PermissionCode.WORKERS_MANAGE.value: "Управление работниками",
    PermissionCode.PROJECTS_VIEW.value: "Просмотр объектов",
    PermissionCode.PROJECTS_MANAGE.value: "Управление объектами",
    PermissionCode.WORKS_VIEW.value: "Просмотр работ",
    PermissionCode.WORKS_CREATE.value: "Внесение выполненных работ",
    PermissionCode.WORKS_EDIT.value: "Редактирование работ",
    PermissionCode.WORKS_CANCEL.value: "Отмена работ",
    PermissionCode.WORKS_ACCEPT_INTERNAL.value: "Внутренняя приёмка работ",
    PermissionCode.WORKS_ACCEPT_CUSTOMER.value: "Приёмка заказчиком",
    PermissionCode.PAYMENTS_VIEW.value: "Просмотр начислений и выплат",
    PermissionCode.PAYMENTS_MANAGE.value: "Начисления и выплаты людям",
    PermissionCode.CASH_VIEW.value: "Просмотр остатка кассы",
    PermissionCode.CASH_MANAGE.value: "Управление общей кассой",
    PermissionCode.REPORTS_VIEW.value: "Просмотр отчётов",
    PermissionCode.ACTS_VIEW.value: "Просмотр актов",
    PermissionCode.ACTS_MANAGE.value: "Формирование актов",
    PermissionCode.EXTRA_WORKS_MANAGE.value: "Управление дополнительными работами",
    PermissionCode.AUDIT_VIEW.value: "Просмотр журнала изменений",
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
                    settings.ilya_telegram_id,
                    settings.ilya_full_name,
                    admin_role,
                ),
                (
                    settings.asan_telegram_id,
                    settings.asan_full_name,
                    admin_role,
                ),
                (
                    settings.alisher_telegram_id,
                    settings.alisher_full_name,
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
