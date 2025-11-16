from aiogram.fsm.state import State, StatesGroup


class RealtorState(StatesGroup):
    collecting_name = State()
    browsing = State()
    collecting_filters = State()
    viewing_selection = State()
    viewing_request = State()