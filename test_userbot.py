#!/usr/bin/env python3
"""Тестовый запуск userbot — отправка первого сообщения"""

import asyncio
import os
import sys

SOFIA_PATH = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SOFIA_PATH)

from pyrogram import Client

API_ID = 32374021
API_HASH = "6dc50b91611d636fcc22f5ecb8c96bc6"
SESSION_NAME = "sofia_pyrogram"


async def main():
    app = Client(SESSION_NAME, api_id=API_ID, api_hash=API_HASH, workdir=SOFIA_PATH)

    await app.start()
    me = await app.get_me()
    print(f"✅ Авторизован как: {me.first_name} (@{me.username or 'нет'})")

    # Отправляем тестовое сообщение
    target = "@sergey_7in"
    message = "Привет! Это тестовое сообщение от Sofia Userbot 🙂"

    try:
        await app.send_message(target, message)
        print(f"✅ Отправлено → {target}")
    except Exception as e:
        print(f"❌ Ошибка: {e}")

    await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
