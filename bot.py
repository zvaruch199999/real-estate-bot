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

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

# ================= FILES =================
DATA_DIR = "data"
EXCEL_FILE = f"{DATA_DIR}/offers.xlsx"
os.makedirs(DATA_DIR, exist_ok=True)

# ================= EXCEL =================
HEADERS = [
    "ID","Дата","Категорія","Тип житла","Вулиця","Місто","Район","Переваги",
    "Ціна","Депозит","Комісія","Паркінг",
    "Заселення","Огляди","Маклер",
    "Фото","Фото_IDs","Статус",
    "Хто знайшов нерухомість","Хто знайшов клієнта","Дата контракту",
    "Сума провізії","К-сть оплат","Графік оплат",
    "Клієнт","ПМЖ","Контакт"
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
    row = ws.max_row
    ws.append([
        row,
        datetime.now().strftime("%Y-%m-%d"),
        data["category"], data["property_type"],
        data["street"], data["city"], data["district"],
        data["advantages"], data["rent"], data["deposit"],
        data["commission"], data["parking"],
        data["move_in"], data["viewing"], data["broker"],
        len(data["photos"]),
        ",".join(data["photos"]),
        "Активна",
        "", "", "", "", "", "", "", "", ""
    ])
    wb.save(EXCEL_FILE)
    return row

def get_offer(row):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    return {
        "category": ws.cell(row,3).value,
        "property_type": ws.cell(row,4).value,
        "street": ws.cell(row,5).value,
        "city": ws.cell(row,6).value,
        "district": ws.cell(row,7).value,
        "rent": ws.cell(row,9).value,
        "broker": ws.cell(row,15).value,
        "photos": ws.cell(row,16).value,
    }

def update_status(row, status):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    ws.cell(row=row, column=18).value = status
    wb.save(EXCEL_FILE)

def write_deal(row, values):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    for i, v in enumerate(values, start=19):
        ws.cell(row=row, column=i).value = v
    wb.save(EXCEL_FILE)

def get_active():
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    return [
        r for r in range(2, ws.max_row + 1)
        if ws.cell(r,18).value == "Активна"
    ]

# ================= TEXT =================
def offer_text(o, status=None):
    text = (
        f"🏠 {o['property_type']}\n"
        f"📍 {o['city']}, {o['street']}\n"
        f"💰 Ціна: {o['rent']}\n"
        f"🧑‍💼 Маклер: {o['broker']}"
    )
    if status:
        text = f"{status}\n\n" + text
    return text

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
    summary = State()

class CloseFSM(StatesGroup):
    row = State()
    found_property = State()
    found_client = State()
    contract_date = State()
    commission_sum = State()
    payments_count = State()
    payments_details = State()
    client_name = State()
    residence = State()
    contact = State()
    summary = State()

# ================= KEYBOARDS =================
def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Створити пропозицію", callback_data="new")],
        [InlineKeyboardButton(text="📕 Закрити пропозицію / угоду", callback_data="close")]
    ])

def finish_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Опублікувати", callback_data="publish")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")]
    ])

def status_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🟡 Резерв", callback_data="reserve")],
        [InlineKeyboardButton(text="🔴 Неактуальна", callback_data="inactive")],
        [InlineKeyboardButton(text="🟢 Закрита угода", callback_data="deal")]
    ])

def confirm_deal_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Чудово, зберегти", callback_data="deal_ok")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="deal_cancel")]
    ])

# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(m: Message):
    await m.answer("Вітаю 👋\nОберіть дію:", reply_markup=start_kb())

# ================= CREATE OFFER =================
@dp.callback_query(F.data == "new")
async def new(cb, state: FSMContext):
    await state.clear()
    await cb.message.answer("Категорія:")
    await state.set_state(OfferFSM.category)

@dp.message(OfferFSM.category)
async def step_category(m, s): await s.update_data(category=m.text); await m.answer("Тип житла:"); await s.set_state(OfferFSM.property_type)
@dp.message(OfferFSM.property_type)
async def step_pt(m, s): await s.update_data(property_type=m.text); await m.answer("Вулиця:"); await s.set_state(OfferFSM.street)
@dp.message(OfferFSM.street)
async def step_st(m, s): await s.update_data(street=m.text); await m.answer("Місто:"); await s.set_state(OfferFSM.city)
@dp.message(OfferFSM.city)
async def step_city(m, s): await s.update_data(city=m.text); await m.answer("Район:"); await s.set_state(OfferFSM.district)
@dp.message(OfferFSM.district)
async def step_dist(m, s): await s.update_data(district=m.text); await m.answer("Переваги:"); await s.set_state(OfferFSM.advantages)
@dp.message(OfferFSM.advantages)
async def step_adv(m, s): await s.update_data(advantages=m.text); await m.answer("Ціна:"); await s.set_state(OfferFSM.rent)
@dp.message(OfferFSM.rent)
async def step_rent(m, s): await s.update_data(rent=m.text); await m.answer("Депозит:"); await s.set_state(OfferFSM.deposit)
@dp.message(OfferFSM.deposit)
async def step_dep(m, s): await s.update_data(deposit=m.text); await m.answer("Комісія:"); await s.set_state(OfferFSM.commission)
@dp.message(OfferFSM.commission)
async def step_com(m, s): await s.update_data(commission=m.text); await m.answer("Паркінг:"); await s.set_state(OfferFSM.parking)
@dp.message(OfferFSM.parking)
async def step_par(m, s): await s.update_data(parking=m.text); await m.answer("Заселення від:"); await s.set_state(OfferFSM.move_in)
@dp.message(OfferFSM.move_in)
async def step_mi(m, s): await s.update_data(move_in=m.text); await m.answer("Огляди від:"); await s.set_state(OfferFSM.viewing)
@dp.message(OfferFSM.viewing)
async def step_view(m, s): await s.update_data(viewing=m.text); await m.answer("Маклер:"); await s.set_state(OfferFSM.broker)

@dp.message(OfferFSM.broker)
async def broker(m, s):
    await s.update_data(broker=m.text, photos=[])
    await m.answer("Надішліть фото (можна кілька)")

@dp.message(OfferFSM.photos, F.photo)
async def photos(m, s):
    data = await s.get_data()
    data["photos"].append(m.photo[-1].file_id)
    await s.update_data(photos=data["photos"])
    await m.answer("Фото додано. Напишіть будь-що, коли готово")

@dp.message(OfferFSM.photos)
async def summary(m, s):
    data = await s.get_data()
    await m.answer("Опублікувати пропозицію?", reply_markup=finish_kb())
    await s.set_state(OfferFSM.summary)

@dp.callback_query(F.data == "publish")
async def publish(cb, s):
    data = await s.get_data()
    row = save_offer(data)
    text = offer_text(data)
    media = [InputMediaPhoto(p, caption=text if i == 0 else None) for i, p in enumerate(data["photos"])]
    await bot.send_media_group(GROUP_CHAT_ID, media)
    await cb.message.answer("✅ Пропозицію опубліковано")
    await s.clear()

# ================= CLOSE =================
@dp.callback_query(F.data == "close")
async def close(cb, s):
    active = get_active()
    if not active:
        await cb.message.answer("Немає активних пропозицій")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Пропозиція {r}", callback_data=f"row_{r}")]
        for r in active
    ])
    await cb.message.answer("Оберіть пропозицію:", reply_markup=kb)

@dp.callback_query(F.data.startswith("row_"))
async def choose(cb, s):
    row = int(cb.data.split("_")[1])
    await s.update_data(row=row)
    await cb.message.answer("Оберіть статус:", reply_markup=status_kb())

async def send_status(row, status_text):
    o = get_offer(row)
    photos = o["photos"].split(",")
    text = offer_text(o, status_text)
    media = [InputMediaPhoto(p, caption=text if i == 0 else None) for i, p in enumerate(photos)]
    await bot.send_media_group(GROUP_CHAT_ID, media)

@dp.callback_query(F.data == "reserve")
async def reserve(cb, s):
    row = (await s.get_data())["row"]
    update_status(row, "Резерв")
    await send_status(row, "🟡 СТАТУС: РЕЗЕРВ")
    await s.clear()

@dp.callback_query(F.data == "inactive")
async def inactive(cb, s):
    row = (await s.get_data())["row"]
    update_status(row, "Неактуальна")
    await send_status(row, "🔴 СТАТУС: НЕАКТУАЛЬНА")
    await s.clear()

@dp.callback_query(F.data == "deal")
async def deal(cb, s):
    await cb.message.answer("Хто знайшов нерухомість?")
    await s.set_state(CloseFSM.found_property)

@dp.message(CloseFSM.found_property)
async def fp(m,s): await s.update_data(found_property=m.text); await m.answer("Хто знайшов клієнта?"); await s.set_state(CloseFSM.found_client)
@dp.message(CloseFSM.found_client)
async def fc(m,s): await s.update_data(found_client=m.text); await m.answer("Дата контракту:"); await s.set_state(CloseFSM.contract_date)
@dp.message(CloseFSM.contract_date)
async def cd(m,s): await s.update_data(contract_date=m.text); await m.answer("Сума провізії:"); await s.set_state(CloseFSM.commission_sum)
@dp.message(CloseFSM.commission_sum)
async def cs(m,s): await s.update_data(commission_sum=m.text); await m.answer("К-сть оплат:"); await s.set_state(CloseFSM.payments_count)
@dp.message(CloseFSM.payments_count)
async def pc(m,s): await s.update_data(payments_count=m.text); await m.answer("Графік оплат:"); await s.set_state(CloseFSM.payments_details)
@dp.message(CloseFSM.payments_details)
async def pd(m,s): await s.update_data(payments_details=m.text); await m.answer("ПІБ клієнта:"); await s.set_state(CloseFSM.client_name)
@dp.message(CloseFSM.client_name)
async def cn(m,s): await s.update_data(client_name=m.text); await m.answer("ПМЖ клієнта:"); await s.set_state(CloseFSM.residence)
@dp.message(CloseFSM.residence)
async def rs(m,s): await s.update_data(residence=m.text); await m.answer("Контакт:"); await s.set_state(CloseFSM.contact)

@dp.message(CloseFSM.contact)
async def confirm(m,s):
    await s.update_data(contact=m.text)
    d = await s.get_data()
    text = (
        "📋 УЗАГАЛЬНЕННЯ УГОДИ\n\n"
        f"Клієнт: {d['client_name']}\n"
        f"Провізія: {d['commission_sum']}"
    )
    await m.answer(text, reply_markup=confirm_deal_kb())
    await s.set_state(CloseFSM.summary)

@dp.callback_query(F.data == "deal_ok")
async def deal_ok(cb,s):
    d = await s.get_data()
    row = d["row"]
    write_deal(row, [
        d["found_property"], d["found_client"], d["contract_date"],
        d["commission_sum"], d["payments_count"], d["payments_details"],
        d["client_name"], d["residence"], d["contact"]
    ])
    update_status(row, "Закрита угода")
    await send_status(row, "🟢 УГОДУ ЗАКРИТО")
    await cb.message.answer("✅ Угоду збережено")
    await s.clear()

@dp.callback_query(F.data == "deal_cancel")
async def deal_cancel(cb,s):
    await s.clear()
    await cb.message.answer("❌ Скасовано")

# ================= MAIN =================
async def main():
    init_excel()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
