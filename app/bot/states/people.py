from aiogram.fsm.state import State, StatesGroup


class PeopleStates(StatesGroup):
    menu = State()
    listing = State()
    searching = State()
    card = State()
    editing = State()
    picking = State()
    picker_search = State()
    confirming = State()
    reason = State()
    status_confirm = State()
    members = State()
    member_confirm = State()
