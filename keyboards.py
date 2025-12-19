from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Я пропоную житло", callback_data="offer")],
        [InlineKeyboardButton(text="🔍 Я шукаю житло", callback_data="search")]
    ])


def category_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Квартира", callback_data="cat:Квартира")],
        [InlineKeyboardButton(text="Будинок", callback_data="cat:Будинок")],
        [InlineKeyboardButton(text="Кімната", callback_data="cat:Кімната")],
        [InlineKeyboardButton(text="Студіо", callback_data="cat:Студіо")]
    ])


def status_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟢 АКТУАЛЬНА", callback_data="status:active")],
        [InlineKeyboardButton(text="🟡 РЕЗЕРВОВАНА", callback_data="status:reserved")],
        [InlineKeyboardButton(text="🔴 НЕАКТУАЛЬНА", callback_data="status:inactive")]
    ])

