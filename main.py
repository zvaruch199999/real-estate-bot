import asyncio
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from db import init_db, create_offer
from states import OfferFlow
from keyboards import (
    start_kb,
    category_kb,
    status_kb,
    confirm_kb,
    post_status_kb
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_ID = int(os.getenv("GROUP_ID"))

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher(storage=MemoryStorage())


def format_preview(data: dict) -> str:
    return (
        "🆕 <b>Нова пропозиція</b>\n\n"
        f"🏠 <b>Тип:</b> {data['category']}\n"
        f"📍 <b>Вулиця:</b> {data['street']}\n"
        f"🗺 <b>Район:</b> {data['district']}\n"
        f"💰 <b>Ціна:</b> {data['rent']}\n"
        f"👤 <b>Маклер:</b> {data['broker']}\n\n"
        f"📌 <b>Статус:</b> {data['status']}"
    )


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вітаю! Оберіть дію:", reply_markup=start_kb())


@dp.callback_query(F.data == "offer")
async def offer_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(OfferFlow.category)
    await call.message.answer("Оберіть тип житла:", reply_markup=category_kb())
    await call.answer()


@dp.callback_query(F.data.startswith("cat:"))
async def category_step(call: CallbackQuery, state: FSMContext):
    await state.update_data(category=call.data.split(":")[1])
    await state.set_state(OfferFlow.street)
    await call.message.answer("Вкажіть вулицю:")
    await call.answer()


@dp.message(OfferFlow.street)
async def street_step(message: Message, state: FSMContext):
    await state.update_data(street=message.text)
    await state.set_state(OfferFlow.district)
    await message.answer("Вкажіть район:")


@dp.message(OfferFlow.district)
async def district_step(message: Message, state: FSMContext):
    await state.update_data(district=message.text)
    await state.set_state(OfferFlow.rent)
    await message.answer("Вкажіть ціну оренди:")


@dp.message(OfferFlow.rent)
async def rent_step(message: Message, state: FSMContext):
    await state.update_data(rent=message.text)
    await state.set_state(OfferFlow.broker)
    await message.answer("Вкажіть імʼя маклера:")


@dp.message(OfferFlow.broker)
async def broker_step(message: Message, state: FSMContext):
    await state.update_data(broker=message.text)
    await state.set_state(OfferFlow.status)
    await message.answer("Оберіть статус:", reply_markup=status_kb())


@dp.callback_query(F.data.startswith("status:"))
async def status_step(call: CallbackQuery, state: FSMContext):
    await state.update_data(status=call.data.split(":")[1])
    data = await state.get_data()
    await state.set_state(OfferFlow.confirm)
    await call.message.answer(format_preview(data), reply_markup=confirm_kb())
    await call.answer()


@dp.callback_query(F.data.startswith("confirm:"))
async def confirm_step(call: CallbackQuery, state: FSMContext):
    if call.data.endswith("no"):
        await state.clear()
        await call.message.answer("❌ Скасовано")
        await call.answer()
        return

    data = await state.get_data()
    create_offer(data)

    await bot.send_message(
        chat_id=GROUP_ID,
        text=format_preview(data),
        reply_markup=post_status_kb()
    )

    await state.clear()
    await call.message.answer("✅ Опубліковано в групу")
    await call.answer()


@dp.callback_query(F.data.startswith("post:"))
async def change_post_status(call: CallbackQuery):
    status = call.data.split(":")[1]
    text = call.message.text.split("\n\n")[0] + f"\n\n📌 <b>Статус:</b> {status}"
    await call.message.edit_text(text, reply_markup=post_status_kb())
    await call.answer("Статус оновлено")


async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
