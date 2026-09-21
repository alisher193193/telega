from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select

from app.db.session import session_factory
from app.models import User


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[
            [TelegramObject, dict[str, Any]],
            Awaitable[Any],
        ],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user = data.get("event_from_user")

        if telegram_user is None:
            return None

        async with session_factory() as session:
            user = await session.scalar(
                select(User).where(
                    User.telegram_id == telegram_user.id,
                    User.is_active.is_(True),
                )
            )

        if user is None:
            text = (
                "⛔ У вас нет доступа к системе.\n\n"
                f"Ваш Telegram ID: <code>{telegram_user.id}</code>"
            )

            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    "У вас нет доступа",
                    show_alert=True,
                )

            return None

        data["system_user"] = user
        return await handler(event, data)
