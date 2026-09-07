"""
Разовый скрипт: переносит объекты из старого properties_data.py (список PROPERTIES)
в новую базу данных. Запустить один раз после настройки DATABASE_URL:

    python3 migrate_from_static.py

Файл properties_data.py (со списком PROPERTIES) должен лежать рядом с этим скриптом
или быть доступен по sys.path.
"""
import asyncio
import sys

import db
from config import DATABASE_URL


async def main():
    from properties_data import PROPERTIES  # noqa

    await db.init_pool(DATABASE_URL)
    for p in PROPERTIES:
        p.setdefault("status", "available")
        await db.upsert_property(p)
        print("OK:", p["id"], p["title"])
    total = await db.count_properties()
    print(f"\nГотово. Всего объектов в базе: {total}")
    await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
