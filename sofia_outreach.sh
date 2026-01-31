#!/bin/bash
# Sofia Outreach — проактивная отправка через Radist
# Использование:
#   ./sofia_outreach.sh telegram @username [Имя]
#   ./sofia_outreach.sh max 79001234567 [Имя]

API_KEY="-cCC1Lbcwc6Et-s8mClF8_qPkE7mNF35VmTVUoZEIKYAZurc_Oyjjf2AdXTHqjvWm8cMp_U6NzJD_xNzl4jOZA"
COMPANY_ID="205054"
BASE_URL="https://api-ru.radist.online/v2/companies/$COMPANY_ID"
DB_PATH="/opt/sofia-gpt/sofia_gpt.db"

# Connection IDs
TG_CONNECTION=80200
MAX_CONNECTION=80024

# Observer group
OBSERVER_CHAT_ID="-5206139579"
TG_BOT_TOKEN="8409538626:AAGqB4bkk81dCZutNmLfTd95mi_4Ky19U5M"

CHANNEL=$1
TARGET=$2
NAME=$3

if [ -z "$CHANNEL" ] || [ -z "$TARGET" ]; then
    echo "❌ Использование:"
    echo "   $0 telegram @username [Имя]"
    echo "   $0 max 79001234567 [Имя]"
    echo ""
    echo "Примеры:"
    echo "   $0 telegram @ivan_petrov Иван"
    echo "   $0 max 79161234567"
    exit 1
fi

# Шаблон приветствия
if [ -n "$NAME" ]; then
    MESSAGE="$NAME, добрый день! Это София, по недвижимости. Вы оставляли заявку на сайте — удобно сейчас пообщаться?"
else
    MESSAGE="Добрый день! Это София, по недвижимости. Вы оставляли заявку на сайте — удобно сейчас пообщаться?"
fi

save_to_db() {
    local channel="$1"
    local connection_id="$2"
    local chat_id="$3"
    local contact_id="$4"
    local phone="$5"
    local message="$6"
    
    sqlite3 "$DB_PATH" "INSERT INTO radist_messages (channel, connection_id, chat_id, contact_id, phone, role, content) VALUES ('$channel', $connection_id, $chat_id, $contact_id, '$phone', 'assistant', '$message');"
}

notify_observer() {
    local channel="$1"
    local target="$2"
    local message="$3"
    
    if [ "$channel" = "telegram" ]; then
        EMOJI="✈️"
    else
        EMOJI="💬"
    fi
    
    TEXT="${EMOJI} [${channel^^}] Sofia → $target

$message"
    
    curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
      -H "Content-Type: application/json" \
      -d "{\"chat_id\": \"$OBSERVER_CHAT_ID\", \"text\": \"$TEXT\"}" > /dev/null
}

send_telegram() {
    local username="${1#@}"
    local message="$2"
    
    echo "✈️ Telegram → @$username"
    echo "📝 $message"
    echo ""
    
    CHAT_RESPONSE=$(curl -s -X POST "$BASE_URL/messaging/chats/" \
      -H "X-Api-Key: $API_KEY" \
      -H "Content-Type: application/json" \
      -d "{\"connection_id\": $TG_CONNECTION, \"user_name\": \"$username\"}")
    
    CHAT_ID=$(echo "$CHAT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('chat_id',''))" 2>/dev/null)
    CONTACT_ID=$(echo "$CHAT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('contact_id','0'))" 2>/dev/null)
    
    if [ -z "$CHAT_ID" ]; then
        echo "❌ Не удалось создать чат: $CHAT_RESPONSE"
        exit 1
    fi
    
    echo "✅ Чат создан: $CHAT_ID"
    
    MSG_RESPONSE=$(curl -s -X POST "$BASE_URL/messaging/messages/" \
      -H "X-Api-Key: $API_KEY" \
      -H "Content-Type: application/json" \
      -d "{\"connection_id\": $TG_CONNECTION, \"chat_id\": $CHAT_ID, \"message_type\": \"text\", \"text\": {\"text\": \"$message\"}}")
    
    if echo "$MSG_RESPONSE" | grep -q "message_id"; then
        echo "✅ Сообщение отправлено!"
        # Сохраняем в БД для контекста
        save_to_db "telegram" "$TG_CONNECTION" "$CHAT_ID" "${CONTACT_ID:-0}" "$username" "$message"
        echo "💾 Сохранено в БД"
        notify_observer "telegram" "@$username" "$message"
        echo "👁️ Копия в Observer"
    else
        echo "❌ Ошибка: $MSG_RESPONSE"
    fi
}

send_max() {
    local phone="$1"
    local message="$2"
    
    phone="${phone#+}"
    
    echo "💬 Max → $phone"
    echo "📝 $message"
    echo ""
    
    CHAT_RESPONSE=$(curl -s -X POST "$BASE_URL/messaging/chats/" \
      -H "X-Api-Key: $API_KEY" \
      -H "Content-Type: application/json" \
      -d "{\"connection_id\": $MAX_CONNECTION, \"phone\": \"$phone\"}")
    
    CHAT_ID=$(echo "$CHAT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('chat_id',''))" 2>/dev/null)
    CONTACT_ID=$(echo "$CHAT_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('contact_id','0'))" 2>/dev/null)
    
    if [ -z "$CHAT_ID" ]; then
        echo "❌ Не удалось создать чат: $CHAT_RESPONSE"
        exit 1
    fi
    
    echo "✅ Чат создан: $CHAT_ID"
    
    MSG_RESPONSE=$(curl -s -X POST "$BASE_URL/messaging/messages/" \
      -H "X-Api-Key: $API_KEY" \
      -H "Content-Type: application/json" \
      -d "{\"connection_id\": $MAX_CONNECTION, \"chat_id\": $CHAT_ID, \"message_type\": \"text\", \"text\": {\"text\": \"$message\"}}")
    
    if echo "$MSG_RESPONSE" | grep -q "message_id"; then
        echo "✅ Сообщение отправлено!"
        # Сохраняем в БД для контекста
        save_to_db "max" "$MAX_CONNECTION" "$CHAT_ID" "${CONTACT_ID:-0}" "$phone" "$message"
        echo "💾 Сохранено в БД"
        notify_observer "max" "$phone" "$message"
        echo "👁️ Копия в Observer"
    else
        echo "❌ Ошибка: $MSG_RESPONSE"
    fi
}

case $CHANNEL in
    telegram|tg)
        send_telegram "$TARGET" "$MESSAGE"
        ;;
    max)
        send_max "$TARGET" "$MESSAGE"
        ;;
    *)
        echo "❌ Неизвестный канал: $CHANNEL"
        exit 1
        ;;
esac
