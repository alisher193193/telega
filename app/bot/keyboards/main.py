from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class BillingMenuCallback(CallbackData, prefix="billing_menu"):
    action: str  # customer_acceptance | acts


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="📝 Внести данные"),
                KeyboardButton(text="👥 Люди"),
            ],
            [
                KeyboardButton(text="🏗 Объекты"),
                KeyboardButton(text="💰 Касса"),
            ],
            [
                KeyboardButton(text="📊 Отчёты"),
                KeyboardButton(text="📄 К выставлению"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите раздел",
    )


def billing_menu() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="🧾 Приёмка заказчиком",
        callback_data=BillingMenuCallback(action="customer_acceptance"),
    )
    builder.button(
        text="📄 Акты",
        callback_data=BillingMenuCallback(action="acts"),
    )
    builder.adjust(1)
    return builder.as_markup()
