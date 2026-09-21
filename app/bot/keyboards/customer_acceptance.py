from __future__ import annotations

import uuid

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class CAProjectCallback(CallbackData, prefix="ca_proj"):
    project_id: uuid.UUID


class CAWorkCallback(CallbackData, prefix="ca_work"):
    work_entry_id: uuid.UUID


class CAConfirmCallback(CallbackData, prefix="ca_confirm"):
    action: str  # save | edit | cancel


class CANavCallback(CallbackData, prefix="ca_nav"):
    action: str  # back | cancel


def projects_keyboard(projects: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for project in projects:
        builder.button(
            text=project.name,
            callback_data=CAProjectCallback(project_id=project.id),
        )
    builder.button(text="✖ Отмена", callback_data=CANavCallback(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def work_entries_keyboard(entries: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for entry in entries:
        label = f"{entry.entry_date:%d.%m} · {entry.claimed_volume}"
        builder.button(text=label, callback_data=CAWorkCallback(work_entry_id=entry.id))
    builder.button(text="⬅ Назад", callback_data=CANavCallback(action="back"))
    builder.adjust(1)
    return builder.as_markup()


def confirmation_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Сохранить", callback_data=CAConfirmCallback(action="save"))
    builder.button(text="✏️ Исправить", callback_data=CAConfirmCallback(action="edit"))
    builder.button(text="✖ Отменить", callback_data=CAConfirmCallback(action="cancel"))
    builder.adjust(1)
    return builder.as_markup()


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅ Назад", callback_data=CANavCallback(action="back").pack())]
        ]
    )
