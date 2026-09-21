import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.bot.handlers.start import router as start_router
from app.bot.middlewares.access import AccessMiddleware
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import engine


async def main() -> None:
    configure_logging()
    settings = get_settings()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    dispatcher = Dispatcher()

    access_middleware = AccessMiddleware()
    dispatcher.message.outer_middleware(access_middleware)
    dispatcher.callback_query.outer_middleware(access_middleware)

    dispatcher.include_router(start_router)

    await bot.set_my_commands([
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="menu", description="Главное меню"),
    ])

    try:
        logging.info("Telegram-бот запускается")
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())