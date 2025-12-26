from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Зробити пропозицію", callback_data="new_offer")]
    ])

def category_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оренда", callback_data="rent")],
        [InlineKeyboardButton(text="Продажа", callback_data="sale")]
    ])

def finish_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data="publish")],
        [InlineKeyboardButton(text="✏️ Змінити пункт", callback_data="edit")]
    ])
