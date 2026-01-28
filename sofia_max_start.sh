#!/bin/bash
# Отправка первого сообщения в Max через Radist API
# Использование: ./sofia_max_start.sh +79001234567

API_URL="https://api-ru.radist.online/v2"
COMPANY_ID="205054"
CONNECTION_ID="80024"
API_KEY="-cCC1Lbcwc6Et-s8mClF8_qPkE7mNF35VmTVUoZEIKYAZurc_Oyjjf2AdXTHqjvWm8cMp_U6NzJD_xNzl4jOZA"

PHONE="$1"
MESSAGE="${2:-Добрый день! Меня зовут София, я из Oazis Estate. Вы оставляли заявку на курортную недвижимость — подскажите, актуально?}"

if [ -z "$PHONE" ]; then
    echo "Использование: $0 <номер_телефона> [сообщение]"
    echo "Пример: $0 +79001234567"
    exit 1
fi

echo "📱 Создаём чат с $PHONE..."

# 1. Создаём чат
CHAT_RESPONSE=$(curl -s -X POST "$API_URL/companies/$COMPANY_ID/messaging/chats/" \
  -H "X-Api-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"connection_id\": $CONNECTION_ID, \"phone\": \"$PHONE\"}")

echo "Ответ создания чата: $CHAT_RESPONSE"

CHAT_ID=$(echo "$CHAT_RESPONSE" | grep -o '"chat_id":[0-9]*' | grep -o '[0-9]*')

if [ -z "$CHAT_ID" ]; then
    echo "❌ Не удалось создать чат"
    exit 1
fi

echo "✅ Чат создан: chat_id=$CHAT_ID"
echo "📤 Отправляем сообщение..."

# 2. Отправляем сообщение
MSG_RESPONSE=$(curl -s -X POST "$API_URL/companies/$COMPANY_ID/messaging/messages/" \
  -H "X-Api-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"connection_id\": $CONNECTION_ID,
    \"chat_id\": $CHAT_ID,
    \"message_type\": \"text\",
    \"text\": {\"text\": \"$MESSAGE\"}
  }")

echo "Ответ отправки: $MSG_RESPONSE"
echo "✅ Готово!"
