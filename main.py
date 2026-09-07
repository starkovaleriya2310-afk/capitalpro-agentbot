import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import db
from config import BOT_TOKEN, DATABASE_URL
from handlers import router


async def main():
    logging.basicConfig(level=logging.INFO)

    if not BOT_TOKEN:
        raise RuntimeError("AGENT_BOT_TOKEN не задан")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL не задан")

    await db.init_pool(DATABASE_URL)

    # При первом запуске база пустая - автоматически загружаем 27 объектов
    # из properties_data.py, чтобы не нужно было запускать ничего вручную.
    existing_count = await db.count_properties()
    if existing_count == 0:
        try:
            from properties_data import PROPERTIES
            for p in PROPERTIES:
                p.setdefault("status", "available")
                await db.upsert_property(p)
            logging.info("Автозагрузка: добавлено %d объектов в базу", len(PROPERTIES))
        except Exception as e:
            logging.error("Не удалось автоматически загрузить объекты: %s", e)
    else:
        logging.info("В базе уже есть %d объектов, автозагрузка пропущена", existing_count)

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
