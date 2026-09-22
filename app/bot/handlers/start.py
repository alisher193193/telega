from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.bot.keyboards.main import billing_menu, main_menu
from app.models import User


router = Router(name="start")


@router.message(CommandStart())
@router.message(Command("menu"))
async def start_handler(
    message: Message,
    system_user: User,
) -> None:
    await message.answer(
        f"Добро пожаловать, <b>{system_user.full_name}</b>!\n\n"
        "Система рабочего и финансового учёта.\n"
        "Выберите нужный раздел:",
        reply_markup=main_menu(),
    )


@router.message(F.text == "📄 К выставлению")
async def billing_menu_handler(message: Message) -> None:
    await message.answer(
        "<b>К выставлению</b>\n\nВыберите раздел:",
        reply_markup=billing_menu(),
    )


@router.message(
    F.text.in_(
        {
            "📝 Внести данные",
            "👥 Люди",
            "🏗 Объекты",
            "💰 Касса",
            "📊 Отчёты",
        }
    )
)
async def menu_handler(message: Message) -> None:
    section = message.text or "Раздел"

    await message.answer(
        f"<b>{section}</b>\n\n"
        "Раздел подключён к меню и будет реализован следующим этапом.",
    )


@router.message()
async def unknown_handler(message: Message) -> None:
    await message.answer(
        "Используйте кнопки главного меню.",
        reply_markup=main_menu(),
    )