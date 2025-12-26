import os
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.filters import Command

from openpyxl import Workbook, load_workbook

# ===================== ENV =====================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задано")

# ===================== FILES =====================
DATA_DIR = "data"
EXCEL_FILE = f"{DATA_DIR}/offers.xlsx"
os.makedirs(DATA_DIR, exist_ok=True)

# ===================== LABELS =====================
FIELD_LABELS = {
    "category": "Категорія",
    "property_type": "Тип житла",
    "street": "Вулиця",
    "city": "Місто",
    "district": "Район",
    "advantages": "Переваги",
    "rent": "Орендна плата",
    "deposit": "Депозит",
    "commission": "Комісія",
    "parking": "Паркінг",
    "move_in": "Заселення від",
    "viewing": "Огляди від",
    "broker": "Маклер",
}

def format_offer(data: dict) -> str:
    text = ""
    for k, label in FIELD_LABELS.items():
        text += f"{label}: {data.get(k, '')}\n"
    text += f"\n📸 Фото: {len(data.get('photos', []))}"
    return text

# ===================== EXCEL =====================
HEADERS = [
    "ID","Дата","Категорія","Тип","Вулиця","Місто","Район","Переваги",
    "Оренда","Депозит","Комісія","Паркінг",
    "Заселення","Огляди","Маклер","Фото","Статус",
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
        len(data["photos"]),
        "Активна",
        "", "", "", "", "", "", "", "", ""
    ])
    wb.save(EXCEL_FILE)
    return offer_id

def get_active_offers():
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    result = []
    for r in range(2, ws.max_row + 1):
        if ws.cell(r, 17).value == "Активна":
            result.append((r, ws.cell(r, 6).value, ws.cell(r, 5).value))
    return result

def set_status(row: int, status: str):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    ws.cell(row=row, column=17).value = status
    wb.save(EXCEL_FILE)

def write_deal(row: int, values: list):
    wb = load_workbook(EXCEL_FILE)
    ws = wb.active
    for i, v in enumerate(values, start=18):
        ws.cell(row=row, column=i).value = v
    wb.save(EXCEL_FILE)

# ===================== FSM =====================
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

# ===================== KEYBOARDS =====================
def start_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Створити пропозицію", callback_data="new_offer")],
        [InlineKeyboardButton(text="📕 Закрити пропозицію / угоду", callback_data="close_offer")]
    ])

def category_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оренда", callback_data="Оренда")],
        [InlineKeyboardButton(text="Продаж", callback_data="Продаж")]
    ])

def photos_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📸 Готово з фото", callback_data="photos_done")]
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

# ===================== BOT =====================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer("Вітаю 👋\nОберіть дію:", reply_markup=start_kb())

# ===================== CREATE OFFER =====================
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
    await msg.answer("Переваги:")
    await state.set_state(OfferFSM.advantages)

@dp.message(OfferFSM.advantages)
async def advantages(msg: Message, state: FSMContext):
    await state.update_data(advantages=msg.text)
    await msg.answer("Орендна плата:")
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
    await state.update_data(broker=msg.text, photos=[])
    await msg.answer("Надішліть фото:", reply_markup=photos_kb())
    await state.set_state(OfferFSM.photos)

@dp.message(OfferFSM.photos, F.photo)
async def photos(msg: Message, state: FSMContext):
    data = await state.get_data()
    photos = data["photos"]
    photos.append(msg.photo[-1].file_id)
    await state.update_data(photos=photos)
    await msg.answer(f"📸 Фото додано ({len(photos)})")

@dp.callback_query(F.data == "photos_done")
async def summary(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await cb.message.answer("📋 ПРОПОЗИЦІЯ:\n\n" + format_offer(data), reply_markup=finish_kb())
    await state.set_state(OfferFSM.summary)

@dp.callback_query(F.data == "publish")
async def publish(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offer_id = save_offer(data)
    caption = f"🆕 ПРОПОЗИЦІЯ №{offer_id}\n\n" + format_offer(data)
    media = [InputMediaPhoto(media=p, caption=caption if i == 0 else None)
             for i, p in enumerate(data["photos"])]
    if media:
        await bot.send_media_group(GROUP_CHAT_ID, media)
    else:
        await bot.send_message(GROUP_CHAT_ID, caption)
    await cb.message.answer("✅ Пропозицію опубліковано")
    await state.clear()

@dp.callback_query(F.data == "cancel")
async def cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("❌ Скасовано")

# ===================== CLOSE OFFER =====================
@dp.callback_query(F.data == "close_offer")
async def close_offer(cb: CallbackQuery, state: FSMContext):
    offers = get_active_offers()
    if not offers:
        await cb.message.answer("Немає активних пропозицій")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{city}, {street}", callback_data=f"row_{row}")]
        for row, city, street in offers
    ])
    await cb.message.answer("Оберіть пропозицію:", reply_markup=kb)

@dp.callback_query(F.data.startswith("row_"))
async def choose_status(cb: CallbackQuery, state: FSMContext):
    row = int(cb.data.split("_")[1])
    await state.update_data(offer_row=row)
    await cb.message.answer("Оберіть статус:", reply_markup=status_kb())

@dp.callback_query(F.data == "reserve")
async def reserve(cb: CallbackQuery, state: FSMContext):
    row = (await state.get_data())["offer_row"]
    set_status(row, "Резерв")
    await bot.send_message(GROUP_CHAT_ID, f"🟡 ПРОПОЗИЦІЯ №{row-1} ЗАРЕЗЕРВОВАНА")
    await state.clear()

@dp.callback_query(F.data == "inactive")
async def inactive(cb: CallbackQuery, state: FSMContext):
    row = (await state.get_data())["offer_row"]
    set_status(row, "Неактуальна")
    await bot.send_message(GROUP_CHAT_ID, f"🔴 ПРОПОЗИЦІЯ №{row-1} НЕАКТУАЛЬНА")
    await state.clear()

@dp.callback_query(F.data == "deal")
async def deal(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("Хто знайшов нерухомість?")
    await state.set_state(CloseFSM.found_property)

@dp.message(CloseFSM.found_property)
async def found_property(msg: Message, state: FSMContext):
    await state.update_data(found_property=msg.text)
    await msg.answer("Хто знайшов клієнта?")
    await state.set_state(CloseFSM.found_client)

@dp.message(CloseFSM.found_client)
async def found_client(msg: Message, state: FSMContext):
    await state.update_data(found_client=msg.text)
    await msg.answer("Дата контракту:")
    await state.set_state(CloseFSM.contract_date)

@dp.message(CloseFSM.contract_date)
async def contract_date(msg: Message, state: FSMContext):
    await state.update_data(contract_date=msg.text)
    await msg.answer("Сума провізії:")
    await state.set_state(CloseFSM.commission_sum)

@dp.message(CloseFSM.commission_sum)
async def commission_sum(msg: Message, state: FSMContext):
    await state.update_data(commission_sum=msg.text)
    await msg.answer("Кількість оплат:")
    await state.set_state(CloseFSM.payments_count)

@dp.message(CloseFSM.payments_count)
async def payments_count(msg: Message, state: FSMContext):
    await state.update_data(payments_count=msg.text)
    await msg.answer("Графік оплат:")
    await state.set_state(CloseFSM.payments_details)

@dp.message(CloseFSM.payments_details)
async def payments_details(msg: Message, state: FSMContext):
    await state.update_data(payments_details=msg.text)
    await msg.answer("ПІБ клієнта:")
    await state.set_state(CloseFSM.client_name)

@dp.message(CloseFSM.client_name)
async def client_name(msg: Message, state: FSMContext):
    await state.update_data(client_name=msg.text)
    await msg.answer("ПМЖ клієнта:")
    await state.set_state(CloseFSM.residence)

@dp.message(CloseFSM.residence)
async def residence(msg: Message, state: FSMContext):
    await state.update_data(residence=msg.text)
    await msg.answer("Контакт клієнта:")
    await state.set_state(CloseFSM.contact)

@dp.message(CloseFSM.contact)
async def finish_deal(msg: Message, state: FSMContext):
    data = await state.get_data()
    row = data["offer_row"]
    write_deal(row, [
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
    await msg.answer("✅ Угоду закрито")
    await state.clear()

# ===================== MAIN =====================
async def main():
    init_excel()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
