"""Telegram forms only; validation, permissions and writes live in services."""
import uuid
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import directories as kb
from app.bot.keyboards.main import main_menu
from app.bot.middlewares.permissions import PermissionMiddleware
from app.bot.states.directories import DirectoryStates as States
from app.core.exceptions import ValidationError
from app.db.session import session_factory
from app.models import User
from app.schemas.directories import LABELS, fields, parse, wire
from app.services import catalog

router = Router(name="directories")
router.message.middleware(PermissionMiddleware("projects.view"))
router.callback_query.middleware(PermissionMiddleware("projects.view"))
PAGE_SIZE = 8


def identifier(value):
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("Некорректная кнопка записи; откройте список заново") from None


def page_number(value):
    try:
        page = int(value)
    except (ValueError, TypeError):
        raise ValidationError("Некорректная страница") from None
    if page < 0 or page > 100000:
        raise ValidationError("Некорректная страница")
    return page


async def render(event, text, markup):
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


async def token(state):
    value = uuid.uuid4().hex[:8]
    await state.update_data(nonce=value)
    return value


def field_value(field, value, references=None):
    if value is None:
        return "—"
    if field.relation:
        return (references or {}).get(str(value), "Запись недоступна")
    if field.kind == "bool":
        return "Да" if value else "Нет"
    if field.kind == "choice":
        return dict(field.choices).get(value, value)
    if field.kind == "date":
        return value.strftime("%d.%m.%Y") if hasattr(value, "strftime") else datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
    return str(value)


def summary(kind, values, labels):
    lines = [f"<b>{escape(LABELS[kind])}</b>"]
    for field in fields(kind):
        value = field_value(field, values.get(field.name), labels.get(field.name))
        # Keep cards/previews within Telegram message limits; stored values are not truncated.
        lines.append(f"{escape(field.label)}: {escape(value[:180])}{'…' if len(value) > 180 else ''}")
    return "\n".join(lines)


async def show_menu(event, state):
    await state.clear()
    await state.set_state(States.menu)
    await render(event, "<b>Объекты и справочники</b>\nВыберите раздел:", kb.main_menu())


@router.message(F.text == "🏗 Объекты")
async def open_section(message: Message, state: FSMContext, system_user: User):
    await show_menu(message, state)


async def show_list(event, state, user, *, page=0):
    data = await state.get_data()
    kind = data["kind"]
    async with session_factory() as session:
        rows, more = await catalog.list_page(session, kind, user_id=user.id, query=data.get("query", ""),
                                             archived=data.get("archived", False), page=page, size=PAGE_SIZE)
        labels = await catalog.reference_labels(session, kind, rows, user_id=user.id)
    choices = []
    for row in rows:
        title = catalog.title(kind, row)
        if kind == "rate":
            title = labels["work_type_id"].get(str(row.work_type_id), "Вид работы") + " · " + title
        choices.append((row.id, title))
    await state.set_state(States.listing)
    await state.update_data(page=page)
    nonce = await token(state)
    text = f"<b>{escape(LABELS[kind])}</b> · {'Архив' if data.get('archived') else 'Действующие'}"
    if data.get("query"):
        text += f"\nПоиск: {escape(data['query'])}"
    if not rows:
        text += "\nЗаписей не найдено."
    await render(event, text, kb.listing(choices, nonce=nonce, page=page, more=more, archived=data.get("archived", False)))


async def show_card(event, state, user, entity_id):
    data = await state.get_data()
    kind = data["kind"]
    async with session_factory() as session:
        row = await catalog.get(session, kind, entity_id, user_id=user.id)
        labels = await catalog.reference_labels(session, kind, [row], user_id=user.id)
        values = catalog.snapshot(kind, row)
        stamp = catalog.version(kind, row)
        created = getattr(row, "created_at", None)
    await state.set_state(States.card)
    await state.update_data(entity_id=str(row.id), expected_version=stamp, values=values, labels=labels)
    nonce = await token(state)
    text = summary(kind, values, labels) + f"\nАрхив: {'Да' if values['archived'] else 'Нет'}"
    if created:
        text += f"\nСоздано: {created.astimezone(ZoneInfo('Asia/Almaty')):%d.%m.%Y %H:%M}"
    await render(event, text, kb.card(nonce=nonce, archived=values["archived"], rate=kind == "rate"))


async def show_field(event, state, user, *, picker_page=0):
    data = await state.get_data()
    definition = fields(data["kind"])
    index = data.get("field_index", 0)
    if index >= len(definition):
        await state.set_state(States.confirming)
        nonce = await token(state)
        text = summary(data["kind"], data["draft"], data.get("labels", {}))
        if data["kind"] == "rate" and data.get("editing_id"):
            text += "\nБудет создана новая версия. Предыдущий период закончится накануне её начала."
        await render(event, text + "\n\nСохранить?", kb.confirm(nonce))
        return
    field = definition[index]
    current = data["draft"].get(field.name)
    nonce = await token(state)
    label = field_value(field, current, data.get("labels", {}).get(field.name))
    text = f"<b>{escape(LABELS[data['kind']])}</b> · шаг {index + 1}/{len(definition)}\n{escape(field.label)}"
    if current is not None:
        text += f"\nТекущее: {escape(label[:180])}"
    if field.relation:
        scope = {}
        if field.relation == "contract":
            raw = data["draft"].get("project_id")
            if raw is None:
                await state.set_state(States.editing)
                await render(event, text + "\nДля общей расценки договор не указывается. Нажмите «Пропустить».",
                             kb.field(field, nonce=nonce))
                return
            scope["project_id"] = uuid.UUID(raw)
        async with session_factory() as session:
            rows, more = await catalog.list_page(session, field.relation, user_id=user.id, scope=scope,
                query=data.get("picker_query", ""), page=picker_page, size=PAGE_SIZE)
        await state.set_state(States.picking)
        await state.update_data(picker_page=picker_page)
        if not rows:
            text += "\nНет подходящих записей. Создайте их в соответствующем справочнике."
        await render(event, text, kb.listing([(row.id, catalog.title(field.relation, row)) for row in rows],
            nonce=nonce, page=picker_page, more=more, archived=False, picker=True, optional=not field.required, has_value=current is not None))
    else:
        await state.set_state(States.editing)
        if field.kind == "date":
            text += "\nФормат: ДД.ММ.ГГГГ"
        elif field.kind == "money":
            text += "\nНеотрицательная сумма, не более двух знаков после запятой"
        if not field.required:
            text += "\n«-» — пропустить или очистить поле"
        await render(event, text, kb.field(field, nonce=nonce, has_value=current is not None))


async def accept_value(event, state, user, raw):
    data = await state.get_data()
    field = fields(data["kind"])[data["field_index"]]
    value = parse(field, raw)
    draft = dict(data["draft"])
    if (field.name == "project_id" and wire(value) != draft.get("project_id")
            and any(f.name == "contract_id" for f in fields(data["kind"]))):
        draft["contract_id"] = None
    draft[field.name] = wire(value)
    await state.update_data(draft=draft, field_index=data["field_index"] + 1, picker_query="")
    await show_field(event, state, user)


async def go_back(event, state, user):
    current = await state.get_state()
    data = await state.get_data()
    if current == States.searching_reference.state:
        await show_field(event, state, user)
    elif current in {States.editing.state, States.picking.state, States.confirming.state}:
        index = data.get("field_index", 0)
        if index > 0:
            await state.update_data(field_index=index - 1, picker_query="")
            await show_field(event, state, user)
        elif data.get("editing_id"):
            await show_card(event, state, user, uuid.UUID(data["editing_id"]))
        else:
            await show_list(event, state, user)
    elif current == States.confirming_archive.state:
        await show_card(event, state, user, uuid.UUID(data["entity_id"]))
    elif current in {States.card.state, States.searching.state}:
        await show_list(event, state, user, page=data.get("page", 0))
    else:
        await show_menu(event, state)


async def cancel(event, state):
    await state.clear()
    if isinstance(event, CallbackQuery):
        await event.message.edit_text("Действие отменено.")
        await event.message.answer("Главное меню", reply_markup=main_menu())
    else:
        await event.answer("Действие отменено.", reply_markup=main_menu())


@router.callback_query(kb.DirectoryCallback.filter())
async def handle_action(callback: CallbackQuery, callback_data: kb.DirectoryCallback, state: FSMContext, system_user: User):
    action, value = callback_data.action, callback_data.value
    data = await state.get_data()
    current = await state.get_state()
    if action == "category":
        fields(value)
        await state.clear()
        await state.update_data(kind=value, query="", archived=False)
        await show_list(callback, state, system_user)
    elif action == "main":
        await cancel(callback, state)
    else:
        if not data.get("nonce") or data["nonce"] != callback_data.nonce:
            raise ValidationError("Кнопка устарела. Откройте раздел заново")
        if action == "cancel":
            await cancel(callback, state)
        elif action == "back":
            await go_back(callback, state, system_user)
        elif action in {"page", "toggle", "search", "new", "open"}:
            if current != States.listing.state:
                raise ValidationError("Сначала откройте список")
            if action == "page":
                await show_list(callback, state, system_user, page=page_number(value))
            elif action == "toggle":
                await state.update_data(archived=not data.get("archived", False))
                await show_list(callback, state, system_user)
            elif action == "search":
                await state.set_state(States.searching)
                await render(callback, "Введите название, код или номер:", kb.back_cancel(await token(state)))
            elif action == "open":
                await show_card(callback, state, system_user, identifier(value))
            else:
                async with session_factory() as session:
                    await catalog.require_change(session, system_user.id)
                defaults = {"status": "draft"} if data["kind"] in {"project", "contract"} else {}
                if data["kind"] == "rate":
                    defaults["is_active"] = True
                await state.update_data(draft=defaults, labels={}, field_index=0, editing_id=None,
                    expected_version=None, idempotency_key=str(uuid.uuid4()), picker_query="")
                await show_field(callback, state, system_user)
        elif action == "edit":
            if current != States.card.state:
                raise ValidationError("Откройте карточку")
            async with session_factory() as session:
                await catalog.require_change(session, system_user.id)
            draft = {f.name: data["values"].get(f.name) for f in fields(data["kind"])}
            if data["kind"] == "rate":
                draft["valid_from"] = None
            await state.update_data(draft=draft, field_index=0, editing_id=data["entity_id"],
                                    idempotency_key=str(uuid.uuid4()), picker_query="")
            await show_field(callback, state, system_user)
        elif action in {"archive", "restore"}:
            if current != States.card.state:
                raise ValidationError("Откройте карточку")
            async with session_factory() as session:
                await catalog.require_change(session, system_user.id)
            await state.update_data(archive_target=action == "archive", idempotency_key=str(uuid.uuid4()))
            await state.set_state(States.confirming_archive)
            explanation = "Восстановить запись?" if action == "restore" else "Перенести запись в архив? История и связанные операции сохранятся."
            if action == "restore" and data["kind"] == "contract":
                explanation += " Договор будет восстановлен в статусе «Черновик»."
            await render(callback, explanation, kb.confirm(await token(state), archive=True))
        elif action in {"save", "save_archive"}:
            expected = States.confirming.state if action == "save" else States.confirming_archive.state
            if current != expected:
                raise ValidationError("Сначала подтвердите данные")
            async with session_factory() as session:
                async with session.begin():
                    if action == "save":
                        row = await catalog.save(session, data["kind"], data["draft"], user_id=system_user.id,
                            idempotency_key=uuid.UUID(data["idempotency_key"]),
                            entity_id=uuid.UUID(data["editing_id"]) if data.get("editing_id") else None,
                            expected_version=data.get("expected_version"))
                    else:
                        row = await catalog.set_archived(session, data["kind"], uuid.UUID(data["entity_id"]),
                            data["archive_target"], user_id=system_user.id, idempotency_key=uuid.UUID(data["idempotency_key"]),
                            expected_version=data["expected_version"])
                    record_id = row.id
            await show_card(callback, state, system_user, record_id)
            await callback.answer(f"Сохранено: {record_id}")
            return
        elif action in {"pick", "pickpage", "picksearch", "keep", "skip", "option"}:
            if current not in {States.editing.state, States.picking.state}:
                raise ValidationError("Форма устарела")
            field = fields(data["kind"])[data["field_index"]]
            if action == "pickpage":
                await show_field(callback, state, system_user, picker_page=page_number(value))
            elif action == "picksearch":
                await state.set_state(States.searching_reference)
                await render(callback, "Введите название или код для поиска:", kb.back_cancel(await token(state)))
            elif action == "pick":
                if not field.relation:
                    raise ValidationError("Выбор записи сейчас недоступен")
                async with session_factory() as session:
                    parent = await catalog.get(session, field.relation, identifier(value), user_id=system_user.id)
                if field.relation == "contract" and str(parent.project_id) != data["draft"].get("project_id"):
                    raise ValidationError("Договор не принадлежит выбранному объекту")
                labels = data.get("labels", {})
                labels[field.name] = {str(parent.id): catalog.title(field.relation, parent)}
                await state.update_data(labels=labels)
                await accept_value(callback, state, system_user, parent.id)
            elif action == "keep":
                await accept_value(callback, state, system_user, data["draft"].get(field.name))
            elif action == "skip":
                await accept_value(callback, state, system_user, None)
            else:
                if not field.choices:
                    raise ValidationError("Используйте текстовый ввод")
                await accept_value(callback, state, system_user, value)
        elif action == "clearsearch":
            if current == States.picking.state:
                await state.update_data(picker_query="")
                await show_field(callback, state, system_user)
            elif current == States.listing.state:
                await state.update_data(query="")
                await show_list(callback, state, system_user)
            else:
                raise ValidationError("Откройте список")
        else:
            raise ValidationError("Неизвестное действие")
    await callback.answer()


@router.message(States.searching)
@router.message(States.searching_reference)
async def search_text(message: Message, state: FSMContext, system_user: User):
    query = (message.text or "").strip()
    if not query or len(query) > 100:
        raise ValidationError("Введите от 1 до 100 символов")
    if await state.get_state() == States.searching_reference.state:
        await state.update_data(picker_query=query)
        await show_field(message, state, system_user)
    else:
        await state.update_data(query=query)
        await show_list(message, state, system_user)


@router.message(States.editing)
async def field_text(message: Message, state: FSMContext, system_user: User):
    data = await state.get_data()
    field = fields(data["kind"])[data["field_index"]]
    if field.relation or field.choices:
        raise ValidationError("Используйте кнопки выбора")
    if message.text is None:
        raise ValidationError("Введите текст или используйте кнопку «Пропустить»")
    await accept_value(message, state, system_user, message.text)


@router.message(States.picking,)
@router.message(States.confirming)
@router.message(States.confirming_archive)
async def use_buttons(message: Message):
    await message.answer("Используйте кнопки текущей формы; /menu — главное меню.")
