from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from app.bot.keyboards.act import (
    ActCardActionCallback,
    ActContractCallback,
    ActLineCallback,
    ActNavCallback,
    ActOpenCallback,
    ActProjectCallback,
    ActWorkCallback,
    act_card_keyboard,
    acts_list_keyboard,
    available_work_entries_keyboard,
    contracts_keyboard,
    line_card_keyboard,
    lines_keyboard,
    projects_keyboard,
)
from app.bot.keyboards.main import BillingMenuCallback, main_menu
from app.bot.states.act import ActStates
from app.core.exceptions import AppError
from app.db.repositories import act as act_repo
from app.db.repositories.directories import list_active_projects, list_contracts_for_project
from app.db.session import session_factory
from app.models import Project, User
from app.reports.act_excel import generate_act_excel
from app.services import act as act_service
from app.services import customer_acceptance as ca_service

router = Router(name="acts")


def _act_card_text(act) -> str:
    return (
        f"<b>Акт №{act.act_number}</b> от {act.act_date:%d.%m.%Y}\n"
        f"Статус: {act.status}\n"
        f"Сумма: {act.total_amount}\n"
        + (f"Причина отмены: {act.cancellation_reason}\n" if act.cancellation_reason else "")
    )


async def _show_act_card(callback: CallbackQuery, state: FSMContext, act_id: uuid.UUID) -> None:
    async with session_factory() as session:
        act = await act_repo.get_or_raise(session, act_id)

    await state.set_state(ActStates.viewing_act)
    await state.update_data(act_id=str(act_id))
    await callback.message.edit_text(_act_card_text(act), reply_markup=act_card_keyboard(act))


@router.callback_query(BillingMenuCallback.filter(F.action == "acts"))
async def start_acts(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()

    async with session_factory() as session:
        acts = await act_repo.list_acts(session)

    await state.set_state(ActStates.listing)
    await callback.message.edit_text(
        "📄 <b>Акты</b>\n\nВыберите акт или создайте новый черновик:",
        reply_markup=acts_list_keyboard(acts),
    )
    await callback.answer()


@router.callback_query(ActStates.listing, ActOpenCallback.filter())
async def open_act(callback: CallbackQuery, callback_data: ActOpenCallback, state: FSMContext) -> None:
    await _show_act_card(callback, state, callback_data.act_id)
    await callback.answer()


@router.callback_query(ActNavCallback.filter(F.action == "new"))
async def new_act_choose_project(callback: CallbackQuery, state: FSMContext) -> None:
    async with session_factory() as session:
        projects = await list_active_projects(session)

    if not projects:
        await callback.answer("Нет доступных объектов", show_alert=True)
        return

    await state.set_state(ActStates.choosing_project)
    await callback.message.edit_text("Выберите объект для акта:", reply_markup=projects_keyboard(projects))
    await callback.answer()


@router.callback_query(ActStates.choosing_project, ActProjectCallback.filter())
async def choose_project(
    callback: CallbackQuery, callback_data: ActProjectCallback, state: FSMContext
) -> None:
    async with session_factory() as session:
        contracts = await list_contracts_for_project(session, callback_data.project_id)

    await state.update_data(project_id=str(callback_data.project_id))
    await state.set_state(ActStates.choosing_contract)
    await callback.message.edit_text("Выберите договор:", reply_markup=contracts_keyboard(contracts))
    await callback.answer()


@router.callback_query(ActStates.choosing_contract, ActContractCallback.filter())
async def choose_contract(
    callback: CallbackQuery,
    callback_data: ActContractCallback,
    state: FSMContext,
    system_user: User,
) -> None:
    data = await state.get_data()
    project_id = uuid.UUID(data["project_id"])
    contract_id = None if callback_data.contract_id == "none" else uuid.UUID(callback_data.contract_id)

    async with session_factory() as session:
        project = await session.get(Project, project_id)
        act_number = f"{date.today():%Y%m%d}-{project.code}-{uuid.uuid4().hex[:6]}"

        async with session.begin():
            act = await act_service.create_draft(
                session,
                project_id=project_id,
                contract_id=contract_id,
                act_number=act_number,
                act_date=date.today(),
                created_by=system_user.id,
            )
        act_id = act.id

    await _show_act_card(callback, state, act_id)
    await callback.answer("Черновик создан")


@router.callback_query(ActCardActionCallback.filter(F.action == "add_line"))
async def show_available_work_entries(
    callback: CallbackQuery, callback_data: ActCardActionCallback, state: FSMContext
) -> None:
    async with session_factory() as session:
        act = await act_repo.get_or_raise(session, callback_data.act_id)

        if act.status != "draft":
            await callback.answer("Редактировать можно только черновик", show_alert=True)
            return

        candidates = await ca_service.list_available_for_project(session, act.project_id)
        options = []
        for entry, _summary in candidates:
            available = await act_service.available_volume_for_act(session, entry.id)
            if available > 0:
                options.append((entry, available))

    if not options:
        await callback.answer("Нет работ, доступных к включению", show_alert=True)
        return

    await state.set_state(ActStates.choosing_work_entry)
    await state.update_data(act_id=str(callback_data.act_id))
    await callback.message.edit_text(
        "Выберите работу для включения в акт:",
        reply_markup=available_work_entries_keyboard(callback_data.act_id, options),
    )
    await callback.answer()


@router.callback_query(ActStates.choosing_work_entry, ActWorkCallback.filter())
async def choose_work_entry(
    callback: CallbackQuery, callback_data: ActWorkCallback, state: FSMContext
) -> None:
    async with session_factory() as session:
        available = await act_service.available_volume_for_act(session, callback_data.work_entry_id)

    await state.update_data(
        act_id=str(callback_data.act_id),
        work_entry_id=str(callback_data.work_entry_id),
    )
    await state.set_state(ActStates.entering_quantity)
    await callback.message.edit_text(
        f"Доступно к включению: {available}\n\nВведите включаемый объём числом:",
    )
    await callback.answer()


@router.message(ActStates.entering_quantity)
async def enter_quantity(message: Message, state: FSMContext, system_user: User) -> None:
    raw = (message.text or "").strip().replace(",", ".")

    try:
        quantity = Decimal(raw)
    except InvalidOperation:
        await message.answer("Введите корректное число, например 12.5")
        return

    data = await state.get_data()
    act_id = uuid.UUID(data["act_id"])
    work_entry_id = uuid.UUID(data["work_entry_id"])

    async with session_factory() as session:
        async with session.begin():
            try:
                await act_service.add_line(
                    session,
                    act_id=act_id,
                    work_entry_id=work_entry_id,
                    quantity=quantity,
                    user_id=system_user.id,
                )
            except AppError as exc:
                await message.answer(f"⚠ {exc}\nВведите объём ещё раз:")
                return

    async with session_factory() as session:
        act = await act_repo.get_or_raise(session, act_id)

    await state.set_state(ActStates.viewing_act)
    await message.answer("Строка добавлена ✅")
    await message.answer(_act_card_text(act), reply_markup=act_card_keyboard(act))


@router.callback_query(ActCardActionCallback.filter(F.action == "lines"))
async def show_lines(
    callback: CallbackQuery, callback_data: ActCardActionCallback, state: FSMContext
) -> None:
    async with session_factory() as session:
        lines = await act_repo.list_lines(session, callback_data.act_id)

    if not lines:
        await callback.answer("В акте пока нет строк", show_alert=True)
        return

    await callback.message.edit_text(
        "Строки акта:",
        reply_markup=lines_keyboard(callback_data.act_id, lines),
    )
    await callback.answer()


@router.callback_query(ActLineCallback.filter())
async def line_card_or_delete(
    callback: CallbackQuery,
    callback_data: ActLineCallback,
    state: FSMContext,
    system_user: User,
) -> None:
    async with session_factory() as session:
        line = await act_repo.get_line(session, callback_data.line_id)

    if line is None:
        await callback.answer("Строка не найдена", show_alert=True)
        return

    data = await state.get_data()

    # First tap opens the line card; a second tap (from that card) deletes it.
    if data.get("viewing_line") == str(callback_data.line_id):
        await state.update_data(viewing_line=None)

        async with session_factory() as session:
            async with session.begin():
                try:
                    await act_service.remove_line(
                        session,
                        act_id=callback_data.act_id,
                        line_id=callback_data.line_id,
                        user_id=system_user.id,
                    )
                except AppError as exc:
                    await callback.answer(str(exc), show_alert=True)
                    return

        await callback.answer("Строка удалена")
        await show_lines(callback, ActCardActionCallback(act_id=callback_data.act_id, action="lines"), state)
        return

    await state.update_data(viewing_line=str(callback_data.line_id))
    await callback.message.edit_text(
        f"<b>{line.work_type_name}</b>\n"
        f"Объём: {line.accepted_volume}\n"
        f"Цена: {line.unit_price}\n"
        f"Сумма: {line.amount}\n"
        f"Место: {line.location_snapshot or '—'}\n\n"
        "Повторное нажатие «Удалить строку» удалит её из черновика.",
        reply_markup=line_card_keyboard(callback_data.act_id, callback_data.line_id),
    )
    await callback.answer()


@router.callback_query(ActCardActionCallback.filter(F.action == "finalize"))
async def finalize_act(
    callback: CallbackQuery, callback_data: ActCardActionCallback, state: FSMContext, system_user: User
) -> None:
    async with session_factory() as session:
        async with session.begin():
            try:
                await act_service.finalize(session, act_id=callback_data.act_id, user_id=system_user.id)
            except AppError as exc:
                await callback.answer(str(exc), show_alert=True)
                return

    await _show_act_card(callback, state, callback_data.act_id)
    await callback.answer("Акт завершён")


@router.callback_query(ActCardActionCallback.filter(F.action == "cancel"))
async def ask_cancel_reason(
    callback: CallbackQuery, callback_data: ActCardActionCallback, state: FSMContext
) -> None:
    await state.update_data(act_id=str(callback_data.act_id))
    await state.set_state(ActStates.entering_reason)
    await callback.message.edit_text("Укажите причину отмены акта:")
    await callback.answer()


@router.message(ActStates.entering_reason)
async def cancel_act_with_reason(message: Message, state: FSMContext, system_user: User) -> None:
    reason = (message.text or "").strip()
    data = await state.get_data()
    act_id = uuid.UUID(data["act_id"])

    async with session_factory() as session:
        async with session.begin():
            try:
                await act_service.cancel(session, act_id=act_id, reason=reason, user_id=system_user.id)
            except AppError as exc:
                await message.answer(f"⚠ {exc}\nУкажите причину ещё раз:")
                return

    async with session_factory() as session:
        act = await act_repo.get_or_raise(session, act_id)

    await state.set_state(ActStates.viewing_act)
    await message.answer("Акт отменён ⛔")
    await message.answer(_act_card_text(act), reply_markup=act_card_keyboard(act))


@router.callback_query(ActCardActionCallback.filter(F.action == "download"))
async def download_excel(
    callback: CallbackQuery, callback_data: ActCardActionCallback, state: FSMContext
) -> None:
    async with session_factory() as session:
        act = await act_repo.get_or_raise(session, callback_data.act_id)
        lines = await act_repo.list_lines(session, callback_data.act_id)
        project = await session.get(Project, act.project_id)
        contract = None
        if act.contract_id:
            from app.models.directories import Contract

            contract = await session.get(Contract, act.contract_id)

    file_path = generate_act_excel(act, lines, project, contract)
    try:
        await callback.message.answer_document(
            BufferedInputFile(file_path.read_bytes(), filename=file_path.name)
        )
    finally:
        file_path.unlink(missing_ok=True)

    await callback.answer()


@router.callback_query(ActCardActionCallback.filter(F.action == "back"))
async def back_to_list(callback: CallbackQuery, state: FSMContext) -> None:
    async with session_factory() as session:
        acts = await act_repo.list_acts(session)

    await state.set_state(ActStates.listing)
    await callback.message.edit_text("📄 <b>Акты</b>\n\nВыберите акт:", reply_markup=acts_list_keyboard(acts))
    await callback.answer()


@router.callback_query(ActNavCallback.filter(F.action == "cancel_flow"))
async def cancel_flow(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Действие отменено.")
    await callback.answer()
