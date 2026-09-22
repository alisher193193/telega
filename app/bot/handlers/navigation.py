"""Reserved navigation is dispatched before every FSM text-field handler."""
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from app.bot.handlers import start, directories
from app.bot.keyboards.main import main_menu
from app.core.exceptions import AppError
from app.core.operations import operation
from app.db.session import session_factory
from app.models import User
from app.services.access import require_permission

router = Router(name="navigation")
MENU_TEXTS = {"📝 Внести данные", "👥 Люди", "🏗 Объекты", "💰 Касса", "📊 Отчёты", "📄 К выставлению"}
BACK_TEXTS = {"Назад", "⬅ Назад"}
CANCEL_TEXTS = {"Отменить", "Отмена", "✖ Отменить", "✖ Отмена"}
HOME_TEXTS = {"Главное меню", "🏠 Главное меню", "Назад в главное меню", "⬅ В главное меню"}


@router.message(CommandStart())
@router.message(Command("menu"))
@router.message(F.text.in_(HOME_TEXTS))
async def home(message: Message, state: FSMContext, system_user: User):
    await state.clear()
    await start.start_handler(message, system_user)


@router.message(F.text.in_(MENU_TEXTS))
@operation
async def section(message: Message, state: FSMContext, system_user: User):
    try:
        if message.text == "🏗 Объекты":
            async with session_factory() as session:
                await require_permission(session, system_user.id, "projects.view")
            await directories.open_section(message, state, system_user)
        else:
            await state.clear()
            if message.text == "📄 К выставлению":
                await start.billing_menu_handler(message)
            else:
                await start.menu_handler(message)
    except AppError as exc:
        await message.answer(str(exc), parse_mode=None)


@router.message(Command("cancel"))
@router.message(F.text.in_(CANCEL_TEXTS | BACK_TEXTS))
@operation
async def control(message: Message, state: FSMContext, system_user: User):
    current = await state.get_state()
    if message.text in BACK_TEXTS and current and current.startswith("DirectoryStates:"):
        try:
            async with session_factory() as session:
                await require_permission(session, system_user.id, "projects.view")
            await directories.go_back(message, state, system_user)
        except AppError as exc:
            await message.answer(str(exc), parse_mode=None)
    else:
        await state.clear()
        await message.answer("Ввод отменён. Главное меню.", reply_markup=main_menu())
