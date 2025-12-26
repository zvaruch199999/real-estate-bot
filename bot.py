import os
import asyncio
from datetime import datetime
from typing import List

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from openpyxl import Workbook, load_workbook

# =======================
# ENV VARIABLES
# =======================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))
ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(",")]

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN not set")

# =======================
# FILES
# =======================
DATA_DIR = "data"
EXCEL_FILE = f"{DATA_DIR}/offers.xlsx"

os.makedirs(DATA_DIR, exist_ok=True)

# =======================
# EXCEL INIT
# =======================
HEADERS = [
    "ID",
    "Дата створення",
    "Категорія",
    "Тип житла",
    "Вулиця",
    "Місто",
    "Район",
    "Переваги",
    "Оренда",
    "Депозит",
    "Комісія",
    "Паркінг",
    "Заселення від",
    "Огляди від",
    "Маклер",
    "Статус",
]

def init_excel():
    if not os.path.exists(EXCEL_FILE):
        wb = Workbook()
        ws = wb.active
        ws.append(HEADERS)
        wb.save(EXCEL_FILE)

def save_offer(data: dict) -> int:
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    offer_id = ws.max_row
    ws.append([
        offer_id,
        datetime.now().strftime("%Y-%m-%d"),
        data["category"],
        data["property_type"],
        data["street"],
        data["city"],
        data["district"],
        data["advantages"],
        data["rent"],
        data["deposit"],
        data["commission"],
        data["parking"],
        data["move_in"],
        data["viewing"],
        data["broker"],
        "Активна",
    ])
    wb.save(EXCEL_FILE)
    return offer_id

def update_status(offer_id: int, status: str):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    ws.cell(row=offer_id + 1, column=16).value = status
    wb.save(EXCEL_FILE)

def get_active_offers():
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    offers = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[15] == "Активна":
            offers.append(row)
    return offers

# =======================
# FSM
# =======================
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
    summary = State()

class CloseFSM(StatesGroup):
    offer_id = State()
    status = State()

# =======================
# KEYBOARDS
# =======================
def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Зробити пропозицію", callback_data="new_offer")],
        [InlineKeyboardButton(text="📕 Закрити / Резерв", callback_data="close_offer")],
    ])

def category_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оренда", callback_data="Оренда")],
        [InlineKeyboardButton(text="Продажа", callback_data="Продажа")],
    ])

def finish_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово / Публікувати", callback_data="publish")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")],
    ])

def close_status_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟡 Резерв", callback_data="Резерв")],
        [InlineKeyboardButton(text="🔴 Неактуальна", callback_data="Неактуальна")],
    ])

# =======================
# BOT INIT
# =======================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# =======================
# START
# =======================
@dp.message(Command("start"))
async def start(msg: Message):
    await msg.answer(
        "Вітаю 👋\nОберіть дію:",
        reply_markup=start_kb()
    )

# =======================
# NEW OFFER
# =======================
@dp.callback_query(F.data == "new_offer")
async def new_offer(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("Категорія:", reply_markup=category_kb())
    await state.set_state(OfferFSM.category)

@dp.callback_query(OfferFSM.category)
async def category(cb: CallbackQuery, state: FSMContext):
    await state.update_data(category=cb.data)
    await cb.message.answer("Тип житла:")
    await state.set_state(OfferFSM.property_type)

@dp.message(OfferFSM.property_type)
async def property_type(msg: Message, state: FSMContext):
    await state.update_data(property_type=msg.text)
    await msg.answer("Вулиця:")
    await state.set_state(OfferFSM.street)

@dp.message(OfferFSM.street)
async def street(msg: Message, state: FSMContext):
    await state.update_data(street=msg.text)
    await msg.answer("Місто:")
    await state.set_state(OfferFSM.city)

@dp.message(OfferFSM.city)
async def city(msg: Message, state: FSMContext):
    await state.update_data(city=msg.text)
    await msg.answer("Район:")
    await state.set_state(OfferFSM.district)

@dp.message(OfferFSM.district)
async def district(msg: Message, state: FSMContext):
    await state.update_data(district=msg.text)
    await msg.answer("Переваги житла:")
    await state.set_state(OfferFSM.advantages)

@dp.message(OfferFSM.advantages)
async def advantages(msg: Message, state: FSMContext):
    await state.update_data(advantages=msg.text)
    await msg.answer("Оренда (сума):")
    await state.set_state(OfferFSM.rent)

@dp.message(OfferFSM.rent)
async def rent(msg: Message, state: FSMContext):
    await state.update_data(rent=msg.text)
    await msg.answer("Депозит:")
    await state.set_state(OfferFSM.deposit)

@dp.message(OfferFSM.deposit)
async def deposit(msg: Message, state: FSMContext):
    await state.update_data(deposit=msg.text)
    await msg.answer("Комісія:")
    await state.set_state(OfferFSM.commission)

@dp.message(OfferFSM.commission)
async def commission(msg: Message, state: FSMContext):
    await state.update_data(commission=msg.text)
    await msg.answer("Паркінг:")
    await state.set_state(OfferFSM.parking)

@dp.message(OfferFSM.parking)
async def parking(msg: Message, state: FSMContext):
    await state.update_data(parking=msg.text)
    await msg.answer("Заселення від:")
    await state.set_state(OfferFSM.move_in)

@dp.message(OfferFSM.move_in)
async def move_in(msg: Message, state: FSMContext):
    await state.update_data(move_in=msg.text)
    await msg.answer("Огляди від:")
    await state.set_state(OfferFSM.viewing)

@dp.message(OfferFSM.viewing)
async def viewing(msg: Message, state: FSMContext):
    await state.update_data(viewing=msg.text)
    await msg.answer("Маклер (@нік):")
    await state.set_state(OfferFSM.broker)

@dp.message(OfferFSM.broker)
async def broker(msg: Message, state: FSMContext):
    await state.update_data(broker=msg.text)
    data = await state.get_data()

    text = "📋 ПРОПОЗИЦІЯ:\n\n"
    for k, v in data.items():
        text += f"{k}: {v}\n"

    await msg.answer(text, reply_markup=finish_kb())
    await state.set_state(OfferFSM.summary)

# =======================
# PUBLISH
# =======================
@dp.callback_query(F.data == "publish")
async def publish(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offer_id = save_offer(data)

    text = f"🆕 ПРОПОЗИЦІЯ №{offer_id}\n\n"
    for k, v in data.items():
        text += f"{k}: {v}\n"

    await bot.send_message(GROUP_CHAT_ID, text)
    await cb.message.answer("✅ Опубліковано")
    await state.clear()

@dp.callback_query(F.data == "cancel")
async def cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("❌ Скасовано")

# =======================
# CLOSE / RESERVE
# =======================
@dp.callback_query(F.data == "close_offer")
async def close_offer(cb: CallbackQuery, state: FSMContext):
    offers = get_active_offers()
    if not offers:
        await cb.message.answer("Немає активних пропозицій")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"#{o[0]} {o[4]}, {o[5]}",
            callback_data=f"close_{o[0]}"
        )] for o in offers
    ])

    await cb.message.answer("Оберіть пропозицію:", reply_markup=kb)

@dp.callback_query(F.data.startswith("close_"))
async def choose_close(cb: CallbackQuery, state: FSMContext):
    offer_id = int(cb.data.split("_")[1])
    await state.update_data(offer_id=offer_id)
    await cb.message.answer("Статус:", reply_markup=close_status_kb())
    await state.set_state(CloseFSM.status)

@dp.callback_query(CloseFSM.status)
async def set_status(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offer_id = data["offer_id"]
    status = cb.data

    update_status(offer_id, status)
    await bot.send_message(
        GROUP_CHAT_ID,
        f"⚠️ ПРОПОЗИЦІЯ №{offer_id}\nСтатус: {status}"
    )
    await cb.message.answer("Статус оновлено")
    await state.clear()

# =======================
# MAIN
# =======================
async def main():
    init_excel()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
