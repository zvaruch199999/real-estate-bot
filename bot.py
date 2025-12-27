import asyncio
import os

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InputMediaPhoto, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


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


# ================= START =================

@dp.message(F.text == "/start")
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Вітаю 👋\n\n"
        "✍️ Напишіть:\n"
        "👉 `створити` — створити пропозицію\n"
        "👉 `скасувати` — скасувати дію",
        reply_markup=ReplyKeyboardRemove()
    )


# ================= CANCEL =================

@dp.message(F.text.lower() == "скасувати")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Дію скасовано.\n\n/start — почати знову")


# ================= CREATE =================

@dp.message(F.text.lower() == "створити")
async def create_offer(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(OfferFSM.category)
    await message.answer("Категорія (оренда / продаж):")


# ================= STEPS =================

@dp.message(OfferFSM.category)
async def s1(message: Message, state: FSMContext):
    await state.update_data(category=message.text)
    await state.set_state(OfferFSM.property_type)
    await message.answer("Тип житла:")


@dp.message(OfferFSM.property_type)
async def s2(message: Message, state: FSMContext):
    await state.update_data(property_type=message.text)
    await state.set_state(OfferFSM.street)
    await message.answer("Вулиця:")


@dp.message(OfferFSM.street)
async def s3(message: Message, state: FSMContext):
    await state.update_data(street=message.text)
    await state.set_state(OfferFSM.city)
    await message.answer("Місто:")


@dp.message(OfferFSM.city)
async def s4(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    await state.set_state(OfferFSM.district)
    await message.answer("Район:")


@dp.message(OfferFSM.district)
async def s5(message: Message, state: FSMContext):
    await state.update_data(district=message.text)
    await state.set_state(OfferFSM.advantages)
    await message.answer("Переваги:")


@dp.message(OfferFSM.advantages)
async def s6(message: Message, state: FSMContext):
    await state.update_data(advantages=message.text)
    await state.set_state(OfferFSM.rent)
    await message.answer("Ціна:")


@dp.message(OfferFSM.rent)
async def s7(message: Message, state: FSMContext):
    await state.update_data(rent=message.text)
    await state.set_state(OfferFSM.deposit)
    await message.answer("Депозит:")


@dp.message(OfferFSM.deposit)
async def s8(message: Message, state: FSMContext):
    await state.update_data(deposit=message.text)
    await state.set_state(OfferFSM.commission)
    await message.answer("Комісія:")


@dp.message(OfferFSM.commission)
async def s9(message: Message, state: FSMContext):
    await state.update_data(commission=message.text)
    await state.set_state(OfferFSM.parking)
    await message.answer("Паркінг:")


@dp.message(OfferFSM.parking)
async def s10(message: Message, state: FSMContext):
    await state.update_data(parking=message.text)
    await state.set_state(OfferFSM.move_in)
    await message.answer("Заселення:")


@dp.message(OfferFSM.move_in)
async def s11(message: Message, state: FSMContext):
    await state.update_data(move_in=message.text)
    await state.set_state(OfferFSM.viewing)
    await message.answer("Огляди:")


@dp.message(OfferFSM.viewing)
async def s12(message: Message, state: FSMContext):
    await state.update_data(viewing=message.text)
    await state.set_state(OfferFSM.broker)
    await message.answer("Маклер (нік):")


@dp.message(OfferFSM.broker)
async def s13(message: Message, state: FSMContext):
    await state.update_data(broker=message.text, photos=[], _finished=False)
    await state.set_state(OfferFSM.photos)
    await message.answer(
        "📸 Надішліть фото.\n"
        "Коли закінчите — напишіть **Готово**"
    )


# ================= PHOTOS =================

@dp.message(OfferFSM.photos, F.photo)
async def add_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    photos = data.get("photos", [])
    photos.append(message.photo[-1].file_id)
    await state.update_data(photos=photos)
    await message.answer("📷 Фото додано. Можете додати ще або написати **Готово**.")


@dp.message(OfferFSM.photos)
async def finish_offer(message: Message, state: FSMContext):
    if "готово" not in (message.text or "").lower():
        return

    data = await state.get_data()

    if data.get("_finished"):
        return

    if not data.get("photos"):
        await message.answer("⚠️ Додайте хоча б одне фото.")
        return

    await state.update_data(_finished=True)
    await state.clear()

    caption = (
        "🏠 НОВА ПРОПОЗИЦІЯ\n\n"
        f"Категорія: {data['category']}\n"
        f"Тип житла: {data['property_type']}\n"
        f"Адреса: {data['street']}, {data['city']} ({data['district']})\n"
        f"Переваги: {data['advantages']}\n"
        f"Ціна: {data['rent']}\n"
        f"Депозит: {data['deposit']}\n"
        f"Комісія: {data['commission']}\n"
        f"Паркінг: {data['parking']}\n"
        f"Заселення: {data['move_in']}\n"
        f"Огляди: {data['viewing']}\n"
        f"Маклер: {data['broker']}"
    )

    media = [
        InputMediaPhoto(p, caption=caption if i == 0 else None)
        for i, p in enumerate(data["photos"])
    ]

    await bot.send_media_group(GROUP_CHAT_ID, media)

    await message.answer("✅ Пропозицію опубліковано!\n\n/start — нова пропозиція")


# ================= MAIN =================

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
