#!/usr/bin/env python3
"""Тест умного старта диалога через Planner"""

import asyncio
import sys
sys.path.insert(0, "/opt/sofia-gpt")

from dotenv import load_dotenv
load_dotenv("/opt/sofia-gpt/.env")

from pyrogram import Client
from sofia_userbot_pyrogram import start_smart_dialog, SOFIA_AVAILABLE

API_ID = 32374021
API_HASH = "6dc50b91611d636fcc22f5ecb8c96bc6"
SESSION_NAME = "sofia_pyrogram"

async def main():
    # Импортируем app из userbot
    from sofia_userbot_pyrogram import app
    
    print(f"🔧 Sofia логика: {'✅ подключена' if SOFIA_AVAILABLE else '❌ не подключена'}")
    
    await app.start()
    me = await app.get_me()
    print(f"✅ Авторизован как: {me.first_name}")
    
    # Умный старт с указанием источника
    target = "@sergey_7in"
    lead_info = {"source": "website"}
    
    print(f"\n🚀 Запускаем start_smart_dialog для {target}...")
    result = await start_smart_dialog(target, lead_info)
    
    print(f"\n{'✅ Успешно!' if result else '❌ Ошибка'}")
    
    await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
