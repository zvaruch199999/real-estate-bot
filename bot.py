import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from config import BOT_TOKEN, GROUP_CHAT_ID
from states import OfferFSM
from keyboards import start_kb, category_kb, finish_kb
from excel import init_excel, add_offer

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

@dp.message(F.text == "/start")
async def start(msg: Message):
    await msg.answer("Вітаю! Оберіть дію:", reply_markup=start_kb())

@dp.callback_query(F.data == "new_offer")
async def new_offer(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("Оберіть категорію:", reply_markup=category_kb())
    await state.set_state(OfferFSM.category)

@dp.callback_query(OfferFSM.category)
async def category(cb: CallbackQuery, state: FSMContext):
    await state.update_data(category=cb.data)
    await cb.message.answer("Тип житла:")
    await state.set_state(OfferFSM.property_type)

@dp.message(OfferFSM.property_type)
async def prop_type(msg: Message, state: FSMContext):
    await state.update_data(type=msg.text)
    await msg.answer("Вулиця:")
    await state.set_state(OfferFSM.street)

# ⚠️ Далі — АНАЛОГІЧНО ВСІ ПУНКТИ
# street → city → district → advantages → rent → deposit → commission
# parking → move_in → viewing → broker → photos

@dp.message(OfferFSM.summary)
async def summary(msg: Message, state: FSMContext):
    data = await state.get_data()
    text = "\n".join([f"{k}: {v}" for k, v in data.items()])
    await msg.answer(text, reply_markup=finish_kb())

@dp.callback_query(F.data == "publish")
async def publish(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    offer_id = add_offer(data)

    await bot.send_message(
        GROUP_CHAT_ID,
        f"🆕 НОВА ПРОПОЗИЦІЯ №{offer_id}\n\n" +
        "\n".join([f"{k}: {v}" for k, v in data.items()])
    )

    await cb.message.answer("✅ Опубліковано")
    await state.clear()

async def main():
    init_excel()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
