import os
import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InputMediaPhoto,
)
from aiogram.filters import CommandStart
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage


# ----------------------------
# ENV
# ----------------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GROUP_ID_RAW = os.getenv("GROUP_ID", "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set it in environment variables.")

try:
    GROUP_ID = int(GROUP_ID_RAW)
except Exception:
    raise RuntimeError("GROUP_ID is missing or invalid. Must be an integer like -100xxxxxxxxxx.")


# ----------------------------
# Data model (in-memory)
# ----------------------------
@dataclass
class Offer:
    category: Optional[str] = None       # Оренда / Продаж
    property_type: Optional[str] = None  # Квартира / Будинок / Кімната / ...
    city_area: Optional[str] = None      # Місто / Район
    address: Optional[str] = None
    price: Optional[str] = None
    contact: Optional[str] = None
    notes: Optional[str] = None
    photos: List[str] = field(default_factory=list)  # file_id list


OFFERS: Dict[int, Offer] = {}  # user_id -> Offer


def get_offer(user_id: int) -> Offer:
    if user_id not in OFFERS:
        OFFERS[user_id] = Offer()
    return OFFERS[user_id]


def reset_offer(user_id: int) -> None:
    OFFERS[user_id] = Offer()


# ----------------------------
# FSM
# ----------------------------
class OfferFlow(StatesGroup):
    category = State()
    property_type = State()
    city_area = State()
    address = State()
    price = State()
    contact = State()
    notes = State()
    photos_collect = State()
    confirm = State()


# ----------------------------
# UI helpers
# ----------------------------
def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏠 Пропоную житло")],
            [KeyboardButton(text="🔍 Шукаю житло")],
            [KeyboardButton(text="ℹ️ Правила / Як працює")],
        ],
        resize_keyboard=True,
        selective=True,
    )


def kb_offer_category() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏠 Оренда", callback_data="offer_cat:Оренда"),
            InlineKeyboardButton(text="🏷️ Продаж", callback_data="offer_cat:Продаж"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:home")]
    ])


def kb_property_type() -> InlineKeyboardMarkup:
    types = ["Квартира", "Будинок", "Кімната", "Комерція", "Ділянка", "Інше"]
    rows = []
    for i in range(0, len(types), 2):
        row = [InlineKeyboardButton(text=types[i], callback_data=f"offer_type:{types[i]}")]
        if i + 1 < len(types):
            row.append(InlineKeyboardButton(text=types[i+1], callback_data=f"offer_type:{types[i+1]}"))
        rows.append(row)

    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:cat")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Опублікувати", callback_data="offer_confirm:publish"),
            InlineKeyboardButton(text="❌ Скасувати", callback_data="offer_confirm:cancel"),
        ],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:photos")]
    ])


def format_offer(o: Offer) -> str:
    lines = []
    lines.append("🆕 *Нове оголошення*")
    if o.category:
        lines.append(f"📌 *Категорія:* {o.category}")
    if o.property_type:
        lines.append(f"🏡 *Тип:* {o.property_type}")
    if o.city_area:
        lines.append(f"📍 *Місто/район:* {o.city_area}")
    if o.address:
        lines.append(f"🧭 *Адреса:* {o.address}")
    if o.price:
        lines.append(f"💰 *Ціна:* {o.price}")
    if o.contact:
        lines.append(f"☎️ *Контакт:* {o.contact}")
    if o.notes:
        lines.append(f"📝 *Додатково:* {o.notes}")
    if o.photos:
        lines.append(f"🖼️ *Фото:* {len(o.photos)} шт.")
    lines.append("\n#нерухомість")
    return "\n".join(lines)


# ----------------------------
# Bot setup
# ----------------------------
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    reset_offer(message.from_user.id)
    await message.answer(
        "Привіт! Я бот для публікації оголошень у вашу групу.\n"
        "Обери дію нижче 👇",
        reply_markup=main_menu_kb()
    )


@dp.message(F.text == "ℹ️ Правила / Як працює")
async def how_it_works(message: Message):
    await message.answer(
        "ℹ️ *Як працює бот*\n\n"
        "1) Натисни *🏠 Пропоную житло*\n"
        "2) Відповідай на питання (категорія, тип, адреса, ціна, контакт)\n"
        "3) Додай фото (можна кілька), потім напиши *ГОТОВО*\n"
        "4) Натисни *✅ Опублікувати* — оголошення піде у вашу групу\n\n"
        "Якщо бот не публікує — перевір, що він *адмін у групі* ✅",
        parse_mode="Markdown",
        reply_markup=main_menu_kb()
    )


@dp.message(F.text == "🔍 Шукаю житло")
async def looking(message: Message):
    await message.answer(
        "🔍 Напиши в групі, що саме шукаєш (місто/район, бюджет, тип житла).\n"
        "Або натисни *🏠 Пропоную житло*, якщо хочеш опублікувати пропозицію.",
        parse_mode="Markdown",
        reply_markup=main_menu_kb()
    )


@dp.message(F.text == "🏠 Пропоную житло")
async def start_offer(message: Message, state: FSMContext):
    reset_offer(message.from_user.id)
    await state.set_state(OfferFlow.category)
    await message.answer("Обери категорію:", reply_markup=main_menu_kb())
    await message.answer("👇", reply_markup=kb_offer_category())


# ----------------------------
# Navigation callbacks
# ----------------------------
@dp.callback_query(F.data == "nav:home")
async def nav_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    reset_offer(cb.from_user.id)
    await cb.message.answer("Головне меню 👇", reply_markup=main_menu_kb())
    await cb.answer()


@dp.callback_query(F.data == "nav:cat")
async def nav_cat(cb: CallbackQuery, state: FSMContext):
    await state.set_state(OfferFlow.category)
    await cb.message.answer("Обери категорію:", reply_markup=kb_offer_category())
    await cb.answer()


@dp.callback_query(F.data == "nav:photos")
async def nav_photos(cb: CallbackQuery, state: FSMContext):
    await state.set_state(OfferFlow.photos_collect)
    await cb.message.answer("Надішли фото (можна кілька). Коли закінчиш — напиши *ГОТОВО*.", parse_mode="Markdown")
    await cb.answer()


# ----------------------------
# Offer flow
# ----------------------------
@dp.callback_query(OfferFlow.category, F.data.startswith("offer_cat:"))
async def pick_category(cb: CallbackQuery, state: FSMContext):
    o = get_offer(cb.from_user.id)
    o.category = cb.data.split(":", 1)[1]
    await state.set_state(OfferFlow.property_type)
    await cb.message.answer(f"Категорія: *{o.category}*\nТепер обери тип:", parse_mode="Markdown")
    await cb.message.answer("👇", reply_markup=kb_property_type())
    await cb.answer()


@dp.callback_query(OfferFlow.property_type, F.data.startswith("offer_type:"))
async def pick_type(cb: CallbackQuery, state: FSMContext):
    o = get_offer(cb.from_user.id)
    o.property_type = cb.data.split(":", 1)[1]
    await state.set_state(OfferFlow.city_area)
    await cb.message.answer(f"Тип: *{o.property_type}*\n\nВведи *місто / район* (наприклад: Київ, Оболонь):", parse_mode="Markdown")
    await cb.answer()


@dp.message(OfferFlow.city_area, F.text)
async def set_city_area(message: Message, state: FSMContext):
    o = get_offer(message.from_user.id)
    o.city_area = message.text.strip()
    await state.set_state(OfferFlow.address)
    await message.answer("Введи адресу (або приблизно, без персональних даних):")


@dp.message(OfferFlow.address, F.text)
async def set_address(message: Message, state: FSMContext):
    o = get_offer(message.from_user.id)
    o.address = message.text.strip()
    await state.set_state(OfferFlow.price)
    await message.answer("Введи ціну (наприклад: 500€/міс або 120000$):")


@dp.message(OfferFlow.price, F.text)
async def set_price(message: Message, state: FSMContext):
    o = get_offer(message.from_user.id)
    o.price = message.text.strip()
    await state.set_state(OfferFlow.contact)
    await message.answer("Введи контакт (телефон або @username):")


@dp.message(OfferFlow.contact, F.text)
async def set_contact(message: Message, state: FSMContext):
    o = get_offer(message.from_user.id)
    o.contact = message.text.strip()
    await state.set_state(OfferFlow.notes)
    await message.answer("Додай коментар (умови, кількість кімнат, тварини, комунальні тощо) або напиши '-' щоб пропустити:")


@dp.message(OfferFlow.notes, F.text)
async def set_notes(message: Message, state: FSMContext):
    o = get_offer(message.from_user.id)
    txt = message.text.strip()
    o.notes = None if txt == "-" else txt
    await state.set_state(OfferFlow.photos_collect)
    await message.answer("Надішли фото (можна кілька). Коли закінчиш — напиши *ГОТОВО*.", parse_mode="Markdown")


@dp.message(OfferFlow.photos_collect, F.photo)
async def photos_collect(message: Message, state: FSMContext):
    o = get_offer(message.from_user.id)
    o.photos.append(message.photo[-1].file_id)
    await message.answer(f"✅ Фото додано ({len(o.photos)}). Надішли ще або напиши *ГОТОВО*.", parse_mode="Markdown")


@dp.message(OfferFlow.photos_collect, F.text.casefold() == "готово")
async def photos_done(message: Message, state: FSMContext):
    o = get_offer(message.from_user.id)
    await state.set_state(OfferFlow.confirm)
    await message.answer("Перевір оголошення 👇", reply_markup=main_menu_kb())
    await message.answer(format_offer(o), parse_mode="Markdown", reply_markup=kb_confirm())


@dp.message(OfferFlow.photos_collect, F.text)
async def photos_collect_text(message: Message, state: FSMContext):
    # user wrote something else while in photos state
    await message.answer("Надішли фото або напиши *ГОТОВО*.", parse_mode="Markdown")


@dp.callback_query(OfferFlow.confirm, F.data.startswith("offer_confirm:"))
async def confirm_offer(cb: CallbackQuery, state: FSMContext, bot: Bot):
    action = cb.data.split(":", 1)[1]
    o = get_offer(cb.from_user.id)

    if action == "cancel":
        await state.clear()
        reset_offer(cb.from_user.id)
        await cb.message.answer("❌ Скасовано. Повертаю в меню.", reply_markup=main_menu_kb())
        await cb.answer()
        return

    # publish
    text = format_offer(o)

    try:
        if o.photos:
            # send album first (up to 10 per media group)
            media = [InputMediaPhoto(media=pid) for pid in o.photos[:10]]
            await bot.send_media_group(chat_id=GROUP_ID, media=media)
            await bot.send_message(chat_id=GROUP_ID, text=text, parse_mode="Markdown")
        else:
            await bot.send_message(chat_id=GROUP_ID, text=text, parse_mode="Markdown")

        await cb.message.answer("✅ Опубліковано в групу!", reply_markup=main_menu_kb())
    except Exception as e:
        await cb.message.answer(
            "❌ Не зміг опублікувати в групу.\n"
            "Перевір:\n"
            "1) бот є *адміном* у групі\n"
            "2) GROUP_ID правильний\n\n"
            f"Помилка: {type(e).__name__}: {e}",
            parse_mode="Markdown",
            reply_markup=main_menu_kb()
        )

    await state.clear()
    reset_offer(cb.from_user.id)
    await cb.answer()


# ----------------------------
# Fallback: unknown messages
# ----------------------------
@dp.message()
async def fallback(message: Message):
    await message.answer("Обери дію з меню 👇", reply_markup=main_menu_kb())


# ----------------------------
# Entrypoint
# ----------------------------
async def main():
    bot = Bot(BOT_TOKEN)

    # If webhook was set earlier, remove it so polling works
    await bot.delete_webhook(drop_pending_updates=True)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
