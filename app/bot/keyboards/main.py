from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


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
