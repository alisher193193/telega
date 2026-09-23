"""Telegram presentation and FSM orchestration; services own business rules."""
import uuid
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

from aiogram import BaseMiddleware, F, Router
from aiogram.types import CallbackQuery, Message
from app.bot.keyboards.people import PeopleCallback, keyboard, pages
from app.bot.keyboards.main import main_menu
from app.bot.states.people import PeopleStates as States
from app.bot.handlers.directories import identifier, page_number
from app.core.exceptions import AppError, AccessDeniedError, ValidationError
from app.core.operations import operation
from app.db.session import session_factory
from app.schemas.people import LABELS, PAYMENTS, fields, parse, wire
from app.services import people

router = Router(name="people")


class PeopleErrors(BaseMiddleware):
    @operation
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except AppError as exc:
            if isinstance(event, CallbackQuery):
                await event.answer(str(exc), show_alert=True)
            else:
                await event.answer(str(exc), parse_mode=None)


router.message.middleware(PeopleErrors())
router.callback_query.middleware(PeopleErrors())


def safe(value, limit=300):
    text = str(value if value is not None else "—")
    return escape(text[:limit]) + ("…" if len(text) > limit else "")


def stamp(value):
    if not value:
        return "—"
    value = str(value)
    if "T" not in value and " " not in value:
        return value  # Legacy calendar date, not an invented timestamp.
    return datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Almaty")).strftime("%d.%m.%Y %H:%M")


async def render(event, state, text, items, *, controls=True):
    nonce = uuid.uuid4().hex[:8]
    await state.update_data(nonce=nonce)
    markup = keyboard(items, nonce, controls=controls)
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)


async def caps(user):
    async with session_factory() as session:
        return await people.capabilities(session, user.id)


async def open_section(event, state, system_user):
    permissions = await caps(system_user)
    items = [(label, "category", kind) for kind, label in LABELS.items() if f"{kind}.view" in permissions]
    if "worker.view" in permissions:
        items.append(("🔍 Поиск человека", "find", ""))
    if not items:
        raise AccessDeniedError("Нет прав на просмотр раздела «Люди»")
    await state.clear()
    await state.set_state(States.menu)
    items.append(("◀️ Назад", "home", ""))
    await render(event, state, "<b>👥 Люди</b>", items, controls=False)


@router.message(F.text == "👥 Люди")
async def entry(message: Message, state, system_user):
    await open_section(message, state, system_user)


async def show_list(event, state, user, page=0):
    data = await state.get_data()
    kind = data["kind"]
    async with session_factory() as session:
        rows, more = await people.list_page(session, kind, user_id=user.id, page=page,
            query=data.get("query", ""), status=data.get("status", "active"),
            project_id=identifier(data["project_filter"]) if data.get("project_filter") else None)
        permissions = await people.capabilities(session, user.id)
    items = [(getattr(row, "full_name", None) or row.name, "open", row.id.hex) for row in rows]
    pages(items, page, more)
    items += [("🔍 Поиск", "search", ""), ("Сбросить поиск", "clear", ""),
              ("Работающие / уволенные" if kind == "worker" else "Действующие / архив", "toggle", "")]
    if kind == "worker":
        items.append(("Фильтр по объекту", "filter", ""))
        if data.get("project_filter"):
            items.append(("Все объекты", "unfilter", ""))
    if f"{kind}.manage" in permissions:
        items.append(("➕ Добавить", "new", ""))
    await state.set_state(States.listing)
    await state.update_data(page=page)
    text = f"<b>{LABELS[kind]}</b> · {'Уволенные / архив' if data.get('status') == 'inactive' else 'Действующие'}"
    if data.get("query"):
        text += "\nПоиск: " + safe(data["query"])
    if data.get("project_filter"):
        text += "\nОбъект: " + safe(data.get("project_filter_label"))
    if not rows:
        text += "\nЗаписей не найдено."
    await render(event, state, text, items)


def summary(kind, values, labels):
    lines = [f"<b>{LABELS[kind]}</b>"]
    for field in fields(kind):
        value = values.get(field.name)
        if field.relation:
            value = labels.get(field.name, "Без объекта" if field.name == "current_project_id" and not value else "Не указано")
        elif field.name == "payment_type":
            value = dict(PAYMENTS).get(value, value)
        lines.append(f"{field.label}: {safe(value)}")
    return "\n".join(lines)


async def show_card(event, state, user, entity_id, *, saved=False):
    data = await state.get_data()
    kind = data["kind"]
    async with session_factory() as session:
        detail = await people.detail(session, kind, entity_id, user_id=user.id)
        permissions = await people.capabilities(session, user.id)
        if kind == "crew":
            active_members, more_active = await people.members(session, entity_id, user_id=user.id)
            ended_members, more_ended = await people.members(session, entity_id, user_id=user.id, ended=True)
    labels = {"specialty_id": detail.get("specialty_label"), "current_project_id": detail.get("project_label")}
    text = summary(kind, detail, labels)
    if kind == "worker":
        status = {"working": "Работает", "terminated": "Уволен", "on_leave": "Временно не работает"}.get(detail["status"], detail["status"])
        text += f"\nСтатус: {safe(status)}\nБригада: {safe(detail['crew_label'])}"
        text += "\nДата увольнения: " + safe(stamp(detail.get("terminated_at") or detail.get("termination_date")))
        text += "\n\nФинансовые показатели будут подключены на этапе кассы и начислений."
    else:
        text += "\nСтатус: " + ("Архив" if detail["archived"] else "Действует")
    text += "\nСоздано: " + safe(stamp(detail["created_at"]))
    items = []
    if f"{kind}.manage" in permissions:
        if not detail["archived"]:
            items.append(("✏️ Редактировать", "edit", ""))
        items.append(("Восстановить" if detail["archived"] else "Уволить" if kind == "worker" else "Архивировать", "status", ""))
    if kind == "crew":
        text += "\n\n<b>Действующие участники</b>"
        for member, name in active_members:
            text += f"\n{safe(name, 80)} · с {safe(stamp(member.joined_on or member.joined_at))}"
        if not active_members:
            text += "\nНет."
        elif more_active:
            text += "\nПродолжение — в списке участников."
        text += "\n\n<b>Завершённые участия</b>"
        for member, name in ended_members[:3]:
            text += f"\n{safe(name, 80)} · {safe(stamp(member.joined_on or member.joined_at))} — {safe(stamp(member.left_on or member.left_at))}"
        if not ended_members:
            text += "\nНет."
        elif more_ended or len(ended_members) > 3:
            text += "\nПродолжение — в истории участия."
        items += [("Действующие участники", "members", "active"), ("Завершённые участия", "members", "ended")]
        if not detail["archived"] and "crew.manage" in permissions:
            items.append(("Добавить участника", "join", ""))
    if saved:
        text = "✅ Сохранено\n" + text
        items.append(("Открыть карточку", "refresh", ""))
        if f"{kind}.manage" in permissions:
            items.append(("Добавить ещё", "new", ""))
    items.append(("Вернуться к списку", "list", ""))
    await state.set_state(States.card)
    await state.update_data(entity_id=str(entity_id), old=detail, labels=labels)
    await render(event, state, text, items)


async def form(event, state, user):
    data = await state.get_data()
    definition = fields(data["kind"])
    index = data["index"]
    if index == len(definition):
        await state.set_state(States.confirming)
        text = summary(data["kind"], data["draft"], data.get("draft_labels", {}))
        if data.get("editing"):
            old = data["old"]
            text = "<b>До изменения</b>\n" + summary(data["kind"], old, data.get("labels", {})) + "\n\n<b>После изменения</b>\n" + text
        await render(event, state, text + "\n\nПодтвердите сохранение.", [("✅ Сохранить", "save", ""), ("✏️ Исправить", "correct", "")])
        return
    field = definition[index]
    if field.relation:
        await state.update_data(purpose="form", relation=field.relation, picker_query="")
        await picker(event, state, user)
        return
    await state.set_state(States.editing)
    items = [(label, "option", value) for value, label in field.choices]
    if field.name in data["draft"]:
        items.append(("Оставить текущее", "keep", ""))
    text = f"<b>{LABELS[data['kind']]}</b> · {index + 1}/{len(definition)}\n{field.label}"
    if field.name in data["draft"]:
        text += "\nТекущее: " + safe(data["draft"][field.name])
    await render(event, state, text, items)


async def picker(event, state, user, page=0):
    data = await state.get_data()
    async with session_factory() as session:
        rows, more = await people.choices(session, data["relation"], user_id=user.id,
            purpose=data["purpose"], query=data.get("picker_query", ""), page=page)
    items = [(getattr(row, "full_name", None) or row.name, "pick", row.id.hex) for row in rows]
    pages(items, page, more)
    items.append(("🔍 Поиск", "picksearch", ""))
    if data["purpose"] == "form":
        field = fields(data["kind"])[data["index"]]
        if not field.required:
            items.append(("Без объекта", "skip", ""))
        if data["draft"].get(field.name):
            items.append(("Оставить текущее", "keep", ""))
    await state.set_state(States.picking)
    await state.update_data(picker_page=page)
    title = {"specialty": "Выберите специальность", "project": "Выберите объект", "worker": "Выберите работника"}[data["relation"]]
    if not rows:
        title += "\nЗаписей нет. Сначала создайте нужную запись в соответствующем разделе."
    await render(event, state, title, items)


async def accept(event, state, user, raw, label=None):
    data = await state.get_data()
    field = fields(data["kind"])[data["index"]]
    draft = dict(data["draft"])
    draft[field.name] = wire(parse(field, raw))
    labels = dict(data.get("draft_labels", {}))
    if field.relation and label is not None:
        labels[field.name] = label
    await state.update_data(draft=draft, draft_labels=labels, index=data["index"] + 1)
    await form(event, state, user)


async def show_members(event, state, user, page=0):
    data = await state.get_data()
    async with session_factory() as session:
        rows, more = await people.members(session, identifier(data["entity_id"]), user_id=user.id,
                                          ended=data.get("ended", False), page=page)
        permissions = await people.capabilities(session, user.id)
    text = "<b>Завершённые участия</b>" if data.get("ended") else "<b>Действующие участники</b>"
    items = []
    # IDs of rows on this page stay in FSM; callback carries only one membership ID.
    members = {}
    for member, name in rows:
        text += f"\n{safe(name, 150)} · с {safe(stamp(member.joined_on or member.joined_at))}"
        if member.left_at:
            text += " по " + safe(stamp(member.left_on or member.left_at))
        elif "crew.manage" in permissions:
            items.append((f"Завершить: {name}", "leave", member.id.hex))
        members[member.id.hex] = {"worker_id": str(member.worker_id), "name": name}
    if not rows:
        text += "\nУчастий нет."
    pages(items, page, more)
    await state.set_state(States.members)
    await state.update_data(member_rows=members, member_page=page)
    await render(event, state, text, items)


async def back(event, state, user):
    data = await state.get_data()
    current = await state.get_state()
    if current == States.picker_search.state:
        await picker(event, state, user)
    elif current in {States.editing.state, States.confirming.state, States.picking.state} and data.get("purpose") not in {"filter", "member"}:
        if data.get("index", 0) > 0:
            await state.update_data(index=data["index"] - 1)
            await form(event, state, user)
        elif data.get("editing"):
            await show_card(event, state, user, identifier(data["entity_id"]))
        else:
            await show_list(event, state, user)
    elif current == States.picking.state and data.get("purpose") == "filter":
        await show_list(event, state, user)
    elif current in {States.reason.state, States.status_confirm.state, States.members.state, States.member_confirm.state, States.picking.state}:
        await show_card(event, state, user, identifier(data["entity_id"]))
    elif current in {States.card.state, States.searching.state}:
        await show_list(event, state, user)
    else:
        await open_section(event, state, user)


async def cancel(event, state):
    await state.clear()
    message = event.message if isinstance(event, CallbackQuery) else event
    if isinstance(event, CallbackQuery):
        await message.edit_text("Действие завершено или отменено.")
    await message.answer("Главное меню", reply_markup=main_menu())


async def confirm_status(event, state):
    data = await state.get_data()
    await state.set_state(States.status_confirm)
    verb = "Восстановить" if data["old"]["archived"] else "Уволить" if data["kind"] == "worker" else "Архивировать"
    text = verb + " запись?\n" + safe(data["old"].get("full_name") or data["old"].get("name"))
    if not data["old"]["archived"] and data["kind"] in {"worker", "crew"}:
        text += "\nТекущие участия будут завершены. История сохранится."
    if data.get("reason"):
        text += "\nПричина: " + safe(data["reason"])
    await render(event, state, text, [("✅ Подтвердить", "savestatus", "")])


@router.callback_query(PeopleCallback.filter())
async def action(callback: CallbackQuery, callback_data: PeopleCallback, state, system_user):
    data = await state.get_data()
    current = await state.get_state()
    act, value = callback_data.action, callback_data.value
    if not data.get("nonce") or callback_data.nonce != data["nonce"]:
        raise ValidationError("Кнопка устарела. Откройте раздел «Люди» заново")
    if act in {"home", "cancel"}:
        await cancel(callback, state)
        await callback.answer()
        return
    if act in {"category", "find"}:
        if current != States.menu.state:
            raise ValidationError("Откройте меню «Люди»")
        kind = "worker" if act == "find" else value
        async with session_factory() as session:
            await people.require(session, kind, system_user.id)
        await state.update_data(kind=kind, query="", status="active", project_filter=None)
        if act == "find":
            await state.set_state(States.searching)
            await render(callback, state, "Введите ФИО:", [])
        else:
            await show_list(callback, state, system_user)
        await callback.answer()
        return
    kind = data.get("kind")
    async with session_factory() as session:
        await people.require(session, kind, system_user.id)
        if act in {"new", "edit", "save", "status", "savestatus", "join", "leave", "savemember", "correct"}:
            await people.require(session, kind, system_user.id, "manage")
    if act == "back":
        await back(callback, state, system_user)
    elif act == "page":
        page = page_number(value)
        if current == States.listing.state:
            await show_list(callback, state, system_user, page)
        elif current == States.picking.state:
            await picker(callback, state, system_user, page)
        elif current == States.members.state:
            await show_members(callback, state, system_user, page)
        else:
            raise ValidationError("Откройте список")
    elif act in {"search", "toggle", "clear", "filter", "unfilter", "open"}:
        if current != States.listing.state:
            raise ValidationError("Откройте список")
        if act == "search":
            await state.set_state(States.searching)
            await render(callback, state, "Введите ФИО или название:", [])
        elif act == "open":
            await show_card(callback, state, system_user, identifier(value))
        elif act == "filter":
            if kind != "worker":
                raise ValidationError("Фильтр доступен только работникам")
            await state.update_data(purpose="filter", relation="project", picker_query="")
            await picker(callback, state, system_user)
        else:
            changes = {"query": ""} if act == "clear" else {"project_filter": None} if act == "unfilter" else {
                "status": "active" if data.get("status") == "inactive" else "inactive"}
            await state.update_data(**changes)
            await show_list(callback, state, system_user)
    elif act in {"new", "edit"}:
        if current not in {States.card.state, States.listing.state} or (act == "edit" and current != States.card.state):
            raise ValidationError("Откройте карточку или список")
        draft = {f.name: data["old"].get(f.name) for f in fields(kind)} if act == "edit" else {}
        await state.update_data(draft=draft, draft_labels=data.get("labels", {}) if act == "edit" else {},
            editing=act == "edit", index=0, purpose="form", key=str(uuid.uuid4()))
        await form(callback, state, system_user)
    elif act == "correct":
        if current != States.confirming.state:
            raise ValidationError("Откройте предпросмотр")
        await state.update_data(index=0, purpose="form")
        await form(callback, state, system_user)
    elif act in {"pick", "picksearch", "skip", "keep", "option"}:
        if current not in {States.picking.state, States.editing.state}:
            raise ValidationError("Откройте форму")
        if act == "picksearch":
            await state.set_state(States.picker_search)
            await render(callback, state, "Введите строку поиска:", [])
        elif act == "pick":
            if current != States.picking.state:
                raise ValidationError("Откройте список выбора")
            # Resolve only through authorized service choices; direct ID is revalidated on save.
            async with session_factory() as session:
                row = await people.choice(session, data["relation"], identifier(value),
                    user_id=system_user.id, purpose=data["purpose"])
            label = getattr(row, "full_name", None) or row.name
            if data["purpose"] == "filter":
                await state.update_data(project_filter=str(row.id), project_filter_label=label)
                await show_list(callback, state, system_user)
            elif data["purpose"] == "member":
                await state.update_data(worker_id=str(row.id), joining=True, membership_id=None, key=str(uuid.uuid4()))
                await state.set_state(States.member_confirm)
                await render(callback, state, "Добавить в бригаду: " + safe(label) + "?", [("✅ Подтвердить", "savemember", "")])
            else:
                await accept(callback, state, system_user, row.id, label)
        else:
            if data.get("purpose") != "form":
                raise ValidationError("Откройте форму")
            async with session_factory() as session:
                await people.require(session, kind, system_user.id, "manage")
            field = fields(kind)[data["index"]]
            if act == "option" and not field.choices:
                raise ValidationError("Используйте текстовый ввод")
            raw = data["draft"].get(field.name) if act == "keep" else None if act == "skip" else value
            await accept(callback, state, system_user, raw, "Без объекта" if act == "skip" else None)
    elif act == "save":
        if current != States.confirming.state:
            raise ValidationError("Сначала подтвердите данные")
        async with session_factory() as session:
            async with session.begin():
                row = await people.save(session, kind, data["draft"], user_id=system_user.id,
                    idempotency_key=identifier(data["key"]),
                    entity_id=identifier(data["entity_id"]) if data["editing"] else None,
                    expected_version=data["old"]["version"] if data["editing"] else None)
                entity_id = row.id
        await show_card(callback, state, system_user, entity_id, saved=True)
    elif act in {"status", "refresh", "list", "members", "join"}:
        if current != States.card.state:
            raise ValidationError("Откройте карточку")
        if act == "list":
            await show_list(callback, state, system_user)
        elif act == "refresh":
            await show_card(callback, state, system_user, identifier(data["entity_id"]))
        elif act == "status":
            await state.update_data(key=str(uuid.uuid4()), reason=None)
            if kind == "worker" and not data["old"]["archived"]:
                await state.set_state(States.reason)
                await render(callback, state, "Причина увольнения (необязательно). Введите текст или «-».", [("Без причины", "noreason", "")])
            else:
                await confirm_status(callback, state)
        elif kind != "crew":
            raise ValidationError("Откройте бригаду")
        elif act == "members":
            await state.update_data(ended=value == "ended")
            await show_members(callback, state, system_user)
        else:
            await state.update_data(purpose="member", relation="worker", picker_query="")
            await picker(callback, state, system_user)
    elif act == "noreason":
        if current != States.reason.state:
            raise ValidationError("Откройте подтверждение увольнения")
        await state.update_data(reason=None)
        await confirm_status(callback, state)
    elif act == "savestatus":
        if current != States.status_confirm.state:
            raise ValidationError("Сначала подтвердите действие")
        async with session_factory() as session:
            async with session.begin():
                await people.change_status(session, kind, identifier(data["entity_id"]),
                    inactive=not data["old"]["archived"], reason=data.get("reason"), user_id=system_user.id,
                    idempotency_key=identifier(data["key"]), expected_version=data["old"]["version"])
        await show_card(callback, state, system_user, identifier(data["entity_id"]))
    elif act == "leave":
        if current != States.members.state or value not in data.get("member_rows", {}):
            raise ValidationError("Выберите действующее участие")
        member = data["member_rows"][value]
        await state.update_data(worker_id=member["worker_id"], joining=False, membership_id=str(identifier(value)), key=str(uuid.uuid4()))
        await state.set_state(States.member_confirm)
        await render(callback, state, "Завершить участие: " + safe(member["name"]) + "?", [("✅ Подтвердить", "savemember", "")])
    elif act == "savemember":
        if current != States.member_confirm.state or kind != "crew":
            raise ValidationError("Сначала подтвердите участие")
        async with session_factory() as session:
            async with session.begin():
                await people.membership(session, identifier(data["entity_id"]), identifier(data["worker_id"]),
                    joining=data["joining"], user_id=system_user.id, idempotency_key=identifier(data["key"]),
                    membership_id=identifier(data["membership_id"]) if data.get("membership_id") else None)
        await show_card(callback, state, system_user, identifier(data["entity_id"]))
    else:
        raise ValidationError("Неизвестное действие")
    await callback.answer()


@router.message(States.editing, States.searching, States.picker_search, States.reason)
async def text_input(message: Message, state, system_user):
    data = await state.get_data()
    current = await state.get_state()
    async with session_factory() as session:
        await people.require(session, data["kind"], system_user.id,
                             "manage" if current in {States.editing.state, States.reason.state} else "view")
    text = message.text
    if text is None:
        raise ValidationError("Введите текст")
    if current == States.editing.state:
        field = fields(data["kind"])[data["index"]]
        if field.choices or field.relation:
            raise ValidationError("Используйте кнопки выбора")
        await accept(message, state, system_user, text)
    elif current == States.reason.state:
        if len(text) > 1000:
            raise ValidationError("Причина: максимум 1000 символов")
        await state.update_data(reason=None if text.strip() == "-" else text.strip())
        await confirm_status(message, state)
    else:
        if not text.strip() or len(text) > 100:
            raise ValidationError("Введите от 1 до 100 символов")
        await state.update_data(**{"picker_query" if current == States.picker_search.state else "query": text.strip()})
        if current == States.picker_search.state:
            await picker(message, state, system_user)
        else:
            await show_list(message, state, system_user)


@router.message(States.picking, States.confirming, States.status_confirm, States.member_confirm, States.members, States.card, States.listing, States.menu)
async def use_buttons(message: Message):
    await message.answer("Используйте кнопки текущего экрана. /menu — главное меню.")
