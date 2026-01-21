#!/bin/bash
# Умный старт диалога через userbot
# Использование: ./sofia_start.sh @username [источник]

if [ -z "$1" ]; then
    echo "Использование: ./sofia_start.sh @username [источник]"
    echo "Пример: ./sofia_start.sh @sergey_7in avito"
    exit 1
fi

TARGET=$1
SOURCE=$2

echo "🛑 Останавливаю daemon..."
systemctl stop sofia-userbot

echo "🚀 Запускаю smart start для $TARGET..."
cd /opt/sofia-gpt

if [ -z "$SOURCE" ]; then
    ./venv/bin/python -c "
import asyncio
from sofia_userbot_pyrogram import app, start_smart_dialog

async def run():
    await app.start()
    await start_smart_dialog('$TARGET')
    await app.stop()

asyncio.run(run())
"
else
    ./venv/bin/python -c "
import asyncio
from sofia_userbot_pyrogram import app, start_smart_dialog

async def run():
    await app.start()
    await start_smart_dialog('$TARGET', {'source': '$SOURCE'})
    await app.stop()

asyncio.run(run())
"
fi

echo "🔄 Запускаю daemon обратно..."
systemctl start sofia-userbot

echo "✅ Готово! Daemon снова работает."
