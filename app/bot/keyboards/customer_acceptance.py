import uuid
from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder


class CAProjectCallback(CallbackData, prefix="ca_proj"):
    project_id: uuid.UUID


class CAWorkCallback(CallbackData, prefix="ca_work"):
    work_entry_id: uuid.UUID


class CAConfirmCallback(CallbackData, prefix="ca_confirm"):
    action: str


class CANavCallback(CallbackData, prefix="ca_nav"):
    action: str


class CAPageCallback(CallbackData, prefix="ca_page"):
    page: int


def _navigation(builder, page=None, more=False):
    if page is not None:
        if page > 0:
            builder.button(text="◀ Предыдущие", callback_data=CAPageCallback(page=page - 1))
        if more:
            builder.button(text="Следующие ▶", callback_data=CAPageCallback(page=page + 1))
    builder.button(text="⬅ Назад", callback_data=CANavCallback(action="back"))
    builder.button(text="✖ Отмена", callback_data=CANavCallback(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def projects_keyboard(projects, *, page=0, more=False):
    b = InlineKeyboardBuilder()
    for project in projects:
        b.button(text=project.name, callback_data=CAProjectCallback(project_id=project.id))
    return _navigation(b, page, more)


def work_entries_keyboard(entries, *, page=0, more=False):
    b = InlineKeyboardBuilder()
    for entry in entries:
        b.button(text=f"{entry.entry_date:%d.%m} · {entry.claimed_volume}", callback_data=CAWorkCallback(work_entry_id=entry.id))
    return _navigation(b, page, more)


def confirmation_keyboard():
    b = InlineKeyboardBuilder()
    for text, action in [("✅ Сохранить", "save"), ("✏️ Исправить", "edit"), ("✖ Отменить", "cancel")]:
        b.button(text=text, callback_data=CAConfirmCallback(action=action))
    return _navigation(b)


def back_keyboard():
    return _navigation(InlineKeyboardBuilder())
