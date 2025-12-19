import asyncio
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message
from aiogram.filters import CommandStart

from dotenv import load_dotenv
from db import init_db, insert_offer

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN nie je nastavený")

async def main():
    init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode="Markdown")
    )

    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(message: Message):
        insert_offer("Testová ponuka")
        await message.answer("✅ Bot funguje. Ponuka uložená do DB.")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
