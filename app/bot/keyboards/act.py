import uuid
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder


class ActProjectCallback(CallbackData, prefix="ap"):
    project_id: uuid.UUID


class ActContractCallback(CallbackData, prefix="ac"):
    contract_id: str


class ActOpenCallback(CallbackData, prefix="ao"):
    act_id: uuid.UUID


class ActWorkCallback(CallbackData, prefix="aw"):
    work_entry_id: uuid.UUID


class ActLineCallback(CallbackData, prefix="al"):
    line_id: uuid.UUID
    action: str = "open"


class ActCardActionCallback(CallbackData, prefix="act_card"):
    act_id: uuid.UUID
    action: str


class ActNavCallback(CallbackData, prefix="an"):
    action: str


class ActPageCallback(CallbackData, prefix="ag"):
    kind: str
    page: int


def _pages(builder, kind, page, more):
    if page > 0:
        builder.button(text="◀ Предыдущие", callback_data=ActPageCallback(kind=kind, page=page - 1))
    if more:
        builder.button(text="Следующие ▶", callback_data=ActPageCallback(kind=kind, page=page + 1))


def _flow(builder, back=True):
    if back:
        builder.button(text="⬅ Назад", callback_data=ActNavCallback(action="back"))
    builder.button(text="✖ Отмена", callback_data=ActNavCallback(action="cancel_flow"))
    builder.adjust(1)
    return builder.as_markup()


def acts_list_keyboard(acts, *, page=0, more=False):
    b = InlineKeyboardBuilder()
    for act in acts:
        b.button(text=f"№{act.act_number} от {act.act_date:%d.%m.%Y} · {act.status}", callback_data=ActOpenCallback(act_id=act.id))
    _pages(b, "acts", page, more)
    b.button(text="➕ Новый черновик", callback_data=ActNavCallback(action="new"))
    return _flow(b, False)


def projects_keyboard(projects, *, page=0, more=False):
    b = InlineKeyboardBuilder()
    for project in projects:
        b.button(text=project.name, callback_data=ActProjectCallback(project_id=project.id))
    _pages(b, "projects", page, more)
    return _flow(b)


def contracts_keyboard(contracts, *, page=0, more=False):
    b = InlineKeyboardBuilder()
    for contract in contracts:
        b.button(text=contract.number, callback_data=ActContractCallback(contract_id=str(contract.id)))
    b.button(text="Без договора", callback_data=ActContractCallback(contract_id="none"))
    _pages(b, "contracts", page, more)
    return _flow(b)


def available_work_entries_keyboard(act_id, entries, *, page=0, more=False):
    b = InlineKeyboardBuilder()
    for entry, available in entries:
        b.button(text=f"{entry.entry_date:%d.%m} · доступно {available}", callback_data=ActWorkCallback(work_entry_id=entry.id))
    _pages(b, "works", page, more)
    return _flow(b)


def act_card_keyboard(act):
    b = InlineKeyboardBuilder()
    actions = []
    if act.status == "draft":
        actions += [("➕ Добавить работу", "add_line"), ("📋 Строки акта", "lines"), ("✅ Завершить", "finalize")]
    if act.status != "cancelled":
        actions.append(("⛔ Отменить акт", "cancel"))
    actions += [("📥 Скачать Excel", "download"), ("⬅ К списку актов", "back")]
    for text, action in actions:
        b.button(text=text, callback_data=ActCardActionCallback(act_id=act.id, action=action))
    return _flow(b, False)


def lines_keyboard(act_id, lines, *, page=0, more=False):
    b = InlineKeyboardBuilder()
    for line in lines:
        b.button(text=f"{line.work_type_name} · {line.accepted_volume} = {line.amount}", callback_data=ActLineCallback(line_id=line.id))
    _pages(b, "lines", page, more)
    return _flow(b)


def line_card_keyboard(act_id, line_id):
    b = InlineKeyboardBuilder()
    b.button(text="⛔ Отменить строку", callback_data=ActLineCallback(line_id=line_id, action="cancel"))
    return _flow(b)


def back_keyboard(act_id=None):
    return _flow(InlineKeyboardBuilder())


def confirmation_keyboard():
    b = InlineKeyboardBuilder()
    b.button(text="✅ Сохранить", callback_data=ActNavCallback(action="save_line"))
    return _flow(b)
