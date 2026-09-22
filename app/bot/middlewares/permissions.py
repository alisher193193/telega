from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery
from app.core.exceptions import AppError
from app.core.operations import operation
from app.db.session import session_factory
from app.services.access import require_permission


class PermissionMiddleware(BaseMiddleware):
    def __init__(self, default_permission):
        self.default_permission = default_permission

    @operation
    async def __call__(self, handler, event, data):
        permission = data["handler"].flags.get("permission", self.default_permission)
        try:
            async with session_factory() as session:
                await require_permission(session, data["system_user"].id, permission)
            return await handler(event, data)
        except AppError as exc:
            if isinstance(event, CallbackQuery):
                await event.answer(str(exc), show_alert=True)
            else:
                await event.answer(str(exc), parse_mode=None)
