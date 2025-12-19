import os
import sqlite3
import asyncio
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage


# ======================
# ENV
# ======================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))
APP_TITLE = os.getenv("APP_TITLE", "ORENDA SK")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing")
if not GROUP_ID:
    raise RuntimeError("GROUP_ID missing")


# ======================
# DATABASE
# ======================
DB_PATH = "offers.db"

def db():
    return sqlite3.connect(DB_PATH)

def init_db():
    con = db()
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            created_by INTEGER NOT NULL,
            created_by_name TEXT,
            category TEXT NOT NULL,
            district TEXT NOT NULL,
            address TEXT NOT NULL,
            price TEXT NOT NULL,
            contact TEXT NOT NULL,
            description TEXT,
            photos TEXT,
            status TEXT NOT NULL,
            group_message_id INTEGER
        )
    """)
    con.commit()
    con.close()

def insert_offer(data: dict) -> int:
    con = db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO offers (
            created_at,
            created_by,
            created_by_name,
            category,
            district,
            address,
            price,
            contact,
            description,
            photos,
            status,
            group_message_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        datetime.utcnow().isoformat(),
        data["created_by"],
        data["created_by_name"],
        data["category"],
        data["district"],
        data["address"],
        data["price"],
        data["contact"],
        data.get("description"),
        ",".join(data.get("photos", [])),
        "active",
        None
    ))
    con.commit()
    oid = cur.lastrowid
    con.close()
    return oid

def get_offer(oid: int) -> Optional[dict]:
    con = db()
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    cur.execute("SELECT * FROM offers WHERE id=?", (oid,))
    row = cur.fetchone()
    con.close()
    return dict(row) if row else None

def update_offer(oid: int, fields: dict):
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [oid]
    con = db()
    cur = con.cursor()
    cur.execute(f"UPDATE offers SET {keys} WHERE id=?", vals)
    con.commit()
    con.close()


# ======================
# UI
# ======================
def kb_main():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Pridať ponuku", callback_data="new_offer")],
        [InlineKeyboardButton(text="ℹ️ Pomoc", callback_data="help")]
    ])

def kb_categories():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Kvarter", callback_data="cat:Kvarter")],
        [InlineKeyboardButton(text="Dom", callback_data="cat:Dom")],
        [InlineKeyboardButton(text="Izba", callback_data="cat:Izba")]
    ])

def kb_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Publikovať", callback_data="publish")],
        [InlineKeyboardButton(text="❌ Zrušiť", callback_data="cancel")]
    ])

def kb_status(oid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢", callback_data=f"st:{oid}:active"),
            InlineKeyboardButton(text="🔴", callback_data=f"st:{oid}:inactive")
        ]
    ])

def render_offer(o: dict) -> str:
    return (
        f"🏠 **Ponuka #{o['id']}**\n"
        f"📌 Typ: {o['category']}\n"
        f"📍 Lokalita: {o['district']}\n"
        f"📍 Adresa: {o['address']}\n"
        f"💶 Cena: {o['price']}\n"
        f"☎️ Kontakt: {o['contact']}\n\n"
        f"📝 {o.get('description', '')}"
    )


# ======================
# FSM
# ======================
class OfferFlow(StatesGroup):
    category = State()
    district = State()
    address = State()
    price = State()
    contact = State()
    description = State()
    photos = State()
    confirm = State()


# ======================
# BOT
# ======================
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="Markdown")
)
dp = Dispatcher(storage=MemoryStorage())


@dp.message(CommandStart())
async def start(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(f"👋 Vitaj v **{APP_TITLE}**", reply_markup=kb_main())


@dp.callback_query(F.data == "help")
async def help_cb(c: CallbackQuery):
    await c.message.answer(
        "Tento bot slúži na pridávanie ponúk bývania.\n\n"
        "1️⃣ Vyplň formulár\n"
        "2️⃣ Skontroluj\n"
        "3️⃣ Publikuj do skupiny",
        reply_markup=kb_main()
    )
    await c.answer()


@dp.callback_query(F.data == "new_offer")
async def new_offer(c: CallbackQuery, state: FSMContext):
    await state.set_state(OfferFlow.category)
    await c.message.answer("🏷 Vyber typ:", reply_markup=kb_categories())
    await c.answer()


@dp.callback_query(OfferFlow.category, F.data.startswith("cat:"))
async def category_step(c: CallbackQuery, state: FSMContext):
    await state.update_data(category=c.data.split(":")[1])
    await state.set_state(OfferFlow.district)
    await c.message.answer("📍 Lokalita:")
    await c.answer()


@dp.message(OfferFlow.district)
async def district_step(m: Message, state: FSMContext):
    await state.update_data(district=m.text)
    await state.set_state(OfferFlow.address)
    await m.answer("📌 Adresa:")


@dp.message(OfferFlow.address)
async def address_step(m: Message, state: FSMContext):
    await state.update_data(address=m.text)
    await state.set_state(OfferFlow.price)
    await m.answer("💶 Cena:")


@dp.message(OfferFlow.price)
async def price_step(m: Message, state: FSMContext):
    await state.update_data(price=m.text)
    await state.set_state(OfferFlow.contact)
    await m.answer("☎️ Kontakt:")


@dp.message(OfferFlow.contact)
async def contact_step(m: Message, state: FSMContext):
    await state.update_data(contact=m.text)
    await state.set_state(OfferFlow.description)
    await m.answer("📝 Popis (alebo '-'):")


@dp.message(OfferFlow.description)
async def description_step(m: Message, state: FSMContext):
    desc = "" if m.text.strip() == "-" else m.text
    await state.update_data(description=desc, photos=[])
    await state.set_state(OfferFlow.photos)
    await m.answer("📸 Pošli fotky alebo napíš 'hotovo'")


@dp.message(OfferFlow.photos, F.photo)
async def photos_step(m: Message, state: FSMContext):
    data = await state.get_data()
    data["photos"].append(m.photo[-1].file_id)
    await state.update_data(photos=data["photos"])


@dp.message(OfferFlow.photos, F.text.casefold() == "hotovo")
async def photos_done(m: Message, state: FSMContext):
    data = await state.get_data()
    preview = {
        "id": 0,
        **data
    }
    await state.set_state(OfferFlow.confirm)
    await m.answer(render_offer(preview), reply_markup=kb_confirm())


@dp.callback_query(OfferFlow.confirm, F.data == "cancel")
async def cancel(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.answer("❌ Zrušené", reply_markup=kb_main())
    await c.answer()


@dp.callback_query(OfferFlow.confirm, F.data == "publish")
async def publish(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    data["created_by"] = c.from_user.id
    data["created_by_name"] = c.from_user.full_name

    oid = insert_offer(data)
    offer = get_offer(oid)

    if offer["photos"]:
        msg = await bot.send_photo(
            GROUP_ID,
            offer["photos"].split(",")[0],
            caption=render_offer(offer),
            reply_markup=kb_status(oid)
        )
    else:
        msg = await bot.send_message(
            GROUP_ID,
            render_offer(offer),
            reply_markup=kb_status(oid)
        )

    update_offer(oid, {"group_message_id": msg.message_id})
    await state.clear()
    await c.message.answer("✅ Publikované", reply_markup=kb_main())
    await c.answer()


@dp.callback_query(F.data.startswith("st:"))
async def change_status(c: CallbackQuery):
    _, oid, status = c.data.split(":")
    update_offer(int(oid), {"status": status})
    offer = get_offer(int(oid))
    await c.message.edit_text(render_offer(offer), reply_markup=kb_status(int(oid)))
    await c.answer("OK")


# ======================
# RUN
# ======================
async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
