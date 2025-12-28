from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def kb_done_photos() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data="photos:done")]
    ])

def kb_preview_actions(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📤 Публікувати", callback_data=f"pub:{offer_id}"),
            InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"edit:{offer_id}")
        ],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data=f"cancel:{offer_id}")]
    ])

def kb_status(offer_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Актуально", callback_data=f"st:{offer_id}:ACTIVE"),
            InlineKeyboardButton(text="🟡 Резерв", callback_data=f"st:{offer_id}:RESERVE"),
        ],
        [
            InlineKeyboardButton(text="⚫️ Знято", callback_data=f"st:{offer_id}:REMOVED"),
            InlineKeyboardButton(text="✅ Угода закрита", callback_data=f"st:{offer_id}:CLOSED"),
        ]
    ])

def kb_housing_type() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Кімната", callback_data="ht:Кімната"),
         InlineKeyboardButton(text="1-кімн.", callback_data="ht:1-кімн.")],
        [InlineKeyboardButton(text="2-кімн.", callback_data="ht:2-кімн."),
         InlineKeyboardButton(text="3-кімн.", callback_data="ht:3-кімн.")],
        [InlineKeyboardButton(text="Будинок", callback_data="ht:Будинок"),
         InlineKeyboardButton(text="Студія", callback_data="ht:Студія")],
        [InlineKeyboardButton(text="Інше…", callback_data="ht:__custom__")]
    ])

def kb_category() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оренда", callback_data="cat:Оренда"),
         InlineKeyboardButton(text="Продаж", callback_data="cat:Продаж")]
    ])
