from __future__ import annotations

import uuid

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class ActProjectCallback(CallbackData, prefix="act_proj"):
    project_id: uuid.UUID


class ActContractCallback(CallbackData, prefix="act_contract"):
    contract_id: str  # "none" or uuid string


class ActOpenCallback(CallbackData, prefix="act_open"):
    act_id: uuid.UUID


class ActWorkCallback(CallbackData, prefix="act_work"):
    act_id: uuid.UUID
    work_entry_id: uuid.UUID


class ActLineCallback(CallbackData, prefix="act_line"):
    act_id: uuid.UUID
    line_id: uuid.UUID


class ActCardActionCallback(CallbackData, prefix="act_card"):
    act_id: uuid.UUID
    action: str  # add_line | lines | finalize | cancel | download | back


class ActNavCallback(CallbackData, prefix="act_nav"):
    action: str  # new | back | cancel_flow


def acts_list_keyboard(acts: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for act in acts:
        builder.button(
            text=f"№{act.act_number} от {act.act_date:%d.%m.%Y} · {act.status}",
            callback_data=ActOpenCallback(act_id=act.id),
        )
    builder.button(text="➕ Новый черновик", callback_data=ActNavCallback(action="new"))
    builder.adjust(1)
    return builder.as_markup()


def projects_keyboard(projects: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for project in projects:
        builder.button(text=project.name, callback_data=ActProjectCallback(project_id=project.id))
    builder.button(text="✖ Отмена", callback_data=ActNavCallback(action="cancel_flow"))
    builder.adjust(1)
    return builder.as_markup()


def contracts_keyboard(contracts: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for contract in contracts:
        builder.button(text=contract.number, callback_data=ActContractCallback(contract_id=str(contract.id)))
    builder.button(text="Без договора", callback_data=ActContractCallback(contract_id="none"))
    builder.adjust(1)
    return builder.as_markup()


def available_work_entries_keyboard(act_id: uuid.UUID, entries: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for entry, available in entries:
        label = f"{entry.entry_date:%d.%m} · доступно {available}"
        builder.button(
            text=label,
            callback_data=ActWorkCallback(act_id=act_id, work_entry_id=entry.id),
        )
    builder.button(text="⬅ Назад", callback_data=ActCardActionCallback(act_id=act_id, action="back"))
    builder.adjust(1)
    return builder.as_markup()


def act_card_keyboard(act) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if act.status == "draft":
        builder.button(text="➕ Добавить работу", callback_data=ActCardActionCallback(act_id=act.id, action="add_line"))
        builder.button(text="📋 Строки акта", callback_data=ActCardActionCallback(act_id=act.id, action="lines"))
        builder.button(text="✅ Завершить", callback_data=ActCardActionCallback(act_id=act.id, action="finalize"))
    if act.status != "cancelled":
        builder.button(text="⛔ Отменить акт", callback_data=ActCardActionCallback(act_id=act.id, action="cancel"))
    builder.button(text="📥 Скачать Excel", callback_data=ActCardActionCallback(act_id=act.id, action="download"))
    builder.button(text="⬅ К списку актов", callback_data=ActCardActionCallback(act_id=act.id, action="back"))
    builder.adjust(1)
    return builder.as_markup()


def lines_keyboard(act_id: uuid.UUID, lines: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for line in lines:
        builder.button(
            text=f"{line.work_type_name} · {line.accepted_volume} = {line.amount}",
            callback_data=ActLineCallback(act_id=act_id, line_id=line.id),
        )
    builder.button(text="⬅ Назад", callback_data=ActCardActionCallback(act_id=act_id, action="back"))
    builder.adjust(1)
    return builder.as_markup()


def line_card_keyboard(act_id: uuid.UUID, line_id: uuid.UUID) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑 Удалить строку", callback_data=ActLineCallback(act_id=act_id, line_id=line_id))
    builder.button(text="⬅ Назад", callback_data=ActCardActionCallback(act_id=act_id, action="lines"))
    builder.adjust(1)
    return builder.as_markup()


def back_keyboard(act_id: uuid.UUID | None = None) -> InlineKeyboardMarkup:
    action = "back" if act_id else "cancel_flow"
    if act_id:
        callback = ActCardActionCallback(act_id=act_id, action=action).pack()
    else:
        callback = ActNavCallback(action=action).pack()
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅ Назад", callback_data=callback)]])
