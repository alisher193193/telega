from aiogram.fsm.state import State, StatesGroup


class ActStates(StatesGroup):
    listing = State()
    choosing_project = State()
    choosing_contract = State()
    viewing_act = State()
    choosing_work_entry = State()
    entering_quantity = State()
    entering_reason = State()
