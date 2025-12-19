import asyncio
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from db import init_db
from states import OfferFlow
from keyboards import start_kb, category_kb, status_kb

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher(storage=MemoryStorage())


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Вітаю! Оберіть дію:",
        reply_markup=start_kb()
    )


@dp.callback_query(F.data == "offer")
async def offer_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(OfferFlow.category)
    await call.message.answer(
        "Оберіть категорію житла:",
        reply_markup=category_kb()
    )


@dp.callback_query(F.data.startswith("cat:"))
async def category_chosen(call: CallbackQuery, state: FSMContext):
    await state.update_data(category=call.data.split(":")[1])
    await state.set_state(OfferFlow.street)
    await call.message.answer("Вкажіть вулицю:")


@dp.message(OfferFlow.street)
async def street_step(message: Message, state: FSMContext):
    await state.update_data(street=message.text)
    await state.set_state(OfferFlow.status)
    await message.answer(
        "Оберіть статус пропозиції:",
        reply_markup=status_kb()
    )


@dp.callback_query(F.data.startswith("status:"))
async def status_step(call: CallbackQuery, state: FSMContext):
    await state.update_data(status=call.data.split(":")[1])
    await call.message.answer("✅ Статус збережено. Далі продовжимо…")


async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
