from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder
from app.schemas.directories import LABELS


class DirectoryCallback(CallbackData, prefix="dir"):
    action: str
    value: str = ""
    nonce: str = ""


def button(builder, text, action, value="", nonce=""):
    builder.button(text=text[:64], callback_data=DirectoryCallback(action=action, value=str(value), nonce=nonce))


def finish(builder):
    builder.adjust(1)
    return builder.as_markup()


def navigation(builder, nonce, *, back=True):
    if back:
        button(builder, "⬅ Назад", "back", nonce=nonce)
    button(builder, "✖ Отменить", "cancel", nonce=nonce)


def main_menu():
    builder = InlineKeyboardBuilder()
    for kind, label in LABELS.items():
        button(builder, label, "category", kind)
    button(builder, "⬅ В главное меню", "main")
    return finish(builder)


def listing(rows, *, nonce, page, more, archived, picker=False, optional=False, has_value=False):
    builder = InlineKeyboardBuilder()
    for record_id, label in rows:
        button(builder, label, "pick" if picker else "open", record_id.hex, nonce)
    if page:
        button(builder, "◀ Предыдущие", "pickpage" if picker else "page", page - 1, nonce)
    if more:
        button(builder, "Следующие ▶", "pickpage" if picker else "page", page + 1, nonce)
    button(builder, "🔎 Поиск", "picksearch" if picker else "search", nonce=nonce)
    button(builder, "Сбросить поиск", "clearsearch", nonce=nonce)
    if picker:
        if optional:
            button(builder, "Пропустить", "skip", nonce=nonce)
        if has_value:
            button(builder, "Оставить текущее значение", "keep", nonce=nonce)
    else:
        button(builder, "➕ Создать", "new", nonce=nonce)
        button(builder, "Действующие" if archived else "Архив", "toggle", nonce=nonce)
    navigation(builder, nonce)
    return finish(builder)


def card(*, nonce, archived, rate=False):
    builder = InlineKeyboardBuilder()
    if not archived:
        button(builder, "Новая версия расценки" if rate else "✏ Редактировать", "edit", nonce=nonce)
    button(builder, "Восстановить" if archived else "В архив", "restore" if archived else "archive", nonce=nonce)
    navigation(builder, nonce)
    return finish(builder)


def field(field, *, nonce, has_value=False):
    builder = InlineKeyboardBuilder()
    for value, label in field.choices:
        button(builder, label, "option", value, nonce)
    if has_value:
        button(builder, "Оставить текущее значение", "keep", nonce=nonce)
    if not field.required:
        button(builder, "Пропустить / очистить", "skip", nonce=nonce)
    navigation(builder, nonce)
    return finish(builder)


def confirm(nonce, *, archive=False):
    builder = InlineKeyboardBuilder()
    button(builder, "✅ Сохранить", "save_archive" if archive else "save", nonce=nonce)
    navigation(builder, nonce)
    return finish(builder)


def back_cancel(nonce):
    builder = InlineKeyboardBuilder()
    navigation(builder, nonce)
    return finish(builder)
