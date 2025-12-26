import os
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command

from openpyxl import Workbook, load_workbook

# =========================
# ENV
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задано")

# =========================
# FILES
# =========================
DATA_DIR = "data"
EXCEL_FILE = f"{DATA_DIR}/offers.xlsx"
os.makedirs(DATA_DIR, exist_ok=True)

# =========================
# EXCEL HEADERS
# =========================
HEADERS = [
    "ID",
    "Дата створення",
    "Категорія",
    "Тип житла",
    "Вулиця",
    "Місто",
    "Район",
    "Переваги",
    "Орендна плата",
    "Депозит",
    "Комісія",
    "Паркінг",
    "Заселення від",
    "Огляди від",
    "Маклер",
    "Кількість фото",
    "Статус",

    # ДАНІ УГОДИ
    "Хто знайшов нерухомість",
    "Хто знайшов клієнта",
    "Дата підписання контракту",
    "Сума провізії",
    "Кількість оплат",
    "Графік оплат",
    "Клієнт (ПІБ)",
    "ПМЖ клієнта",
    "Контакт клієнта",
]

def init_excel():
    if not os.path.exists(EXCEL_FILE):
        wb = Workbook()
        ws = wb.active
        ws.append(HEADERS)
        wb.save(EXCEL_FILE)

def set_status(row: int, status: str):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    ws.cell(row=row, column=17).value = status
    wb.save(EXCEL_FILE)

def write_deal_data(row: int, values: list):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    for i, val in enumerate(values, start=18):
        ws.cell(row=row, column=i).value = val
    wb.save(EXCEL_FILE)

def get_active_offers():
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    offers = []
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, 17).value == "Активна":
            street = ws.cell(r, 5).value
            city = ws.cell(r, 6).value
            offers.append((r, street, city))
    return offers

# =========================
# FSM — ЗАКРИТТЯ УГОДИ
# =========================
class CloseDealFSM(StatesGroup):
    offer_row = State()
    found_property = State()
    found_client = State()
    contract_date = State()
    commission_sum = State()
    payments_count = State()
    payments_details = State()
    client_name = State()
    residence = State()
    contact = State()

# =========================
# KEYBOARDS
# =========================
def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📕 Закрити пропозицію / угоду", callback_data="close_offer")]
    ])

def status_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟡 Резерв", callback_data="reserve")],
        [InlineKeyboardButton(text="🔴 Неактуальна", callback_data="inactive")],
        [InlineKeyboardButton(text="🟢 Закрита угода", callback_data="deal")],
    ])

# =========================
# BOT
# =========================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# =========================
# START
# =========================
@dp.message(Command("start"))
async def start(msg: Message):
    await msg.answer(
        "Вітаю 👋\nОберіть дію:",
        reply_markup=start_kb()
    )

# =========================
# ВИБІР ПРОПОЗИЦІЇ
# =========================
@dp.callback_query(F.data == "close_offer")
async def choose_offer(cb: CallbackQuery, state: FSMContext):
    offers = get_active_offers()
    if not offers:
        await cb.message.answer("Немає активних пропозицій")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"{city}, {street}",
            callback_data=f"offer_{row}"
        )] for row, street, city in offers
    ])

    await cb.message.answer("Оберіть пропозицію:", reply_markup=kb)

@dp.callback_query(F.data.startswith("offer_"))
async def choose_status(cb: CallbackQuery, state: FSMContext):
    row = int(cb.data.split("_")[1])
    await state.update_data(offer_row=row)
    await cb.message.answer("Оберіть новий статус:", reply_markup=status_kb())

# =========================
# РЕЗЕРВ / НЕАКТУАЛЬНА
# =========================
@dp.callback_query(F.data == "reserve")
async def reserve(cb: CallbackQuery, state: FSMContext):
    row = (await state.get_data())["offer_row"]
    set_status(row, "Резерв")
    await bot.send_message(
        GROUP_CHAT_ID,
        f"🟡 ПРОПОЗИЦІЯ №{row-1} ЗАРЕЗЕРВОВАНА"
    )
    await state.clear()

@dp.callback_query(F.data == "inactive")
async def inactive(cb: CallbackQuery, state: FSMContext):
    row = (await state.get_data())["offer_row"]
    set_status(row, "Неактуальна")
    await bot.send_message(
        GROUP_CHAT_ID,
        f"🔴 ПРОПОЗИЦІЯ №{row-1} НЕАКТУАЛЬНА"
    )
    await state.clear()

# =========================
# ЗАКРИТА УГОДА (FSM)
# =========================
@dp.callback_query(F.data == "deal")
async def deal_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("Хто знайшов нерухомість?")
    await state.set_state(CloseDealFSM.found_property)

@dp.message(CloseDealFSM.found_property)
async def found_property(msg: Message, state: FSMContext):
    await state.update_data(found_property=msg.text)
    await msg.answer("Хто знайшов клієнта?")
    await state.set_state(CloseDealFSM.found_client)

@dp.message(CloseDealFSM.found_client)
async def found_client(msg: Message, state: FSMContext):
    await state.update_data(found_client=msg.text)
    await msg.answer("Дата підписання контракту:")
    await state.set_state(CloseDealFSM.contract_date)

@dp.message(CloseDealFSM.contract_date)
async def contract(msg: Message, state: FSMContext):
    await state.update_data(contract_date=msg.text)
    await msg.answer("Сума провізії:")
    await state.set_state(CloseDealFSM.commission_sum)

@dp.message(CloseDealFSM.commission_sum)
async def commission_sum(msg: Message, state: FSMContext):
    await state.update_data(commission_sum=msg.text)
    await msg.answer("На скільки оплат розбита комісія?")
    await state.set_state(CloseDealFSM.payments_count)

@dp.message(CloseDealFSM.payments_count)
async def payments_count(msg: Message, state: FSMContext):
    await state.update_data(payments_count=msg.text)
    await msg.answer("Графік оплат (дати + суми):")
    await state.set_state(CloseDealFSM.payments_details)

@dp.message(CloseDealFSM.payments_details)
async def payments_details(msg: Message, state: FSMContext):
    await state.update_data(payments_details=msg.text)
    await msg.answer("ПІБ клієнта (за паспортом):")
    await state.set_state(CloseDealFSM.client_name)

@dp.message(CloseDealFSM.client_name)
async def client_name(msg: Message, state: FSMContext):
    await state.update_data(client_name=msg.text)
    await msg.answer("ПМЖ клієнта:")
    await state.set_state(CloseDealFSM.residence)

@dp.message(CloseDealFSM.residence)
async def residence(msg: Message, state: FSMContext):
    await state.update_data(residence=msg.text)
    await msg.answer("Контакт клієнта:")
    await state.set_state(CloseDealFSM.contact)

@dp.message(CloseDealFSM.contact)
async def finish_deal(msg: Message, state: FSMContext):
    data = await state.get_data()
    row = data["offer_row"]

    write_deal_data(row, [
        data["found_property"],
        data["found_client"],
        data["contract_date"],
        data["commission_sum"],
        data["payments_count"],
        data["payments_details"],
        data["client_name"],
        data["residence"],
        data["contact"],
    ])

    set_status(row, "Закрита угода")

    await bot.send_message(
        GROUP_CHAT_ID,
        f"🟢 ПРОПОЗИЦІЯ №{row-1} ЗАКРИТА\n"
        f"Клієнт: {data['client_name']}\n"
        f"Провізія: {data['commission_sum']}"
    )

    await msg.answer("✅ Угоду закрито та збережено")
    await state.clear()

# =========================
# MAIN
# =========================
async def main():
    init_excel()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
