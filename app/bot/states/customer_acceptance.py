from aiogram.fsm.state import State, StatesGroup


class CustomerAcceptanceStates(StatesGroup):
    choosing_project = State()
    choosing_work_entry = State()
    entering_volume = State()
    entering_comment = State()
    confirming = State()
