import os
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InputMediaPhoto,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from openpyxl import Workbook, load_workbook

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# =========================
# ПРОСТА ПАМʼЯТЬ
# =========================
user_data = {}
user_photos = {}

FIELDS = [
    ("category", "Категорія"),
    ("type", "Тип житла"),
    ("street", "Вулиця"),
    ("city", "Місто"),
    ("district", "Район"),
    ("price", "Ціна"),
    ("deposit", "Депозит"),
    ("commission", "Комісія"),
    ("parking", "Паркінг (Є / Нема)"),
    ("move_in", "Заселення (Вже / Пізніше)"),
    ("views", "Огляди (Вже / Пізніше)"),
    ("broker", "Маклер (нік)")
]

# =========================
# ЛІЧИЛЬНИК ПРОПОЗИЦІЙ
# =========================
COUNTER_FILE = "counter.txt"

def get_next_offer_id() -> int:
    if not os.path.exists(COUNTER_FILE):
        with open(COUNTER_FILE, "w") as f:
            f.write("1")
        return 1

    with open(COUNTER_FILE, "r+") as f:
        num = int(f.read())
        f.seek(0)
        f.write(str(num + 1))
        f.truncate()
        return num

# =========================
# КНОПКИ СТАТУСУ
# =========================
def status_kb(offer_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Актуально", callback_data=f"status:{offer_id}:active"),
            InlineKeyboardButton(text="🟡 Резерв", callback_data=f"status:{offer_id}:reserved"),
            InlineKeyboardButton(text="🔴 Неактуально", callback_data=f"status:{offer_id}:inactive")
        ],
        [
            InlineKeyboardButton(text="✅ Закрити угоду", callback_data=f"deal:{offer_id}")
        ]
    ])

# =========================
# /start
# =========================
@dp.message(Command("start"))
async def start(msg: Message):
    user_data[msg.from_user.id] = {}
    user_photos[msg.from_user.id] = []

    await msg.answer(
        "🏠 **Створення нової пропозиції**\n\n"
        "Відповідайте на питання по черзі.",
        parse_mode="Markdown"
    )

    key, label = FIELDS[0]
    await msg.answer(f"🏷 {label}:")

# =========================
# ЗБІР ТЕКСТУ
# =========================
@dp.message(F.text)
async def collect_fields(msg: Message):
    uid = msg.from_user.id

    if uid not in user_data:
        return

    if msg.text.lower() == "/done":
        if not user_photos[uid]:
            await msg.answer("❗ Додайте хоча б одне фото")
            return
        await publish_offer(uid, msg)
        return

    data = user_data[uid]

    if len(data) < len(FIELDS):
        key, _ = FIELDS[len(data)]
        data[key] = msg.text

        if len(data) < len(FIELDS):
            next_label = FIELDS[len(data)][1]
            await msg.answer(f"➡️ {next_label}:")
        else:
            await msg.answer(
                "📸 Надішліть фото.\n"
                "Коли завершите — напишіть команду:\n"
                "`/done`",
                parse_mode="Markdown"
            )

# =========================
# ЗБІР ФОТО
# =========================
@dp.message(F.photo)
async def collect_photos(msg: Message):
    uid = msg.from_user.id
    if uid not in user_photos:
        return

    user_photos[uid].append(msg.photo[-1].file_id)
    await msg.answer(f"📷 Фото додано ({len(user_photos[uid])})")

# =========================
# ПУБЛІКАЦІЯ
# =========================
async def publish_offer(uid: int, msg: Message):
    data = user_data[uid]
    photos = user_photos[uid]
    offer_id = get_next_offer_id()

    text = (
        f"🏠 **НОВА ПРОПОЗИЦІЯ #{offer_id:04d}**\n"
        f"📊 Статус: 🟢 Актуально\n\n"
        f"🏷 Категорія: {data['category']}\n"
        f"🏠 Тип: {data['type']}\n"
        f"📍 Адреса: {data['street']}, {data['city']}\n"
        f"🗺 Район: {data['district']}\n"
        f"💰 Ціна: {data['price']}\n"
        f"🔐 Депозит: {data['deposit']}\n"
        f"🤝 Комісія: {data['commission']}\n"
        f"🚗 Паркінг: {data['parking']}\n"
        f"🚪 Заселення: {data['move_in']}\n"
        f"👀 Огляди: {data['views']}\n"
        f"👤 Маклер: {data['broker']}"
    )

    media = [InputMediaPhoto(media=photos[0])]
    for p in photos[1:]:
        media.append(InputMediaPhoto(media=p))

    album = await bot.send_media_group(GROUP_CHAT_ID, media)

    await bot.send_message(
        GROUP_CHAT_ID,
        text,
        parse_mode="Markdown",
        reply_markup=status_kb(offer_id),
        reply_to_message_id=album[0].message_id
    )

    await msg.answer(f"✅ Пропозицію #{offer_id:04d} опубліковано")

    user_data.pop(uid, None)
    user_photos.pop(uid, None)

# =========================
# СТАТУСИ
# =========================
@dp.callback_query(F.data.startswith("status:"))
async def change_status(cb: CallbackQuery):
    _, offer_id, status = cb.data.split(":")

    map_status = {
        "active": "🟢 Актуально",
        "reserved": "🟡 Резерв",
        "inactive": "🔴 Неактуально"
    }

    lines = cb.message.text.splitlines()
    lines[1] = f"📊 Статус: {map_status[status]}"

    await cb.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=status_kb(int(offer_id))
    )
    await cb.answer("Статус оновлено")

# =========================
# ЗАКРИТТЯ + EXCEL
# =========================
@dp.callback_query(F.data.startswith("deal:"))
async def close_deal(cb: CallbackQuery):
    offer_id = cb.data.split(":")[1]
    save_to_excel(offer_id, cb.message.text)

    await cb.message.edit_text(
        cb.message.text.replace("📊 Статус:", "📊 Статус: ✅ Закрито"),
        parse_mode="Markdown"
    )
    await cb.answer("Угоду закрито")

def save_to_excel(offer_id: str, text: str):
    file = "deals.xlsx"

    if not os.path.exists(file):
        wb = Workbook()
        ws = wb.active
        ws.append(["Дата", "ID", "Дані"])
        wb.save(file)

    wb = load_workbook(file)
    ws = wb.active
    ws.append([datetime.now().strftime("%Y-%m-%d %H:%M"), offer_id, text])
    wb.save(file)

# =========================
# START
# =========================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
