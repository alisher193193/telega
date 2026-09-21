import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import AccessDeniedError
from app.models.access import User, Permission, user_roles, role_permissions


async def require_permission(session: AsyncSession, user_id: uuid.UUID | None, code: str) -> None:
    if user_id is None:
        raise AccessDeniedError("Необходим авторизованный пользователь")
    allowed = await session.scalar(
        select(Permission.id)
        .join(role_permissions, role_permissions.c.permission_id == Permission.id)
        .join(user_roles, user_roles.c.role_id == role_permissions.c.role_id)
        .join(User, User.id == user_roles.c.user_id)
        .where(User.id == user_id, User.is_active.is_(True), Permission.code == code)
        .limit(1)
    )
    if allowed is None:
        raise AccessDeniedError("Недостаточно прав для этого действия")
