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
from keyboards import start_kb, category_kb, status_kb, confirm_kb

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN nie je nastavený")

GROUP_ID = os.getenv("GROUP_ID")
if not GROUP_ID:
    raise RuntimeError("GROUP_ID nie je nastavený")

GROUP_ID = int(GROUP_ID)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher(storage=MemoryStorage())

def render_preview(data: dict) -> str:
    status_map = {
        "active": "🟢 АКТУАЛЬНА",
        "reserved": "🟡 РЕЗЕРВОВАНА",
        "inactive": "🔴 НЕАКТУАЛЬНА",
    }

    return (
        "<b>🏠 Нова пропозиція</b>\n\n"
        f"<b>Тип:</b> {data.get('category','')}\n"
        f"<b>Вулиця:</b> {data.get('street','')}\n"
        f"<b>Статус:</b> {status_map.get(data.get('status'))}"
    )

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
    await call.answer()


@dp.callback_query(F.data.startswith("cat:"))
async def category_chosen(call: CallbackQuery, state: FSMContext):
    await state.update_data(category=call.data.split(":")[1])
    await state.set_state(OfferFlow.street)
    await call.message.answer("Вкажіть вулицю:")
    await call.answer()


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
    await call.answer()


async def main():
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
