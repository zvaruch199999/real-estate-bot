from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Створити пропозицію", callback_data="create_offer")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")]
    ])


def category_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏷️ Оренда", callback_data="cat:rent"),
         InlineKeyboardButton(text="🏷️ Продаж", callback_data="cat:sale")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")]
    ])


def living_type_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Кімната", callback_data="type:room"),
         InlineKeyboardButton(text="🏢 Квартира", callback_data="type:flat")],
        [InlineKeyboardButton(text="🏡 Будинок", callback_data="type:house")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")]
    ])


def preview_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опублікувати", callback_data="publish"),
         InlineKeyboardButton(text="✏️ Редагувати", callback_data="edit")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")]
    ])


def edit_fields_kb():
    # Кнопки редагування 2–14 (як у твоєму списку)
    rows = [
        [InlineKeyboardButton(text="2. Категорія", callback_data="editfield:category"),
         InlineKeyboardButton(text="3. Проживання", callback_data="editfield:living_type")],
        [InlineKeyboardButton(text="4. Вулиця", callback_data="editfield:street"),
         InlineKeyboardButton(text="5. Місто", callback_data="editfield:city")],
        [InlineKeyboardButton(text="6. Район", callback_data="editfield:district"),
         InlineKeyboardButton(text="7. Переваги", callback_data="editfield:advantages")],
        [InlineKeyboardButton(text="8. Оренда/Ціна", callback_data="editfield:price"),
         InlineKeyboardButton(text="9. Депозит", callback_data="editfield:deposit")],
        [InlineKeyboardButton(text="10. Комісія", callback_data="editfield:commission"),
         InlineKeyboardButton(text="11. Паркінг", callback_data="editfield:parking")],
        [InlineKeyboardButton(text="12. Заселення від", callback_data="editfield:move_in"),
         InlineKeyboardButton(text="13. Огляди від", callback_data="editfield:viewings")],
        [InlineKeyboardButton(text="14. Маклер", callback_data="editfield:broker")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_preview")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def status_kb(offer_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Актуально", callback_data=f"status:{offer_id}:active"),
            InlineKeyboardButton(text="🟡 Резерв", callback_data=f"status:{offer_id}:reserved"),
        ],
        [
            InlineKeyboardButton(text="✅ Закрито", callback_data=f"status:{offer_id}:closed"),
            InlineKeyboardButton(text="🔴 Знято", callback_data=f"status:{offer_id}:removed"),
        ]
    ])
