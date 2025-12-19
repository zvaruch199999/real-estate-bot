from aiogram.fsm.state import State, StatesGroup


class OfferFlow(StatesGroup):
    category = State()
    street = State()
    district = State()
    advantages = State()
    rent = State()
    deposit = State()
    commission = State()
    parking = State()
    settlement = State()
    viewing = State()
    broker = State()
    photos = State()
    status = State()
    confirm = State()
