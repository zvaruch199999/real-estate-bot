import os
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from openpyxl import Workbook, load_workbook

# ================= SAFE ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID_RAW = os.getenv("GROUP_CHAT_ID")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не заданий у змінних середовища")

GROUP_CHAT_ID = None
if GROUP_CHAT_ID_RAW:
    try:
        GROUP_CHAT_ID = int(GROUP_CHAT_ID_RAW)
    except ValueError:
        raise RuntimeError("❌ GROUP_CHAT_ID має бути числом")

# ================= FILES =================
DATA_DIR = "data"
EXCEL_FILE = f"{DATA_DIR}/offers.xlsx"
os.makedirs(DATA_DIR, exist_ok=True)

# ================= EXCEL =================
HEADERS = [
    "ID","Дата","Категорія","Тип житла","Вулиця","Місто","Район","Переваги",
    "Ціна","Депозит","Комісія","Паркінг",
    "Заселення","Огляди","Маклер",
    "Фото_IDs","Статус"
]

def init_excel():
    if not os.path.exists(EXCEL_FILE):
        wb = Workbook()
        ws = wb.active
        ws.append(HEADERS)
        wb.save(EXCEL_FILE)

def save_offer(data):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    ws.append([
        ws.max_row,
        datetime.now().strftime("%Y-%m-%d"),
        data["category"], data["property_type"],
        data["street"], data["city"], data["district"],
        data["advantages"], data["rent"], data["deposit"],
        data["commission"], data["parking"],
        data["move_in"], data["viewing"], data["broker"],
        ",".join(data["photos"]),
        "Активна"
    ])
    wb.save(EXCEL_FILE)

# ================= FSM =================
class OfferFSM(StatesGroup):
    category = State()
    property_type = State()
    street = State()
    city = State()
    district = State()
    advantages = State()
    rent = State()
    deposit = State()
    commission = State()
    parking = State()
    move_in = State()
    viewing = State()
    broker = State()
    photos = State()

# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ================= START =================
@dp.message(Command("start"))
async def start(message: Message, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Оренда", callback_data="cat_rent"),
            InlineKeyboardButton(text="Продаж", callback_data="cat_sale")
        ]
    ])
    await message.answer(
        "Вітаю 👋\nОберіть категорію:",
        reply_markup=kb
    )
    await state.set_state(OfferFSM.category)

# ================= CATEGORY (BUTTON) =================
@dp.callback_query(F.data.startswith("cat_"))
async def set_category_button(call: CallbackQuery, state: FSMContext):
    category = "Оренда" if call.data == "cat_rent" else "Продаж"
    await state.update_data(category=category)
    await call.message.edit_reply_markup(None)
    await call.message.answer("Тип житла:")
    await state.set_state(OfferFSM.property_type)
    await call.answer()

# ================= CATEGORY (TEXT FALLBACK) =================
@dp.message(OfferFSM.category)
async def set_category_text(message: Message, state: FSMContext):
    text = message.text.lower()
    if "оренд" in text:
        category = "Оренда"
    elif "прод" in text:
        category = "Продаж"
    else:
        await message.answer("❗ Напишіть `Оренда` або `Продаж`.")
        return

    await state.update_data(category=category)
    await message.answer("Тип житла:")
    await state.set_state(OfferFSM.property_type)

# ================= OFFER FLOW =================
@dp.message(OfferFSM.property_type)
async def s2(m,s): await s.update_data(property_type=m.text); await m.answer("Вулиця:"); await s.set_state(OfferFSM.street)

@dp.message(OfferFSM.street)
async def s3(m,s): await s.update_data(street=m.text); await m.answer("Місто:"); await s.set_state(OfferFSM.city)

@dp.message(OfferFSM.city)
async def s4(m,s): await s.update_data(city=m.text); await m.answer("Район:"); await s.set_state(OfferFSM.district)

@dp.message(OfferFSM.district)
async def s5(m,s): await s.update_data(district=m.text); await m.answer("Переваги житла:"); await s.set_state(OfferFSM.advantages)

@dp.message(OfferFSM.advantages)
async def s6(m,s): await s.update_data(advantages=m.text); await m.answer("Ціна:"); await s.set_state(OfferFSM.rent)

@dp.message(OfferFSM.rent)
async def s7(m,s): await s.update_data(rent=m.text); await m.answer("Депозит:"); await s.set_state(OfferFSM.deposit)

@dp.message(OfferFSM.deposit)
async def s8(m,s): await s.update_data(deposit=m.text); await m.answer("Комісія:"); await s.set_state(OfferFSM.commission)

@dp.message(OfferFSM.commission)
async def s9(m,s): await s.update_data(commission=m.text); await m.answer("Паркінг:"); await s.set_state(OfferFSM.parking)

@dp.message(OfferFSM.parking)
async def s10(m,s): await s.update_data(parking=m.text); await m.answer("Заселення від:"); await s.set_state(OfferFSM.move_in)

@dp.message(OfferFSM.move_in)
async def s11(m,s): await s.update_data(move_in=m.text); await m.answer("Огляди від:"); await s.set_state(OfferFSM.viewing)

@dp.message(OfferFSM.viewing)
async def s12(m,s): await s.update_data(viewing=m.text); await m.answer("Маклер (нік):"); await s.set_state(OfferFSM.broker)

@dp.message(OfferFSM.broker)
async def s13(m,s):
    await s.update_data(broker=m.text, photos=[])
    await m.answer("Надішліть фото. Коли завершили — напишіть будь-який текст.")
    await s.set_state(OfferFSM.photos)

@dp.message(OfferFSM.photos, F.photo)
async def s14(m,s):
    d = await s.get_data()
    d["photos"].append(m.photo[-1].file_id)
    await s.update_data(photos=d["photos"])
    await m.answer("Фото додано.")

@dp.message(OfferFSM.photos)
async def finish(m,s):
    data = await s.get_data()
    save_offer(data)

    if GROUP_CHAT_ID:
        media = [
            InputMediaPhoto(p, caption="🏠 Нова пропозиція" if i == 0 else None)
            for i,p in enumerate(data["photos"])
        ]
        await bot.send_media_group(GROUP_CHAT_ID, media)

    await m.answer("✅ Пропозицію збережено.\n\nНапишіть /start для нової.")
    await s.clear()

# ================= MAIN =================
async def main():
    init_excel()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
