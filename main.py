import os
from typing import List, Optional

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    InputMediaPhoto,
)
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
GROUP_ID = (os.getenv("GROUP_ID") or "").strip()

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing. Set it in Render Environment Variables.")
if " " in BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN contains spaces. Copy token again from @BotFather.")
if not GROUP_ID:
    raise RuntimeError("GROUP_ID missing. Set it in Render Environment Variables.")

GROUP_ID_INT = int(GROUP_ID)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# ---------------- Keyboards ----------------
def kb_main() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Я пропоную житло", callback_data="offer_start")],
            [InlineKeyboardButton(text="🔎 Я шукаю житло", callback_data="search_start")],
        ]
    )


def kb_offer_category() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🛏 Ліжко", callback_data="cat_bed"),
                InlineKeyboardButton(text="🛌 Кімната", callback_data="cat_room"),
            ],
            [
                InlineKeyboardButton(text="🏢 Студіо", callback_data="cat_studio"),
                InlineKeyboardButton(text="🏬 Квартира", callback_data="cat_flat"),
            ],
            [InlineKeyboardButton(text="🏡 Дім", callback_data="cat_house")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_main")],
        ]
    )


def kb_district() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Центр", callback_data="dist_center"),
                InlineKeyboardButton(text="Старе Місто", callback_data="dist_oldtown"),
            ],
            [
                InlineKeyboardButton(text="Петржалка", callback_data="dist_petrzalka"),
                InlineKeyboardButton(text="Інше (дописати)", callback_data="dist_other"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="offer_back_category")],
        ]
    )


def kb_move_in() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ Одразу", callback_data="move_now")],
            [InlineKeyboardButton(text="📅 Від дати (написати)", callback_data="move_from_date")],
            [InlineKeyboardButton(text="✍️ Свій варіант (написати)", callback_data="move_custom")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="offer_back_parking")],
        ]
    )


def kb_realtor() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Антон", callback_data="rel_anton"),
                InlineKeyboardButton(text="Юрій", callback_data="rel_yuriy"),
            ],
            [
                InlineKeyboardButton(text="Олександра", callback_data="rel_oleksandra"),
                InlineKeyboardButton(text="Ангеліна", callback_data="rel_angelina"),
            ],
            [InlineKeyboardButton(text="Лілі", callback_data="rel_lili")],
            [InlineKeyboardButton(text="✍️ Інше (написати)", callback_data="rel_other")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="offer_back_viewings")],
        ]
    )


def kb_photos() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📷 Маю фото", callback_data="photos_yes"),
                InlineKeyboardButton(text="🚫 Немає", callback_data="photos_no"),
            ],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="offer_back_realtor")],
        ]
    )


def kb_preview() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Опублікувати в групу", callback_data="publish")],
            [InlineKeyboardButton(text="✏️ Є помилка — повернутись", callback_data="fix")],
            [InlineKeyboardButton(text="🏠 В меню", callback_data="back_to_main")],
        ]
    )


def kb_post_actions(details_link: str, phone_link: Optional[str]) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text="💬 SMS", url=details_link)]
    if phone_link:
        row.append(InlineKeyboardButton(text="📞 Дзвінок", url=phone_link))
    return InlineKeyboardMarkup(
        inline_keyboard=[
            row,
            [InlineKeyboardButton(text="🙋 ХОЧУ", callback_data="i_want")],
        ]
    )


# ---------------- FSM ----------------
class OfferFlow(StatesGroup):
    category = State()
    street = State()
    district = State()
    district_other = State()
    advantages = State()
    rent = State()
    deposit = State()
    commission = State()
    parking = State()
    move_in = State()
    move_in_text = State()
    viewings = State()
    realtor = State()
    realtor_other = State()
    realtor_contact = State()
    photos_choice = State()
    photos_collect = State()
    confirm = State()


CATEGORY_MAP = {
    "cat_bed": "ліжко",
    "cat_room": "кімната",
    "cat_studio": "студіо",
    "cat_flat": "квартира",
    "cat_house": "дім",
}

DISTRICT_MAP = {
    "dist_center": "Центр",
    "dist_oldtown": "Старе Місто",
    "dist_petrzalka": "Петржалка",
}


def contact_to_links(contact: str):
    c = (contact or "").strip()
    phone_link = None
    details_link = None

    if c.startswith("@"):
        details_link = f"https://t.me/{c[1:]}"
    elif c.startswith("http://") or c.startswith("https://"):
        details_link = c
    else:
        details_link = c
        digits = "".join(ch for ch in c if ch.isdigit() or ch == "+")
        if len(digits) >= 9:
            phone_link = f"tel:{digits}"

    if not details_link:
        details_link = "https://t.me/"
    return details_link, phone_link


def format_offer_text(data: dict) -> str:
    lines = []
    lines.append(f"🏠 Оренда: {data.get('category','')}")
    lines.append(f"📍 Адреса: {data.get('street','')} ({data.get('district','')})")
    lines.append("")
    lines.append(f"✨ Переваги проживання: {data.get('advantages','')}")
    lines.append("")
    lines.append(f"💶 Оренда: {data.get('rent','')}")
    lines.append(f"🔒 Депозит: {data.get('deposit','')}")
    lines.append(f"🤝 Комісія: {data.get('commission','')}")
    lines.append("")
    lines.append(f"🅿️ Паркінг: {data.get('parking','')}")
    lines.append(f"📦 Заселення від: {data.get('move_in','')}")
    lines.append(f"👀 Огляди від: {data.get('viewings','')}")
    lines.append("")
    lines.append(f"👤 Маклер: {data.get('realtor_name','')}")
    lines.append(f"🔗 Деталі: {data.get('realtor_contact','')}")
    return "\n".join(lines).strip()


# ---------------- Handlers ----------------
@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Привіт! Обери дію 👇", reply_markup=kb_main())


@dp.callback_query(F.data == "back_to_main")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Головне меню 👇", reply_markup=kb_main())
    await call.answer()


@dp.callback_query(F.data == "search_start")
async def search_start(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.edit_text(
        "🔎 Пошук житла — додамо наступним кроком.\n"
        "Зараз працює гілка «Я пропоную житло».",
        reply_markup=kb_main(),
    )


# ---------- Offer flow ----------
@dp.callback_query(F.data == "offer_start")
async def offer_start(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(OfferFlow.category)
    await call.answer()
    await call.message.edit_text("Обери категорію житла 👇", reply_markup=kb_offer_category())


@dp.callback_query(F.data == "offer_back_category")
async def offer_back_category(call: CallbackQuery, state: FSMContext):
    await state.set_state(OfferFlow.category)
    await call.answer()
    await call.message.edit_text("Обери категорію житла 👇", reply_markup=kb_offer_category())


@dp.callback_query(F.data.startswith("cat_"))
async def offer_category(call: CallbackQuery, state: FSMContext):
    if await state.get_state() != OfferFlow.category.state:
        await call.answer()
        return
    await state.update_data(category=CATEGORY_MAP.get(call.data, ""))
    await state.set_state(OfferFlow.street)
    await call.answer()
    await call.message.edit_text("Напиши вулицю / адресу проживання ✍️")


@dp.message(OfferFlow.street)
async def offer_street(message: Message, state: FSMContext):
    await state.update_data(street=message.text.strip())
    await state.set_state(OfferFlow.district)
    await message.answer("В якому районі житло? 👇", reply_markup=kb_district())


@dp.callback_query(F.data.startswith("dist_"))
async def offer_district(call: CallbackQuery, state: FSMContext):
    if call.data == "dist_other":
        await state.set_state(OfferFlow.district_other)
        await call.answer()
        await call.message.edit_text("Напиши район (свій варіант) ✍️")
        return

    await state.update_data(district=DISTRICT_MAP.get(call.data, ""))
    await state.set_state(OfferFlow.advantages)
    await call.answer()
    await call.message.edit_text("Напиши переваги житла ✨")


@dp.message(OfferFlow.district_other)
async def offer_district_other(message: Message, state: FSMContext):
    await state.update_data(district=message.text.strip())
    await state.set_state(OfferFlow.advantages)
    await message.answer("Напиши переваги житла ✨")


@dp.message(OfferFlow.advantages)
async def offer_advantages(message: Message, state: FSMContext):
    await state.update_data(advantages=message.text.strip())
    await state.set_state(OfferFlow.rent)
    await message.answer("Яка оренда з комуналкою? 💶 (наприклад: 700€ + комунальні)")


@dp.message(OfferFlow.rent)
async def offer_rent(message: Message, state: FSMContext):
    await state.update_data(rent=message.text.strip())
    await state.set_state(OfferFlow.deposit)
    await message.answer("В якій сумі депозит? 🔒")


@dp.message(OfferFlow.deposit)
async def offer_deposit(message: Message, state: FSMContext):
    await state.update_data(deposit=message.text.strip())
    await state.set_state(OfferFlow.commission)
    await message.answer("Яка комісія? 🤝")


@dp.message(OfferFlow.commission)
async def offer_commission(message: Message, state: FSMContext):
    await state.update_data(commission=message.text.strip())
    await state.set_state(OfferFlow.parking)
    await message.answer("Паркінг? 🅿️ (напиши текстом: є/нема/ціна/умови)")


@dp.callback_query(F.data == "offer_back_parking")
async def offer_back_parking(call: CallbackQuery, state: FSMContext):
    await state.set_state(OfferFlow.parking)
    await call.answer()
    await call.message.edit_text("Паркінг? 🅿️ (напиши текстом: є/нема/ціна/умови)")


@dp.message(OfferFlow.parking)
async def offer_parking(message: Message, state: FSMContext):
    await state.update_data(parking=message.text.strip())
    await state.set_state(OfferFlow.move_in)
    await message.answer("Заселення від:", reply_markup=kb_move_in())


@dp.callback_query(F.data.in_({"move_now", "move_from_date", "move_custom"}))
async def offer_move_in_choice(call: CallbackQuery, state: FSMContext):
    if call.data == "move_now":
        await state.update_data(move_in="Одразу")
        await state.set_state(OfferFlow.viewings)
        await call.answer()
        await call.message.edit_text("Огляди від? 👀 (напиши текстом: коли/час)")
        return

    # require text input
    await state.set_state(OfferFlow.move_in_text)
    await call.answer()
    await call.message.edit_text("Напиши дату/умову заселення ✍️")


@dp.message(OfferFlow.move_in_text)
async def offer_move_in_text(message: Message, state: FSMContext):
    await state.update_data(move_in=message.text.strip())
    await state.set_state(OfferFlow.viewings)
    await message.answer("Огляди від? 👀 (напиши текстом: коли/час)")


@dp.callback_query(F.data == "offer_back_viewings")
async def offer_back_viewings(call: CallbackQuery, state: FSMContext):
    await state.set_state(OfferFlow.viewings)
    await call.answer()
    await call.message.edit_text("Огляди від? 👀 (напиши текстом: коли/час)")


@dp.message(OfferFlow.viewings)
async def offer_viewings(message: Message, state: FSMContext):
    await state.update_data(viewings=message.text.strip())
    await state.set_state(OfferFlow.realtor)
    await message.answer("Хто маклер? 👤", reply_markup=kb_realtor())


@dp.callback_query(F.data.startswith("rel_"))
async def offer_realtor(call: CallbackQuery, state: FSMContext):
    if call.data == "rel_other":
        await state.set_state(OfferFlow.realtor_other)
        await call.answer()
        await call.message.edit_text("Напиши імʼя маклера ✍️")
        return

    name_map = {
        "rel_anton": "Антон",
        "rel_yuriy": "Юрій",
        "rel_oleksandra": "Олександра",
        "rel_angelina": "Ангеліна",
        "rel_lili": "Лілі",
    }
    await state.update_data(realtor_name=name_map.get(call.data, ""))
    await state.set_state(OfferFlow.realtor_contact)
    await call.answer()
    await call.message.edit_text("Напиши контакт маклера: @username або телефон ✍️")


@dp.message(OfferFlow.realtor_other)
async def offer_realtor_other(message: Message, state: FSMContext):
    await state.update_data(realtor_name=message.text.strip())
    await state.set_state(OfferFlow.realtor_contact)
    await message.answer("Напиши контакт маклера: @username або телефон ✍️")


@dp.callback_query(F.data == "offer_back_realtor")
async def offer_back_realtor(call: CallbackQuery, state: FSMContext):
    await state.set_state(OfferFlow.realtor_contact)
    await call.answer()
    await call.message.edit_text("Напиши контакт маклера: @username або телефон ✍️")


@dp.message(OfferFlow.realtor_contact)
async def offer_realtor_contact(message: Message, state: FSMContext):
    await state.update_data(realtor_contact=message.text.strip())
    await state.set_state(OfferFlow.photos_choice)
    await message.answer("Фото є? 📸", reply_markup=kb_photos())


@dp.callback_query(F.data.in_({"photos_yes", "photos_no"}))
async def offer_photos_choice(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if call.data == "photos_no":
        await state.update_data(photo_ids=[])
        await state.set_state(OfferFlow.confirm)
        data = await state.get_data()
        await call.message.edit_text("Перевір дані 👇\n\n" + format_offer_text(data), reply_markup=kb_preview())
        return

    # photos_yes
    await state.update_data(photo_ids=[])
    await state.set_state(OfferFlow.photos_collect)
    await call.message.edit_text(
        "Надішли фото (можна кілька). Коли закінчиш — напиши: ГОТОВО ✅\n"
        "Або можеш одразу написати ГОТОВО, якщо передумав."
    )


@dp.message(OfferFlow.photos_collect)
async def offer_photos_collect(message: Message, state: FSMContext):
    text = (message.text or "").strip().lower()

    if text in {"готово", "done", "ok", "ок"}:
        await state.set_state(OfferFlow.confirm)
        data = await state.get_data()
        await message.answer("Перевір дані 👇\n\n" + format_offer_text(data), reply_markup=kb_preview())
        return

    if not message.photo:
        await message.answer("Надішли фото або напиши ГОТОВО ✅")
        return

    largest = message.photo[-1]
    data = await state.get_data()
    photo_ids = data.get("photo_ids", [])
    photo_ids.append(largest.file_id)
    await state.update_data(photo_ids=photo_ids)

    await message.answer(f"Фото додано ✅ ({len(photo_ids)})\nНадішли ще або напиши ГОТОВО.")


@dp.callback_query(F.data == "fix")
async def offer_fix(call: CallbackQuery, state: FSMContext):
    # Повертаємо на категорію (найпростіше)
    await state.set_state(OfferFlow.category)
    await call.answer()
    await call.message.edit_text("Ок, почнемо заново. Обери категорію 👇", reply_markup=kb_offer_category())


@dp.callback_query(F.data == "publish")
async def offer_publish(call: CallbackQuery, state: FSMContext):
    await call.answer()
    data = await state.get_data()

    text = format_offer_text(data)
    details_link, phone_link = contact_to_links(data.get("realtor_contact", ""))

    photo_ids: List[str] = data.get("photo_ids", []) or []

    if photo_ids:
        # send as album + caption on first photo
        media = []
        for i, pid in enumerate(photo_ids[:10]):  # Telegram album limit ~10
            media.append(InputMediaPhoto(media=pid, caption=text if i == 0 else None))
        await bot.send_media_group(chat_id=GROUP_ID_INT, media=media)
        # after album - send action buttons as separate message
        await bot.send_message(
            chat_id=GROUP_ID_INT,
            text="Дії 👇",
            reply_markup=kb_post_actions(details_link, phone_link),
        )
    else:
        await bot.send_message(
            chat_id=GROUP_ID_INT,
            text=text,
            reply_markup=kb_post_actions(details_link, phone_link),
        )

    await state.clear()
    await call.message.edit_text("✅ Опубліковано в групу! Повертаю в меню 👇", reply_markup=kb_main())


@dp.callback_query(F.data == "i_want")
async def i_want(call: CallbackQuery):
    await call.answer("✅ Дякую! Напиши маклеру через кнопки SMS/Дзвінок.", show_alert=True)


# ---------------- Run ----------------
async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
