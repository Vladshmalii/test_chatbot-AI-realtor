from aiogram.fsm.state import State, StatesGroup

class RealtorState(StatesGroup):
    collecting = State()
    waiting_contact = State()
    finished = State()
