import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")  # ваша група/канал для публікації: -100...

# ---------- Дані (поки що in-memory) ----------
@dataclass
class Offer:
    category: Optional[str] = None
    street: Optional[str] = None
    district: Optional[str] = None
    perks: Optional[str] = None
    rent: Optional[str] = None
    deposit: Optional[str] = None
    commission: Optional[str] = None
    parking: Optional[str] = None
    move_in: Optional[str] = None
    viewings: Optional[str] = None
    contact: Optional[str] = None
    photos: List[str] = field(default_factory=list)  # file_id

OFFERS_BY_USER: Dict[int, Offer] = {}
PUBLISHED: List[Offer] = []


# ---------- FSM ----------
class OfferFlow(StatesGroup):
    category = State()
    street = State()
    district = State()
    perks = State()
    rent = State()
    deposit = State()
    commission = State()
    parking = State()
    move_in = State()
    viewings = State()
    contact = State()
    photos_decision = State()
    photos_collect = State()
    confirm = State()


# ---------- Клавіатури ----------
def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Пропоную житло", callback_data="offer_start")],
        [InlineKeyboardButton(text="🔎 Шукаю житло (перегляд)", callback_data="search_start")],
    ])

def kb_category():
    items = [
        ("Кімната", "cat_room"),
        ("Студія", "cat_studio"),
        ("Квартира", "cat_flat"),
        ("Будинок", "cat_house"),
    ]
    rows = []
    for i in range(0, len(items), 2):
        rows.append([InlineKeyboardButton(text=t, callback_data=cb) for t, cb in items[i:i+2]])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_district():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Центр", callback_data="dist_center"),
         InlineKeyboardButton(text="Старе Місто", callback_data="dist_old")],
        [InlineKeyboardButton(text="Петржалка", callback_data="dist_petrzalka")],
        [InlineKeyboardButton(text="Інше (вписати)", callback_data="dist_other")],
    ])

def kb_yes_no(prefix: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Так", callback_data=f"{prefix}_yes"),
         InlineKeyboardButton(text="Ні", callback_data=f"{prefix}_no")],
    ])

def kb_move_in():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Одразу", callback_data="move_now"),
         InlineKeyboardButton(text="З дати (вписати)", callback_data="move_date")],
        [InlineKeyboardButton(text="За домовленістю", callback_data="move_agree")],
    ])

def kb_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опублікувати", callback_data="confirm_publish")],
        [InlineKeyboardButton(text="↩️ Назад (поправити контакт)", callback_data="confirm_back")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="confirm_cancel")],
    ])

def kb_search_nav(idx: int, total: int):
    prev_cb = f"search_prev:{idx}"
    next_cb = f"search_next:{idx}"
    rows = []
    nav = []
    if total > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=prev_cb))
        nav.append(InlineKeyboardButton(text=f"{idx+1}/{total}", callback_data="noop"))
        nav.append(InlineKeyboardButton(text="➡️", callback_data=next_cb))
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🏠 Додати пропозицію", callback_data="offer_start")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Допоміжне ----------
def get_offer(user_id: int) -> Offer:
    if user_id not in OFFERS_BY_USER:
        OFFERS_BY_USER[user_id] = Offer()
    return OFFERS_BY_USER[user_id]

def offer_text(o: Offer) -> str:
    return (
        "📢 *НОВА ПРОПОЗИЦІЯ*\n"
        f"🏷️ Тип: {o.category or '-'}\n"
        f"📍 Локація: {o.street or '-'}\n"
        f"🗺️ Район: {o.district or '-'}\n"
        f"✨ Переваги: {o.perks or '-'}\n"
        f"💶 Оренда: {o.rent or '-'}\n"
        f"💰 Депозит: {o.deposit or '-'}\n"
        f"🧾 Комісія: {o.commission or '-'}\n"
        f"🅿️ Парковка: {o.parking or '-'}\n"
        f"📆 Заселення: {o.move_in or '-'}\n"
        f"👀 Перегляди: {o.viewings or '-'}\n"
        f"📞 Контакт: {o.contact or '-'}\n"
        f"🖼️ Фото: {len(o.photos)}"
    )


# ---------- Bot ----------
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("Вітаю! Оберіть дію:", reply_markup=kb_main())

# ====== Пропоную ======
@dp.callback_query(F.data == "offer_start")
async def offer_start(c: CallbackQuery, state: FSMContext):
    OFFERS_BY_USER[c.from_user.id] = Offer()
    await state.set_state(OfferFlow.category)
    await c.message.answer("Оберіть тип житла:", reply_markup=kb_category())
    await c.answer()

@dp.callback_query(OfferFlow.category, F.data.startswith("cat_"))
async def offer_category(c: CallbackQuery, state: FSMContext):
    o = get_offer(c.from_user.id)
    mapping = {
        "cat_room": "Кімната",
        "cat_studio": "Студія",
        "cat_flat": "Квартира",
        "cat_house": "Будинок",
    }
    o.category = mapping.get(c.data, c.data)
    await state.set_state(OfferFlow.street)
    await c.message.answer("Вкажіть вулицю/локацію (текст):")
    await c.answer()

@dp.message(OfferFlow.street)
async def offer_street(m: Message, state: FSMContext):
    o = get_offer(m.from_user.id)
    o.street = (m.text or "").strip()
    await state.set_state(OfferFlow.district)
    await m.answer("Оберіть район:", reply_markup=kb_district())

@dp.callback_query(OfferFlow.district, F.data.startswith("dist_"))
async def offer_district(c: CallbackQuery, state: FSMContext):
    if c.data == "dist_other":
        await c.message.answer("Впишіть район своїми словами:")
        await c.answer()
        return
    o = get_offer(c.from_user.id)
    mapping = {"dist_center": "Центр", "dist_old": "Старе Місто", "dist_petrzalka": "Петржалка"}
    o.district = mapping.get(c.data, c.data)
    await state.set_state(OfferFlow.perks)
    await c.message.answer("Опишіть переваги (текст):")
    await c.answer()

@dp.message(OfferFlow.district)
async def offer_district_text(m: Message, state: FSMContext):
    o = get_offer(m.from_user.id)
    o.district = (m.text or "").strip()
    await state.set_state(OfferFlow.perks)
    await m.answer("Опишіть переваги (текст):")

@dp.message(OfferFlow.perks)
async def offer_perks(m: Message, state: FSMContext):
    o = get_offer(m.from_user.id)
    o.perks = (m.text or "").strip()
    await state.set_state(OfferFlow.rent)
    await m.answer("Ціна оренди (напр. 750€ / міс):")

@dp.message(OfferFlow.rent)
async def offer_rent(m: Message, state: FSMContext):
    o = get_offer(m.from_user.id)
    o.rent = (m.text or "").strip()
    await state.set_state(OfferFlow.deposit)
    await m.answer("Депозит (сума/умови):")

@dp.message(OfferFlow.deposit)
async def offer_deposit(m: Message, state: FSMContext):
    o = get_offer(m.from_user.id)
    o.deposit = (m.text or "").strip()
    await state.set_state(OfferFlow.commission)
    await m.answer("Комісія (сума/умови):")

@dp.message(OfferFlow.commission)
async def offer_commission(m: Message, state: FSMContext):
    o = get_offer(m.from_user.id)
    o.commission = (m.text or "").strip()
    await state.set_state(OfferFlow.parking)
    await m.answer("Парковка є?", reply_markup=kb_yes_no("park"))

@dp.callback_query(OfferFlow.parking, F.data.in_(["park_yes", "park_no"]))
async def offer_parking(c: CallbackQuery, state: FSMContext):
    o = get_offer(c.from_user.id)
    o.parking = "Є" if c.data == "park_yes" else "Немає"
    await state.set_state(OfferFlow.move_in)
    await c.message.answer("Коли можна заселятися?", reply_markup=kb_move_in())
    await c.answer()

@dp.callback_query(OfferFlow.move_in, F.data.in_(["move_now", "move_date", "move_agree"]))
async def offer_move_in_choice(c: CallbackQuery, state: FSMContext):
    o = get_offer(c.from_user.id)
    if c.data == "move_now":
        o.move_in = "Одразу"
        await state.set_state(OfferFlow.viewings)
        await c.message.answer("Коли можливі перегляди? (текст)")
    elif c.data == "move_agree":
        o.move_in = "За домовленістю"
        await state.set_state(OfferFlow.viewings)
        await c.message.answer("Коли можливі перегляди? (текст)")
    else:
        await c.message.answer("Впишіть дату/умову заселення (текст):")
        # залишаємося в OfferFlow.move_in, але приймемо текстом
    await c.answer()

@dp.message(OfferFlow.move_in)
async def offer_move_in_text(m: Message, state: FSMContext):
    o = get_offer(m.from_user.id)
    o.move_in = (m.text or "").strip()
    await state.set_state(OfferFlow.viewings)
    await m.answer("Коли можливі перегляди? (текст)")

@dp.message(OfferFlow.viewings)
async def offer_viewings(m: Message, state: FSMContext):
    o = get_offer(m.from_user.id)
    o.viewings = (m.text or "").strip()
    await state.set_state(OfferFlow.contact)
    await m.answer("Контакт (імʼя + телефон/telegram):")

@dp.message(OfferFlow.contact)
async def offer_contact(m: Message, state: FSMContext):
    o = get_offer(m.from_user.id)
    o.contact = (m.text or "").strip()
    await state.set_state(OfferFlow.photos_decision)
    await m.answer("Додати фото?", reply_markup=kb_yes_no("photos"))

@dp.callback_query(OfferFlow.photos_decision, F.data.in_(["photos_yes", "photos_no"]))
async def offer_photos_decision(c: CallbackQuery, state: FSMContext):
    if c.data == "photos_no":
        await state.set_state(OfferFlow.confirm)
        o = get_offer(c.from_user.id)
        await c.message.answer(offer_text(o), parse_mode="Markdown", reply_markup=kb_confirm())
        await c.answer()
        return

    await state.set_state(OfferFlow.photos_collect)
    await c.message.answer("Надішліть фото (можна кілька). Коли закінчите — напишіть: ГОТОВО")
    await c.answer()

@dp.message(OfferFlow.photos_collect, F.photo)
async def offer_photos_collect(m: Message, state: FSMContext):
    o = get_offer(m.from_user.id)
    o.photos.append(m.photo[-1].file_id)
    await m.answer(f"✅ Додано фото. Всього: {len(o.photos)}. Надішліть ще або напишіть ГОТОВО.")

@dp.message(OfferFlow.photos_collect)
async def photos_collect(message: Message, state: FSMContext):
    ...

            
