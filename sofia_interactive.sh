#!/bin/bash
# Интерактивный режим userbot

echo "⏸️ Останавливаю демон..."
systemctl stop sofia-userbot

echo "🚀 Запускаю интерактивный режим..."
echo "   Команды: /start @user, /send @user Текст, /quit"
echo ""

cd /opt/sofia-gpt
/opt/sofia-gpt/venv/bin/python3 sofia_userbot_pyrogram.py

echo ""
echo "▶️ Перезапускаю демон..."
systemctl start sofia-userbot
echo "✅ Демон запущен"
