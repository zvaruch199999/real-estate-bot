import os
import logging
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = os.getenv("GROUP_ID")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing in env")
if not GROUP_ID:
    raise RuntimeError("GROUP_ID is missing in env")
GROUP_ID = int(GROUP_ID)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --------- Bratislava districts (all city parts) ----------
BRATISLAVA_DISTRICTS = [
    "Staré Mesto",
    "Ružinov",
    "Nové Mesto",
    "Petržalka",
    "Karlova Ves",
    "Dúbravka",
    "Lamač",
    "Devínska Nová Ves",
    "Devín",
    "Záhorská Bystrica",
    "Vajnory",
    "Rača",
    "Vrakuňa",
    "Podunajské Biskupice",
    "Jarovce",
    "Rusovce",
    "Čunovo",
]

# --------- In-memory storage (simple) ----------
# offer_id -> {"data":..., "group_msg_id": int}
OFFERS = {}
# user_id -> {"photos": [file_id,...], "data": {...}}
USER_TEMP = {}

def now_str():
    return datetime.now().strftime("%d.%m.%Y %H:%M")


# --------- Helpers ----------
def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Я ПРОПОНУЮ ЖИТЛО", callback_data="menu:offer")],
        [InlineKeyboardButton(text="🔎 Я ШУКАЮ ЖИТЛО", callback_data="menu:search")],
    ])

def kb_categories() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🛏 Ліжко", callback_data="cat:Ліжко"),
            InlineKeyboardButton(text="🚪 Кімната", callback_data="cat:Кімната"),
        ],
        [
            InlineKeyboardButton(text="🏢 Студія", callback_data="cat:Студія"),
            InlineKeyboardButton(text="🏠 Квартира", callback_data="cat:Квартира"),
        ],
        [
            InlineKeyboardButton(text="🏡 Дім", callback_data="cat:Дім"),
        ],
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:back"),
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_yes_no(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Так", callback_data=f"{prefix}:yes"),
            InlineKeyboardButton(text="Ні", callback_data=f"{prefix}:no"),
        ]
    ])

def kb_districts(page: int = 0, per_page: int = 6) -> InlineKeyboardMarkup:
    start = page * per_page
    end = start + per_page
    items = BRATISLAVA_DISTRICTS[start:end]

    rows = [[InlineKeyboardButton(text=d, callback_data=f"dist:{d}")] for d in items]

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"distpage:{page-1}"))
    if end < len(BRATISLAVA_DISTRICTS):
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"distpage:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="✍️ Інший район", callback_data="dist:custom")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="dist:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_photos_done() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово (фото)", callback_data="photos:done")],
        [InlineKeyboardButton(text="⏭ Пропустити фото", callback_data="photos:skip")],
    ])

def kb_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Опублікувати", callback_data="confirm:publish"),
            InlineKeyboardButton(text="❌ Скасувати", callback_data="confirm:cancel"),
        ]
    ])

def kb_offer_admin(offer_id: str) -> InlineKeyboardMarkup:
    # no SMS / no ХОЧУ
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Резерв", callback_data=f"adm:reserve:{offer_id}"),
            InlineKeyboardButton(text="🟡 Здано", callback_data=f"adm:rented:{offer_id}"),
        ],
        [
            InlineKeyboardButton(text="♻️ Актив", callback_data=f"adm:active:{offer_id}"),
            InlineKeyboardButton(text="❌ Видалити", callback_data=f"adm:delete:{offer_id}"),
        ]
    ])

async def is_group_admin(user_id: int) -> bool:
    admins = await bot.get_chat_administrators(GROUP_ID)
    return any(a.user.id == user_id for a in admins)

def compact_offer_text(data: dict, status: str = "АКТИВНА") -> str:
    # Menšie rozstupy: minimum prázdnych riadkov
    parts = []
    parts.append(f"📌 STAV: {status}")
    parts.append(f"🏠 Оренда {data['category']} у Братиславі")
    parts.append(f"📍 Вул.: {data['address']}")
    parts.append(f"🗺 Район: {data['district']}")
    parts.append(f"✨ Переваги: {data['advantages']}")
    parts.append(f"💶 Оренда (з комуналкою): {data['rent']}")
    parts.append(f"💰 Депозит: {data['deposit']}")
    parts.append(f"🧾 Комісія: {data['commission']}")
    parts.append(f"🅿️ Паркування: {data['parking']}")
    parts.append(f"🐾 Улюбленець: {data['pets']}")
    parts.append(f"📅 Заселення від: {data['move_in']}")
    parts.append(f"👀 Огляди від: {data['viewing']}")
    parts.append(f"ℹ️ Деталі: {data['details']}")
    parts.append(f"👤 Маклер: Олександр")
    return "\n".join(parts)

def new_offer_id(user_id: int) -> str:
    return f"{user_id}_{int(datetime.now().timestamp())}"


# --------- FSM ----------
class OfferFlow(StatesGroup):
    category = State()
    address = State()
    district = State()
    district_custom = State()
    advantages = State()
    rent = State()
    deposit = State()
    commission = State()
    parking = State()
    pets = State()
    move_in = State()
    viewing = State()
    details = State()
    photos = State()
    confirm = State()


# --------- Handlers ----------
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Привіт! Обери дію:", reply_markup=kb_main())

@dp.callback_query(F.data == "menu:back")
async def menu_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Обери дію:", reply_markup=kb_main())
    await call.answer()

@dp.callback_query(F.data == "menu:offer")
async def menu_offer(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(OfferFlow.category)
    await call.message.edit_text("Оберіть категорію:", reply_markup=kb_categories())
    await call.answer()

@dp.callback_query(F.data == "menu:search")
async def menu_search(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Поки що робимо гілку «Пропоную житло». Потім доробимо «Шукаю житло».", reply_markup=kb_main())
    await call.answer()

@dp.callback_query(F.data.startswith("cat:"))
async def cat_pick(call: CallbackQuery, state: FSMContext):
    category = call.data.split(":", 1)[1]
    await state.update_data(category=category)
    await state.set_state(OfferFlow.address)
    await call.message.edit_text("Напишіть вулицю/адресу проживання (текстом):")
    await call.answer()

@dp.message(OfferFlow.address)
async def address_in(message: Message, state: FSMContext):
    await state.update_data(address=message.text.strip())
    await state.set_state(OfferFlow.district)
    await message.answer("В якому районі житло?", reply_markup=kb_districts(page=0))

@dp.callback_query(F.data.startswith("distpage:"))
async def dist_page(call: CallbackQuery, state: FSMContext):
    page = int(call.data.split(":", 1)[1])
    await call.message.edit_reply_markup(reply_markup=kb_districts(page=page))
    await call.answer()

@dp.callback_query(F.data == "dist:back")
async def dist_back(call: CallbackQuery, state: FSMContext):
    await state.set_state(OfferFlow.address)
    await call.message.edit_text("Напишіть вулицю/адресу проживання (текстом):")
    await call.answer()

@dp.callback_query(F.data.startswith("dist:"))
async def dist_pick(call: CallbackQuery, state: FSMContext):
    val = call.data.split(":", 1)[1]
    if val == "custom":
        await state.set_state(OfferFlow.district_custom)
        await call.message.edit_text("Напишіть район (власним текстом):")
        await call.answer()
        return

    await state.update_data(district=val)
    await state.set_state(OfferFlow.advantages)
    await call.message.edit_text("Напишіть переваги житла (текстом):")
    await call.answer()

@dp.message(OfferFlow.district_custom)
async def district_custom_in(message: Message, state: FSMContext):
    await state.update_data(district=message.text.strip())
    await state.set_state(OfferFlow.advantages)
    await message.answer("Напишіть переваги житла (текстом):")

@dp.message(OfferFlow.advantages)
async def advantages_in(message: Message, state: FSMContext):
    await state.update_data(advantages=message.text.strip())
    await state.set_state(OfferFlow.rent)
    await message.answer("Яка оренда з комуналкою? (наприклад: 750€)")

@dp.message(OfferFlow.rent)
async def rent_in(message: Message, state: FSMContext):
    await state.update_data(rent=message.text.strip())
    await state.set_state(OfferFlow.deposit)
    await message.answer("В якій сумі депозит?")

@dp.message(OfferFlow.deposit)
async def deposit_in(message: Message, state: FSMContext):
    await state.update_data(deposit=message.text.strip())
    await state.set_state(OfferFlow.commission)
    await message.answer("Яка комісія?")

@dp.message(OfferFlow.commission)
async def commission_in(message: Message, state: FSMContext):
    await state.update_data(commission=message.text.strip())
    await state.set_state(OfferFlow.parking)
    await message.answer("Є паркування?", reply_markup=kb_yes_no("parking"))

@dp.callback_query(F.data.startswith("parking:"))
async def parking_in(call: CallbackQuery, state: FSMContext):
    ans = "Так" if call.data.endswith("yes") else "Ні"
    await state.update_data(parking=ans)
    await state.set_state(OfferFlow.pets)
    await call.message.edit_text("Дозволено з улюбленцем?", reply_markup=kb_yes_no("pets"))
    await call.answer()

@dp.callback_query(F.data.startswith("pets:"))
async def pets_in(call: CallbackQuery, state: FSMContext):
    ans = "Так" if call.data.endswith("yes") else "Ні"
    await state.update_data(pets=ans)
    await state.set_state(OfferFlow.move_in)
    await call.message.edit_text("Заселення від (дата/текст):")
    await call.answer()

@dp.message(OfferFlow.move_in)
async def move_in_in(message: Message, state: FSMContext):
    await state.update_data(move_in=message.text.strip())
    await state.set_state(OfferFlow.viewing)
    await message.answer("Огляди від (дата/текст):")

@dp.message(OfferFlow.viewing)
async def viewing_in(message: Message, state: FSMContext):
    await state.update_data(viewing=message.text.strip())
    await state.set_state(OfferFlow.details)
    await message.answer("Деталі / контакт (наприклад: @username або телефон):")

@dp.message(OfferFlow.details)
async def details_in(message: Message, state: FSMContext):
    await state.update_data(details=message.text.strip())
    await state.set_state(OfferFlow.photos)

    USER_TEMP[message.from_user.id] = {"photos": []}
    await message.answer(
        "Можеш надіслати фото (до 6). Коли закінчиш — натисни ✅ Готово.\nАбо пропусти.",
        reply_markup=kb_photos_done()
    )

@dp.message(OfferFlow.photos, F.photo)
async def photo_collect(message: Message, state: FSMContext):
    uid = message.from_user.id
    USER_TEMP.setdefault(uid, {"photos": []})
    photos = USER_TEMP[uid]["photos"]
    if len(photos) >= 6:
        await message.answer("Вже є 6 фото. Натисни ✅ Готово.")
        return
    photos.append(message.photo[-1].file_id)
    await message.answer(f"Фото додано ({len(photos)}/6). Можеш ще або натисни ✅ Готово.")

@dp.callback_query(F.data.in_({"photos:done", "photos:skip"}))
async def photos_done(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = call.from_user.id

    photos = []
    if call.data == "photos:done":
        photos = USER_TEMP.get(uid, {}).get("photos", [])

    await state.update_data(_photos=photos)

    preview = compact_offer_text({**data, "details": data.get("details", "")}, status="АКТИВНА")
    await state.set_state(OfferFlow.confirm)

    # show preview to user
    await call.message.edit_text("Перевірте текст. Опублікувати?", reply_markup=kb_confirm())
    # also send preview text (compact)
    await call.message.answer(preview)
    await call.answer()

@dp.callback_query(F.data == "confirm:cancel")
async def confirm_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Скасовано. Обери дію:", reply_markup=kb_main())
    await call.answer()

@dp.callback_query(F.data == "confirm:publish")
async def confirm_publish(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = call.from_user.id
    offer_id = new_offer_id(uid)

    photos = data.get("_photos", [])
    text = compact_offer_text(data, status="АКТИВНА")

    # publish to group
    if photos:
        # send first photo with caption, others separately
        first = photos[0]
        sent = await bot.send_photo(
            chat_id=GROUP_ID,
            photo=first,
            caption=text,
            reply_markup=kb_offer_admin(offer_id),
        )
        for p in photos[1:]:
            await bot.send_photo(chat_id=GROUP_ID, photo=p)
        group_msg_id = sent.message_id
    else:
        sent = await bot.send_message(
            chat_id=GROUP_ID,
            text=text,
            reply_markup=kb_offer_admin(offer_id),
        )
        group_msg_id = sent.message_id

    OFFERS[offer_id] = {"data": data, "group_msg_id": group_msg_id}

    await state.clear()
    await call.message.edit_text("Готово ✅ Опубліковано в групу.", reply_markup=kb_main())
    await call.answer()

# --------- Admin actions on group message ----------
@dp.callback_query(F.data.startswith("adm:"))
async def admin_actions(call: CallbackQuery):
    # Only group admins can change status (your requirement: "Všetci" -> all admins)
    if not await is_group_admin(call.from_user.id):
        await call.answer("Тільки адміни групи можуть змінювати статус.", show_alert=True)
        return

    _, action, offer_id = call.data.split(":", 2)
    offer = OFFERS.get(offer_id)
    if not offer:
        await call.answer("Не знайдено (можливо старе повідомлення).", show_alert=True)
        return

    data = offer["data"]
    msg_id = offer["group_msg_id"]

    if action == "delete":
        try:
            await bot.delete_message(chat_id=GROUP_ID, message_id=msg_id)
        except Exception:
            pass
        OFFERS.pop(offer_id, None)
        await call.answer("Видалено.")
        return

    status_map = {
        "active": "АКТИВНА",
        "reserve": "РЕЗЕРВОВАНА",
        "rented": "ОРЕНДОВАНА",
    }
    status = status_map.get(action, "АКТИВНА")
    new_text = compact_offer_text(data, status=status)

    # Edit caption if it's photo message, else edit text
    try:
        if call.message.photo:
            await bot.edit_message_caption(
                chat_id=GROUP_ID,
                message_id=msg_id,
                caption=new_text,
                reply_markup=kb_offer_admin(offer_id),
            )
        else:
            await bot.edit_message_text(
                chat_id=GROUP_ID,
                message_id=msg_id,
                text=new_text,
                reply_markup=kb_offer_admin(offer_id),
            )
        await call.answer(f"Статус: {status}")
    except Exception as e:
        await call.answer("Не вдалося оновити повідомлення.", show_alert=True)


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
