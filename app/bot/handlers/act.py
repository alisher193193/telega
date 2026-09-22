import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from html import escape
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from app.bot.keyboards.act import (
    ActCardActionCallback, ActContractCallback, ActLineCallback, ActNavCallback,
    ActOpenCallback, ActProjectCallback, ActWorkCallback, ActPageCallback,
    act_card_keyboard, acts_list_keyboard, available_work_entries_keyboard,
    contracts_keyboard, line_card_keyboard, lines_keyboard, projects_keyboard,
    back_keyboard, confirmation_keyboard,
)
from app.bot.keyboards.main import BillingMenuCallback
from app.bot.states.act import ActStates
from app.bot.middlewares.permissions import PermissionMiddleware
from app.core.exceptions import ValidationError
from app.core.numbers import volume
from app.db.repositories import act as act_repo
from app.db.repositories.directories import list_active_projects, list_contracts_for_project
from app.db.session import session_factory
from app.models import Project, User
from app.reports.act_excel import temporary_act_excel
from app.services import act as act_service

router = Router(name="acts")
router.message.middleware(PermissionMiddleware("acts.manage"))
router.callback_query.middleware(PermissionMiddleware("acts.manage"))
PAGE_SIZE = 10


def _act_card_text(act):
    return (f"<b>Акт №{escape(act.act_number)}</b> от {act.act_date:%d.%m.%Y}\n"
            f"Статус: {escape(act.status)}\nСумма: {act.total_amount}\n"
            + (f"Причина отмены: {escape(act.cancellation_reason)}\n" if act.cancellation_reason else ""))


async def _show_act_card(callback, state, act_id):
    async with session_factory() as session:
        act = await act_repo.get_or_raise(session, act_id)
    await state.set_state(ActStates.viewing_act)
    await state.update_data(act_id=str(act_id))
    await callback.message.edit_text(_act_card_text(act), reply_markup=act_card_keyboard(act))


async def _page(callback, state, kind, page, user):
    if page < 0 or page > 100000:
        raise ValidationError("Некорректная страница")
    data = await state.get_data()
    options = dict(limit=PAGE_SIZE + 1, offset=page * PAGE_SIZE)
    async with session_factory() as session:
        if kind == "acts":
            rows = await act_repo.list_acts(session, **options)
            keyboard, status, title = acts_list_keyboard, ActStates.listing, "📄 Акты"
        elif kind == "projects":
            rows = await list_active_projects(session, **options)
            keyboard, status, title = projects_keyboard, ActStates.choosing_project, "Выберите объект"
        elif kind == "contracts":
            rows = await list_contracts_for_project(session, uuid.UUID(data["project_id"]), **options)
            keyboard, status, title = contracts_keyboard, ActStates.choosing_contract, "Выберите договор"
        elif kind == "works":
            aid = uuid.UUID(data["act_id"])
            rows = await act_service.list_available_work(session, aid, user_id=user.id, **options)
            keyboard = lambda items, **kw: available_work_entries_keyboard(aid, items, **kw)
            status, title = ActStates.choosing_work_entry, "Выберите работу для акта"
        elif kind == "lines":
            aid = uuid.UUID(data["act_id"])
            rows = await act_repo.list_lines(session, aid, **options)
            keyboard = lambda items, **kw: lines_keyboard(aid, items, **kw)
            status, title = ActStates.viewing_lines, "Строки акта"
        else:
            raise ValidationError("Неизвестный список")
    await state.set_state(status)
    await state.update_data(page=page)
    await callback.message.edit_text(title, reply_markup=keyboard(rows[:PAGE_SIZE], page=page, more=len(rows) > PAGE_SIZE))


@router.callback_query(BillingMenuCallback.filter(F.action == "acts"), flags={"permission": "acts.view"})
async def start_acts(callback: CallbackQuery, state: FSMContext, system_user: User):
    await state.clear()
    await _page(callback, state, "acts", 0, system_user)
    await callback.answer()


@router.callback_query(ActPageCallback.filter(), flags={"permission": "acts.view"})
async def page_list(callback: CallbackQuery, callback_data: ActPageCallback, state: FSMContext, system_user: User):
    expected = {"acts": ActStates.listing, "projects": ActStates.choosing_project,
                "contracts": ActStates.choosing_contract, "works": ActStates.choosing_work_entry,
                "lines": ActStates.viewing_lines}
    if callback_data.kind not in expected or await state.get_state() != expected[callback_data.kind].state:
        raise ValidationError("Эта кнопка устарела; откройте список заново")
    await _page(callback, state, callback_data.kind, callback_data.page, system_user)
    await callback.answer()


@router.callback_query(ActStates.listing, ActOpenCallback.filter(), flags={"permission": "acts.view"})
async def open_act(callback: CallbackQuery, callback_data: ActOpenCallback, state: FSMContext):
    await _show_act_card(callback, state, callback_data.act_id)
    await callback.answer()


@router.callback_query(ActNavCallback.filter(F.action == "new"))
async def new_act_choose_project(callback: CallbackQuery, state: FSMContext, system_user: User):
    await state.clear()
    await _page(callback, state, "projects", 0, system_user)
    await callback.answer()


@router.callback_query(ActStates.choosing_project, ActProjectCallback.filter())
async def choose_project(callback: CallbackQuery, callback_data: ActProjectCallback, state: FSMContext, system_user: User):
    await state.update_data(project_id=str(callback_data.project_id))
    await _page(callback, state, "contracts", 0, system_user)
    await callback.answer()


@router.callback_query(ActStates.choosing_contract, ActContractCallback.filter())
async def choose_contract(callback: CallbackQuery, callback_data: ActContractCallback, state: FSMContext, system_user: User):
    data = await state.get_data()
    project_id = uuid.UUID(data["project_id"])
    try:
        contract_id = None if callback_data.contract_id == "none" else uuid.UUID(callback_data.contract_id)
    except ValueError:
        raise ValidationError("Некорректный договор") from None
    today = datetime.now(ZoneInfo("Asia/Almaty")).date()
    async with session_factory() as session:
        async with session.begin():
            project = await session.get(Project, project_id)
            if project is None:
                raise ValidationError("Объект не найден")
            act = await act_service.create_draft(session, project_id=project_id, contract_id=contract_id,
                act_number=f"{today:%Y%m%d}-{uuid.uuid4().hex}", act_date=today, created_by=system_user.id)
        act_id = act.id
    await _show_act_card(callback, state, act_id)
    await callback.answer("Черновик создан")


@router.callback_query(ActCardActionCallback.filter(F.action == "add_line"))
async def show_available_work_entries(callback: CallbackQuery, callback_data: ActCardActionCallback, state: FSMContext, system_user: User):
    await state.update_data(act_id=str(callback_data.act_id))
    await _page(callback, state, "works", 0, system_user)
    await callback.answer()


@router.callback_query(ActStates.choosing_work_entry, ActWorkCallback.filter())
async def choose_work_entry(callback: CallbackQuery, callback_data: ActWorkCallback, state: FSMContext):
    await state.update_data(work_entry_id=str(callback_data.work_entry_id), idempotency_key=str(uuid.uuid4()))
    await state.set_state(ActStates.entering_quantity)
    await callback.message.edit_text("Введите объём для включения в акт:", reply_markup=back_keyboard())
    await callback.answer()


@router.message(ActStates.entering_quantity)
async def enter_quantity(message: Message, state: FSMContext):
    try:
        quantity = volume(Decimal((message.text or "").strip().replace(",", ".")))
    except InvalidOperation:
        raise ValidationError("Введите корректное число") from None
    if quantity <= 0:
        raise ValidationError("Объём должен быть больше нуля")
    await state.update_data(quantity=str(quantity))
    await state.set_state(ActStates.confirming_line)
    await message.answer(f"Добавить в акт объём {quantity}?", reply_markup=confirmation_keyboard())


@router.callback_query(ActStates.confirming_line, ActNavCallback.filter(F.action == "save_line"))
async def confirm_line(callback: CallbackQuery, state: FSMContext, system_user: User):
    data = await state.get_data()
    if not all(k in data for k in ("act_id", "work_entry_id", "quantity", "idempotency_key")):
        raise ValidationError("Форма устарела; откройте акт заново")
    aid = uuid.UUID(data["act_id"])
    async with session_factory() as session:
        async with session.begin():
            line = await act_service.add_line(session, act_id=aid, work_entry_id=uuid.UUID(data["work_entry_id"]),
                quantity=Decimal(data["quantity"]), idempotency_key=uuid.UUID(data["idempotency_key"]), user_id=system_user.id)
    await _show_act_card(callback, state, aid)
    await callback.answer(f"Строка сохранена: {line.id}")


@router.callback_query(ActCardActionCallback.filter(F.action == "lines"), flags={"permission": "acts.view"})
async def show_lines(callback: CallbackQuery, callback_data: ActCardActionCallback, state: FSMContext, system_user: User):
    await state.update_data(act_id=str(callback_data.act_id))
    await _page(callback, state, "lines", 0, system_user)
    await callback.answer()


@router.callback_query(ActStates.viewing_lines, ActLineCallback.filter(F.action == "open"), flags={"permission": "acts.view"})
async def line_card(callback: CallbackQuery, callback_data: ActLineCallback, state: FSMContext):
    data = await state.get_data()
    async with session_factory() as session:
        line = await act_repo.get_line(session, callback_data.line_id)
        if line is None or str(line.act_id) != data.get("act_id") or line.cancelled_at is not None:
            raise ValidationError("Строка не найдена в текущем акте")
    await state.update_data(line_id=str(line.id))
    await state.set_state(ActStates.viewing_line)
    await callback.message.edit_text(f"{escape(line.work_type_name)}\nОбъём: {line.accepted_volume}\nСумма: {line.amount}",
                                    reply_markup=line_card_keyboard(line.act_id, line.id))
    await callback.answer()


@router.callback_query(ActStates.viewing_line, ActLineCallback.filter(F.action == "cancel"))
async def ask_line_reason(callback: CallbackQuery, callback_data: ActLineCallback, state: FSMContext):
    data = await state.get_data()
    if data.get("line_id") != str(callback_data.line_id):
        raise ValidationError("Эта кнопка устарела")
    await state.set_state(ActStates.entering_line_reason)
    await callback.message.edit_text("Укажите причину отмены строки:", reply_markup=back_keyboard())
    await callback.answer()


@router.message(ActStates.entering_line_reason)
async def cancel_line(message: Message, state: FSMContext, system_user: User):
    data = await state.get_data()
    async with session_factory() as session:
        async with session.begin():
            await act_service.remove_line(session, act_id=uuid.UUID(data["act_id"]), line_id=uuid.UUID(data["line_id"]),
                                          reason=(message.text or "").strip(), user_id=system_user.id)
    await state.set_state(ActStates.viewing_act)
    await message.answer(f"Строка {data['line_id']} отменена", reply_markup=back_keyboard())


@router.callback_query(ActCardActionCallback.filter(F.action == "finalize"))
async def finalize_act(callback: CallbackQuery, callback_data: ActCardActionCallback, state: FSMContext, system_user: User):
    async with session_factory() as session:
        async with session.begin():
            await act_service.finalize(session, act_id=callback_data.act_id, user_id=system_user.id)
    await _show_act_card(callback, state, callback_data.act_id)
    await callback.answer("Акт завершён")


@router.callback_query(ActCardActionCallback.filter(F.action == "cancel"))
async def ask_cancel_reason(callback: CallbackQuery, callback_data: ActCardActionCallback, state: FSMContext):
    await state.update_data(act_id=str(callback_data.act_id))
    await state.set_state(ActStates.entering_reason)
    await callback.message.edit_text("Укажите причину отмены акта:", reply_markup=back_keyboard())
    await callback.answer()


@router.message(ActStates.entering_reason)
async def cancel_act_with_reason(message: Message, state: FSMContext, system_user: User):
    data = await state.get_data()
    async with session_factory() as session:
        async with session.begin():
            act = await act_service.cancel(session, act_id=uuid.UUID(data["act_id"]), reason=(message.text or "").strip(), user_id=system_user.id)
    await state.set_state(ActStates.viewing_act)
    await message.answer(_act_card_text(act), reply_markup=act_card_keyboard(act))


@router.callback_query(ActCardActionCallback.filter(F.action == "download"), flags={"permission": "acts.view"})
async def download_excel(callback: CallbackQuery, callback_data: ActCardActionCallback, system_user: User):
    async with session_factory() as session:
        async with session.begin():
            values = await act_service.prepare_export(session, act_id=callback_data.act_id, user_id=system_user.id)
            with temporary_act_excel(*values) as path:
                document = BufferedInputFile(path.read_bytes(), filename=f"act_{callback_data.act_id.hex}.xlsx")
    # Disk file has already been removed, including when Telegram delivery fails.
    await callback.message.answer_document(document)
    await callback.answer()


@router.callback_query(ActCardActionCallback.filter(F.action == "back"), flags={"permission": "acts.view"})
async def back_to_list(callback: CallbackQuery, state: FSMContext, system_user: User):
    await _page(callback, state, "acts", 0, system_user)
    await callback.answer()


@router.callback_query(ActNavCallback.filter(F.action == "back"), flags={"permission": "acts.view"})
async def go_back(callback: CallbackQuery, state: FSMContext, system_user: User):
    current = await state.get_state()
    data = await state.get_data()
    if current == ActStates.confirming_line.state:
        await state.set_state(ActStates.entering_quantity)
        await callback.message.edit_text("Введите объём:", reply_markup=back_keyboard())
    elif current == ActStates.entering_quantity.state:
        await _page(callback, state, "works", 0, system_user)
    elif current == ActStates.choosing_contract.state:
        await _page(callback, state, "projects", 0, system_user)
    elif current in {ActStates.viewing_line.state, ActStates.entering_line_reason.state}:
        await _page(callback, state, "lines", 0, system_user)
    elif data.get("act_id") and current != ActStates.choosing_project.state:
        await _show_act_card(callback, state, uuid.UUID(data["act_id"]))
    else:
        await _page(callback, state, "acts", 0, system_user)
    await callback.answer()


@router.callback_query(ActNavCallback.filter(F.action == "cancel_flow"), flags={"permission": "acts.view"})
async def cancel_flow(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Действие отменено.")
    await callback.answer()
