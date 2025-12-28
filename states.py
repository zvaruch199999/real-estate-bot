from aiogram.fsm.state import StatesGroup, State

class OfferForm(StatesGroup):
    category = State()
    housing_type = State()
    street = State()
    city = State()
    district = State()
    advantages = State()
    rent = State()
    deposit = State()
    commission = State()
    parking = State()
    move_in_from = State()
    viewings_from = State()
    broker = State()
    photos = State()
    preview = State()

class EditForm(StatesGroup):
    choose_field = State()
    enter_value = State()
