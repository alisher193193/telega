from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder


class PeopleCallback(CallbackData, prefix="ppl"):
    action: str
    value: str = ""
    nonce: str = ""


def keyboard(items, nonce, *, controls=True):
    builder = InlineKeyboardBuilder()
    for label, action, value in items:
        builder.button(text=label[:64], callback_data=PeopleCallback(action=action, value=str(value), nonce=nonce).pack())
    if controls:
        for label, action in (("◀️ Назад", "back"), ("❌ Отменить", "cancel"), ("🏠 Главное меню", "home")):
            builder.button(text=label, callback_data=PeopleCallback(action=action, nonce=nonce).pack())
    builder.adjust(1)
    return builder.as_markup()


def pages(items, page, more):
    if page:
        items.append(("◀ Предыдущие", "page", page - 1))
    if more:
        items.append(("Следующие ▶", "page", page + 1))
    return items
