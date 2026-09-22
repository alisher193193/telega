from __future__ import annotations

import uuid

from app.bot.keyboards.act import (
    ActCardActionCallback,
    ActContractCallback,
    ActNavCallback,
    ActOpenCallback,
    act_card_keyboard,
    acts_list_keyboard,
)
from app.bot.keyboards.customer_acceptance import (
    CAConfirmCallback,
    CANavCallback,
    CAProjectCallback,
    confirmation_keyboard,
    projects_keyboard,
)
from app.bot.states.act import ActStates
from app.bot.states.customer_acceptance import CustomerAcceptanceStates


def test_customer_acceptance_states_order():
    states = [
        CustomerAcceptanceStates.choosing_project.state,
        CustomerAcceptanceStates.choosing_work_entry.state,
        CustomerAcceptanceStates.entering_volume.state,
        CustomerAcceptanceStates.entering_comment.state,
        CustomerAcceptanceStates.confirming.state,
    ]
    assert len(set(states)) == 5


def test_act_states_defined():
    states = [
        ActStates.listing.state,
        ActStates.choosing_project.state,
        ActStates.choosing_contract.state,
        ActStates.viewing_act.state,
        ActStates.choosing_work_entry.state,
        ActStates.entering_quantity.state,
        ActStates.entering_reason.state,
    ]
    assert len(set(states)) == 7


def test_customer_acceptance_callback_data_roundtrip():
    project_id = uuid.uuid4()
    packed = CAProjectCallback(project_id=project_id).pack()
    unpacked = CAProjectCallback.unpack(packed)
    assert unpacked.project_id == project_id

    assert CAConfirmCallback(action="save").pack() != CAConfirmCallback(action="cancel").pack()
    assert CANavCallback.unpack(CANavCallback(action="back").pack()).action == "back"


def test_act_callback_data_roundtrip():
    act_id = uuid.uuid4()
    packed = ActOpenCallback(act_id=act_id).pack()
    assert ActOpenCallback.unpack(packed).act_id == act_id

    contract_packed = ActContractCallback(contract_id="none").pack()
    assert ActContractCallback.unpack(contract_packed).contract_id == "none"

    nav_packed = ActNavCallback(action="new").pack()
    assert ActNavCallback.unpack(nav_packed).action == "new"


def test_confirmation_keyboard_has_save_edit_cancel_buttons():
    markup = confirmation_keyboard()
    texts = {button.text for row in markup.inline_keyboard for button in row}
    assert "✅ Сохранить" in texts
    assert "✏️ Исправить" in texts
    assert "✖ Отменить" in texts


def test_projects_keyboard_includes_cancel_button():
    class _FakeProject:
        def __init__(self, name):
            self.id = uuid.uuid4()
            self.name = name

    markup = projects_keyboard([_FakeProject("Объект 1")])
    texts = [button.text for row in markup.inline_keyboard for button in row]
    assert "Объект 1" in texts
    assert "✖ Отмена" in texts


def test_act_card_keyboard_hides_edit_actions_when_not_draft():
    class _FakeAct:
        id = uuid.uuid4()
        status = "finalized"

    markup = act_card_keyboard(_FakeAct())
    action_texts = {
        ActCardActionCallback.unpack(button.callback_data).action
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data and button.callback_data.startswith("act_card")
    }
    assert "add_line" not in action_texts
    assert "download" in action_texts


def test_acts_list_keyboard_has_new_draft_button():
    markup = acts_list_keyboard([])
    texts = [button.text for row in markup.inline_keyboard for button in row]
    assert "➕ Новый черновик" in texts
