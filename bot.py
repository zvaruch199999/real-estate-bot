import asyncio
import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, InputMediaPhoto
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import os
import pickle

from config import BOT_TOKEN, GROUP_ID, SPREADSHEET_ID


# ================= GOOGLE SHEETS =================
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

def get_sheets():
    creds = None
    if os.path.exists("token.json"):
        with open("token.json", "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "client_secret.json", SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "wb") as f:
            pickle.dump(creds, f)

    return build("sheets", "v4", credentials=creds)


def add_to_sheet(data: dict):
    service = get_sheets()
    values = [[
        data["id"],
        data["date"],
        data["status"],
        data["type"],
        data["address"],
        data["price"],
        data["deposit"],
        data["commission"],
        data["broker"]
    ]]

    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range="A1",
        valueInputOption="RAW",
        body={"values": values}
    ).execute()


# ================= FSM =================
class CreateOffer(StatesGroup):
    photos = State()
    text = State()
    preview = State()


# ================= BOT =================
bot = Bot(BOT_TOKEN)
dp = Dispatcher()

offers = {}
counter = 1


# ================= START =================
@dp.message(Command("start"))
async def start(msg: Message):
    await msg.answer("📸 Надішли фото. Коли закінчиш — напиши /done")


# ================= COLLECT PHOTOS =================
@dp.message(F.photo)
async def collect_photos(msg: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(msg.photo[-1].file_id)
    await state.update_data(photos=photos)
    await state.set_state(CreateOffer.photos)
    await msg.answer(f"📸 Фото додано ({len(photos)})")


# ================= DONE =================
@dp.message(Command("done"))
async def done_photos(msg: Message, state: FSMContext):
    await state.set_state(CreateOffer.text)
    await msg.answer("✏️ Надішли текст пропозиції одним повідомленням")


# ================= TEXT =================
@dp.message(CreateOffer.text)
async def save_text(msg: Message, state: FSMContext):
    global counter
    data = await state.get_data()

    offer_id = f"{counter:04d}"
    counter += 1

    offer = {
        "id": offer_id,
        "photos": data["photos"],
        "text": msg.text,
        "status": "🟢 Актуально",
        "date": datetime.date.today().isoformat(),
        "type": "Кімната",
        "address": "—",
        "price": "—",
        "deposit": "—",
        "commission": "—",
        "broker": f"@{msg.from_user.username}"
    }

    offers[offer_id] = offer

    caption = f"""🏠 НОВА ПРОПОЗИЦІЯ #{offer_id}
📊 Статус: {offer['status']}

{offer['text']}

👤 Маклер: {offer['broker']}
"""

    media = [InputMediaPhoto(media=p) for p in offer["photos"]]
    media[0].caption = caption

    await bot.send_media_group(msg.chat.id, media)
    await msg.answer(
        "👇 Це фінальний вигляд. Публікувати?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Публікувати", callback_data=f"pub:{offer_id}"),
                InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")
            ]
        ])
    )

    await state.clear()


# ================= PUBLISH =================
@dp.callback_query(F.data.startswith("pub"))
async def publish(cb: CallbackQuery):
    offer_id = cb.data.split(":")[1]
    offer = offers[offer_id]

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🟢 Актуально", callback_data=f"status:active:{offer_id}"),
            InlineKeyboardButton(text="🟡 Резерв", callback_data=f"status:reserve:{offer_id}")
        ],
        [
            InlineKeyboardButton(text="🔴 Неактуально", callback_data=f"status:inactive:{offer_id}"),
            InlineKeyboardButton(text="✅ Закрити угоду", callback_data=f"close:{offer_id}")
        ]
    ])

    media = [InputMediaPhoto(media=p) for p in offer["photos"]]
    media[0].caption = f"""🏠 ПРОПОЗИЦІЯ #{offer_id}
📊 Статус: {offer['status']}

{offer['text']}

👤 Маклер: {offer['broker']}
"""

    await bot.send_media_group(GROUP_ID, media)
    await bot.send_message(GROUP_ID, "🔧 Керування статусом:", reply_markup=kb)

    add_to_sheet(offer)

    await cb.message.answer(f"✅ Пропозицію #{offer_id} опубліковано")
    await cb.answer()


# ================= STATUS =================
@dp.callback_query(F.data.startswith("status"))
async def status_change(cb: CallbackQuery):
    _, status, offer_id = cb.data.split(":")
    statuses = {
        "active": "🟢 Актуально",
        "reserve": "🟡 Резерв",
        "inactive": "🔴 Неактуально"
    }
    offers[offer_id]["status"] = statuses[status]
    await cb.answer(f"Статус: {statuses[status]}")


# ================= CLOSE =================
@dp.callback_query(F.data.startswith("close"))
async def close_deal(cb: CallbackQuery):
    offer_id = cb.data.split(":")[1]
    offers[offer_id]["status"] = "✅ Закрито"
    await cb.message.edit_reply_markup()
    await cb.answer("Угоду закрито")


# ================= MAIN =================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
