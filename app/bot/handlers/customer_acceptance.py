import uuid
from decimal import Decimal, InvalidOperation
from html import escape
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from app.bot.keyboards.customer_acceptance import (
    CAConfirmCallback, CANavCallback, CAProjectCallback, CAWorkCallback, CAPageCallback,
    confirmation_keyboard, projects_keyboard, work_entries_keyboard, back_keyboard,
)
from app.bot.keyboards.main import BillingMenuCallback, main_menu
from app.bot.states.customer_acceptance import CustomerAcceptanceStates as States
from app.bot.middlewares.permissions import PermissionMiddleware
from app.core.exceptions import ValidationError
from app.core.numbers import volume as checked_volume
from app.db.repositories.directories import list_active_projects
from app.db.repositories.work_entries import get_work_entry
from app.db.session import session_factory
from app.models import User
from app.services import customer_acceptance as service

router = Router(name="customer_acceptance")
router.message.middleware(PermissionMiddleware("works.accept_customer"))
router.callback_query.middleware(PermissionMiddleware("works.accept_customer"))
PAGE_SIZE = 10


async def _list(callback, state, *, projects=False, page=0):
    if page < 0 or page > 100000:
        raise ValidationError("Некорректная страница")
    data = await state.get_data()
    async with session_factory() as session:
        if projects:
            entries = await list_active_projects(session, limit=PAGE_SIZE + 1, offset=page * PAGE_SIZE)
        else:
            rows = await service.list_available_for_project(session, uuid.UUID(data["project_id"]),
                                                           limit=PAGE_SIZE + 1, offset=page * PAGE_SIZE)
            entries = [entry for entry, summary in rows]
    await state.set_state(States.choosing_project if projects else States.choosing_work_entry)
    keyboard = projects_keyboard if projects else work_entries_keyboard
    await callback.message.edit_text("Выберите объект:" if projects else "Выберите работу:",
        reply_markup=keyboard(entries[:PAGE_SIZE], page=page, more=len(entries) > PAGE_SIZE))


@router.callback_query(BillingMenuCallback.filter(F.action == "customer_acceptance"))
async def start_customer_acceptance(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await _list(callback, state, projects=True)
    await callback.answer()


@router.callback_query(CAPageCallback.filter())
async def page_list(callback: CallbackQuery, callback_data: CAPageCallback, state: FSMContext):
    current = await state.get_state()
    if current not in {States.choosing_project.state, States.choosing_work_entry.state}:
        raise ValidationError("Кнопка устарела")
    await _list(callback, state, projects=current == States.choosing_project.state, page=callback_data.page)
    await callback.answer()


@router.callback_query(States.choosing_project, CAProjectCallback.filter())
async def choose_project(callback: CallbackQuery, callback_data: CAProjectCallback, state: FSMContext):
    await state.update_data(project_id=str(callback_data.project_id))
    await _list(callback, state)
    await callback.answer()


@router.callback_query(States.choosing_work_entry, CAWorkCallback.filter())
async def choose_work_entry(callback: CallbackQuery, callback_data: CAWorkCallback, state: FSMContext):
    data = await state.get_data()
    async with session_factory() as session:
        entry = await get_work_entry(session, callback_data.work_entry_id)
        if str(entry.project_id) != data.get("project_id"):
            raise ValidationError("Работа не принадлежит выбранному объекту")
        summary = await service.get_summary(session, entry.id)
    await state.update_data(work_entry_id=str(entry.id), idempotency_key=str(uuid.uuid4()))
    await state.set_state(States.entering_volume)
    await callback.message.edit_text(f"Заявлено: {summary.claimed_volume}\nПринято нами: {summary.internal_accepted}\n"
        f"Принято заказчиком: {summary.customer_accepted}\nДоступно: {summary.remaining_for_customer}\nВведите объём:",
        reply_markup=back_keyboard())
    await callback.answer()


@router.message(States.entering_volume)
async def enter_volume(message: Message, state: FSMContext):
    try:
        value = checked_volume(Decimal((message.text or "").strip().replace(",", ".")))
    except InvalidOperation:
        raise ValidationError("Введите корректное число") from None
    if value <= 0:
        raise ValidationError("Объём должен быть больше нуля")
    await state.update_data(volume=str(value))
    await state.set_state(States.entering_comment)
    await message.answer("Введите комментарий или «-»:", reply_markup=back_keyboard())


@router.message(States.entering_comment)
async def enter_comment(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    data = await state.update_data(comment=None if raw == "-" else raw)
    await state.set_state(States.confirming)
    await message.answer(f"<b>Подтверждение приёмки</b>\nОбъём: {data['volume']}\n"
                         f"Комментарий: {escape(data['comment'] or '—')}\nСохранить?",
                         reply_markup=confirmation_keyboard())


@router.callback_query(States.confirming, CAConfirmCallback.filter())
async def confirm_acceptance(callback: CallbackQuery, callback_data: CAConfirmCallback, state: FSMContext, system_user: User):
    if callback_data.action == "cancel":
        await cancel_flow(callback, state)
        return
    if callback_data.action == "edit":
        await state.set_state(States.entering_volume)
        await callback.message.edit_text("Введите объём:", reply_markup=back_keyboard())
        await callback.answer()
        return
    if callback_data.action != "save":
        raise ValidationError("Неизвестное действие")
    data = await state.get_data()
    if not all(key in data for key in ("volume", "work_entry_id", "idempotency_key")):
        raise ValidationError("Форма устарела; начните приёмку заново")
    async with session_factory() as session:
        async with session.begin():
            result = await service.accept(session, work_entry_id=uuid.UUID(data["work_entry_id"]),
                volume=Decimal(data["volume"]), idempotency_key=uuid.UUID(data["idempotency_key"]),
                user_id=system_user.id, comment=data.get("comment"))
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Приёмка сохранена: {result.id}\nОбъём: {result.accepted_volume}", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(CANavCallback.filter(F.action == "back"))
async def go_back(callback: CallbackQuery, state: FSMContext):
    current = await state.get_state()
    if current == States.confirming.state:
        await state.set_state(States.entering_comment)
        await callback.message.edit_text("Введите комментарий или «-»:", reply_markup=back_keyboard())
    elif current == States.entering_comment.state:
        await state.set_state(States.entering_volume)
        await callback.message.edit_text("Введите объём:", reply_markup=back_keyboard())
    elif current == States.entering_volume.state:
        await _list(callback, state)
    elif current == States.choosing_work_entry.state:
        await _list(callback, state, projects=True)
    else:
        await state.clear()
        await callback.message.edit_text("Возврат в главное меню. Используйте /menu.")
    await callback.answer()


@router.callback_query(CANavCallback.filter(F.action == "cancel"))
async def cancel_flow(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Приёмка отменена.")
    await callback.answer()
