#!/bin/bash
# Быстрый старт диалога: ./sofia_start.sh @username|+phone [источник]

if [ $# -lt 1 ]; then
    echo "Использование: $0 @username|+phone [источник]"
    echo "Пример: $0 @ivan_petrov avito"
    echo "Пример: $0 +79991234567 avito"
    exit 1
fi

TARGET=$1
SOURCE=${2:-"сайте"}

echo "⏸️ Останавливаю демон..."
systemctl stop sofia-userbot
sleep 1

echo "📤 Отправляю приветствие → $TARGET"

cd /opt/sofia-gpt
/opt/sofia-gpt/venv/bin/python3 << PYTHON
import asyncio
import sys
sys.path.insert(0, '/opt/sofia-gpt')

from pyrogram import Client
from pyrogram.raw import functions, types
from state_manager import StateManager

state_manager = StateManager('/opt/sofia-gpt/sofia_gpt.db')
OBSERVER_CHAT_ID = -5206139579

async def main():
    app = Client('/opt/sofia-gpt/sofia_pyrogram', api_id=2040, api_hash='b18441a1ff607e10a989891a5462e627')
    
    async with app:
        target = "$TARGET"
        
        # Определяем тип идентификатора
        if target.startswith('+'):
            # Номер телефона — импортируем контакт
            print(f"📞 Импортирую контакт: {target}")
            phone = target.replace('+', '')
            
            result = await app.invoke(
                functions.contacts.ImportContacts(
                    contacts=[types.InputPhoneContact(
                        client_id=0,
                        phone=phone,
                        first_name="Клиент",
                        last_name=""
                    )]
                )
            )
            
            if not result.users:
                print("❌ Номер не зарегистрирован в Telegram")
                return
            
            user = result.users[0]
            user_id = user.id
            user_name = user.first_name or "друг"
        else:
            # Username
            user = await app.get_users(target)
            user_id = user.id
            user_name = user.first_name or "друг"
        
        print(f"📱 User: {user_name} (ID: {user_id})")
        
        # Сбрасываем состояние
        state_manager.reset_state(user_id)
        
        # Приветствие
        message = f"{user_name}, добрый день! Это София, по недвижимости. Вы оставляли заявку на $SOURCE — удобно сейчас пообщаться?"
        
        # Отправляем клиенту
        await app.send_message(user_id, message)
        print(f"✅ Отправлено: {message}")
        
        # Транслируем в группу
        username_str = f"@{user.username}" if hasattr(user, 'username') and user.username else f"ID:{user_id}"
        broadcast = f"🆕 НОВЫЙ ДИАЛОГ: {user_name} ({username_str})\n\n🤖 София:\n{message}"
        await app.send_message(OBSERVER_CHAT_ID, broadcast)
        print(f"📢 Транслировано в группу")

asyncio.run(main())
PYTHON

echo ""
echo "▶️ Перезапускаю демон..."
systemctl start sofia-userbot
echo "✅ Готово"
