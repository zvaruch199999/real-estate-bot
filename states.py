from aiogram.fsm.state import State, StatesGroup

class CreateOffer(StatesGroup):
    category = State()
    housing_type = State()
    housing_type_custom = State()
    street = State()
    city = State()
    district = State()
    advantages = State()
    rent = State()
    deposit = State()
    commission = State()
    parking = State()
    settlement_from = State()
    viewings_from = State()
    photos = State()
    preview = State()

class EditOffer(StatesGroup):
    pick_field = State()
    new_value = State()
