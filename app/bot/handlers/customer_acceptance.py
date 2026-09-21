from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards.customer_acceptance import (
    CAConfirmCallback,
    CANavCallback,
    CAProjectCallback,
    CAWorkCallback,
    confirmation_keyboard,
    projects_keyboard,
    work_entries_keyboard,
)
from app.bot.keyboards.main import BillingMenuCallback, main_menu
from app.bot.states.customer_acceptance import CustomerAcceptanceStates
from app.core.exceptions import AppError
from app.db.repositories.directories import list_active_projects
from app.db.session import session_factory
from app.models import User
from app.services import customer_acceptance as ca_service

router = Router(name="customer_acceptance")


@router.callback_query(BillingMenuCallback.filter(F.action == "customer_acceptance"))
async def start_customer_acceptance(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()

    async with session_factory() as session:
        projects = await list_active_projects(session)

    if not projects:
        await callback.answer("Нет доступных объектов", show_alert=True)
        return

    await state.set_state(CustomerAcceptanceStates.choosing_project)
    await callback.message.edit_text(
        "🧾 <b>Приёмка заказчиком</b>\n\nВыберите объект:",
        reply_markup=projects_keyboard(projects),
    )
    await callback.answer()


@router.callback_query(
    CustomerAcceptanceStates.choosing_project,
    CAProjectCallback.filter(),
)
async def choose_project(
    callback: CallbackQuery,
    callback_data: CAProjectCallback,
    state: FSMContext,
) -> None:
    async with session_factory() as session:
        entries = await ca_service.list_available_for_project(session, callback_data.project_id)

    if not entries:
        await callback.answer("По этому объекту нет работ, доступных к приёмке", show_alert=True)
        return

    await state.update_data(project_id=str(callback_data.project_id))
    await state.set_state(CustomerAcceptanceStates.choosing_work_entry)

    entry_objects = [entry for entry, _summary in entries]
    await callback.message.edit_text(
        "Выберите работу для приёмки:",
        reply_markup=work_entries_keyboard(entry_objects),
    )
    await callback.answer()


@router.callback_query(
    CustomerAcceptanceStates.choosing_work_entry,
    CAWorkCallback.filter(),
)
async def choose_work_entry(
    callback: CallbackQuery,
    callback_data: CAWorkCallback,
    state: FSMContext,
) -> None:
    async with session_factory() as session:
        try:
            summary = await ca_service.get_summary(session, callback_data.work_entry_id)
        except AppError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

    await state.update_data(work_entry_id=str(callback_data.work_entry_id))
    await state.set_state(CustomerAcceptanceStates.entering_volume)

    await callback.message.edit_text(
        "<b>Карточка работы</b>\n\n"
        f"Заявлено: {summary.claimed_volume}\n"
        f"Принято нами: {summary.internal_accepted}\n"
        f"Уже принято заказчиком: {summary.customer_accepted}\n"
        f"Осталось доступно: {summary.remaining_for_customer}\n\n"
        "Введите принимаемый заказчиком объём числом (например 12.5):",
    )
    await callback.answer()


@router.message(CustomerAcceptanceStates.entering_volume)
async def enter_volume(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace(",", ".")

    try:
        volume = Decimal(raw)
    except InvalidOperation:
        await message.answer("Введите корректное число, например 12.5")
        return

    if volume <= 0:
        await message.answer("Объём должен быть больше нуля. Введите ещё раз:")
        return

    await state.update_data(volume=str(volume))
    await state.set_state(CustomerAcceptanceStates.entering_comment)
    await message.answer("Добавьте комментарий или отправьте «-», если комментарий не нужен:")


@router.message(CustomerAcceptanceStates.entering_comment)
async def enter_comment(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    comment = None if text == "-" else text

    data = await state.update_data(comment=comment)
    await state.set_state(CustomerAcceptanceStates.confirming)

    await message.answer(
        "<b>Подтверждение приёмки</b>\n\n"
        f"Объём: {data['volume']}\n"
        f"Комментарий: {comment or '—'}\n\n"
        "Сохранить?",
        reply_markup=confirmation_keyboard(),
    )


@router.callback_query(
    CustomerAcceptanceStates.confirming,
    CAConfirmCallback.filter(),
)
async def confirm_acceptance(
    callback: CallbackQuery,
    callback_data: CAConfirmCallback,
    state: FSMContext,
    system_user: User,
) -> None:
    data = await state.get_data()

    if callback_data.action == "edit":
        await state.set_state(CustomerAcceptanceStates.entering_volume)
        await callback.message.edit_text("Введите принимаемый заказчиком объём числом ещё раз:")
        await callback.answer()
        return

    if callback_data.action == "cancel":
        await state.clear()
        await callback.message.edit_text("Приёмка отменена.")
        await callback.answer()
        return

    # Guard against double-submission by disabling the keyboard immediately.
    if data.get("processing"):
        await callback.answer("Операция уже выполняется")
        return

    await state.update_data(processing=True)
    await callback.message.edit_reply_markup(reply_markup=None)

    work_entry_id = uuid.UUID(data["work_entry_id"])
    volume = Decimal(data["volume"])
    comment = data.get("comment")

    async with session_factory() as session:
        async with session.begin():
            try:
                await ca_service.accept(
                    session,
                    work_entry_id=work_entry_id,
                    volume=volume,
                    user_id=system_user.id,
                    comment=comment,
                )
            except AppError as exc:
                await callback.answer()
                await callback.message.answer(f"⚠ {exc}")
                await state.clear()
                return

    await callback.answer("Сохранено")
    await callback.message.answer(
        f"✅ Принято заказчиком: {volume}",
        reply_markup=main_menu(),
    )
    await state.clear()


@router.callback_query(CANavCallback.filter(F.action == "back"))
async def go_back(callback: CallbackQuery, state: FSMContext) -> None:
    current = await state.get_state()

    if current == CustomerAcceptanceStates.choosing_work_entry.state:
        async with session_factory() as session:
            projects = await list_active_projects(session)
        await state.set_state(CustomerAcceptanceStates.choosing_project)
        await callback.message.edit_text("Выберите объект:", reply_markup=projects_keyboard(projects))
    else:
        await state.clear()
        await callback.message.edit_text("Возврат в главное меню.")

    await callback.answer()


@router.callback_query(CANavCallback.filter(F.action == "cancel"))
async def cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Приёмка отменена.")
    await callback.answer()
