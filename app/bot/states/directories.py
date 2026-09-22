from aiogram.fsm.state import State, StatesGroup


class DirectoryStates(StatesGroup):
    menu = State()
    listing = State()
    searching = State()
    card = State()
    editing = State()
    picking = State()
    searching_reference = State()
    confirming = State()
    confirming_archive = State()
