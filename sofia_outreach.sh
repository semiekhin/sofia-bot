#!/bin/bash
# Sofia Outreach — проактивная отправка через Radist
# Использование:
#   ./sofia_outreach.sh telegram @username [Имя] [cold|warm|hot]
#   ./sofia_outreach.sh max 79001234567 [Имя] [cold|warm|hot]

API_KEY="-cCC1Lbcwc6Et-s8mClF8_qPkE7mNF35VmTVUoZEIKYAZurc_Oyjjf2AdXTHqjvWm8cMp_U6NzJD_xNzl4jOZA"
COMPANY_ID="205054"
BASE_URL="https://api-ru.radist.online/v2/companies/$COMPANY_ID"
DB_PATH="/opt/sofia-gpt/sofia_gpt.db"

# Connection IDs
TG_CONNECTION=80200
MAX_CONNECTION=80024

# Observer group
OBSERVER_CHAT_ID="-1003874757033"
TG_BOT_TOKEN="8409538626:AAGqB4bkk81dCZutNmLfTd95mi_4Ky19U5M"

CHANNEL=$1
TARGET=$2
NAME=$3
LEAD_TYPE=${4:-warm}  # cold|warm|hot

if [ -z "$CHANNEL" ] || [ -z "$TARGET" ]; then
    echo "❌ Использование:"
    echo "   $0 telegram @username [Имя] [cold|warm|hot]"
    echo "   $0 max 79001234567 [Имя] [cold|warm|hot]"
    echo ""
    echo "Примеры:"
    echo "   $0 telegram @ivan_petrov Иван cold"
    echo "   $0 max 79161234567 "" warm"
    exit 1
fi

# Шаблон приветствия по типу лида
GREETING_NAME="${NAME:+$NAME, }"

case $LEAD_TYPE in
    cold)
        MESSAGE="${GREETING_NAME}добрый день! Это София из Oazis Estate — курортная недвижимость в Сочи) Вы оставляли заявку — ещё актуально?"
        ;;
    warm)
        MESSAGE="${GREETING_NAME}добрый день! Это София из Oazis Estate. Вы интересовались недвижимостью в Сочи — удобно сейчас пообщаться?"
        ;;
    hot)
        MESSAGE="${GREETING_NAME}добрый день! Это София из Oazis Estate. Мы подготовили для вас подборку — удобно обсудить?"
        ;;
    *)
        MESSAGE="${GREETING_NAME}добрый день! Это София из Oazis Estate — курортная недвижимость в Сочи) Вы оставляли заявку — ещё актуально?"
        ;;
esac

save_to_db() {
    local channel="$1"
    local connection_id="$2"
    local chat_id="$3"
    local contact_id="$4"
    local phone="$5"
    local message="$6"
    
    sqlite3 "$DB_PATH" "INSERT INTO radist_messages (channel, connection_id, chat_id, contact_id, phone, role, content) VALUES ('$channel', $connection_id, $chat_id, $contact_id, '$phone', 'assistant', '$message');"
}

save_lead_type() {
    local channel="$1"
    local chat_id="$2"
    local lead_type="$3"
    
    # user_id по формуле gateway: -(offset + chat_id)
    case $channel in
        max) OFFSET=1000000 ;;
        telegram) OFFSET=2000000 ;;
        whatsapp) OFFSET=3000000 ;;
        *) OFFSET=9000000 ;;
    esac
    USER_ID=$(( -(OFFSET + chat_id) ))
    
    sqlite3 "$DB_PATH" "INSERT INTO client_state (user_id, lead_type) VALUES ($USER_ID, '$lead_type') ON CONFLICT(user_id) DO UPDATE SET lead_type='$lead_type';"
}

notify_observer() {
    local channel="$1"
    local target="$2"
    local message="$3"
    
    # Получаем или создаём тему для клиента
    THREAD_ID=$(sqlite3 "$DB_PATH" "SELECT thread_id FROM observer_topics WHERE phone = '$target';" 2>/dev/null)
    
    if [ -z "$THREAD_ID" ]; then
        # Создаём новую тему
        TOPIC_NAME="$target"
        RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/createForumTopic" \
          -H "Content-Type: application/json" \
          -d "{\"chat_id\": \"$OBSERVER_CHAT_ID\", \"name\": \"$TOPIC_NAME\"}")
        
        THREAD_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('result',{}).get('message_thread_id',''))" 2>/dev/null)
        
        if [ -n "$THREAD_ID" ]; then
            sqlite3 "$DB_PATH" "INSERT OR REPLACE INTO observer_topics (phone, thread_id, user_name) VALUES ('$target', $THREAD_ID, '$target');"
            echo "👁️ Создана тема: $TOPIC_NAME"
        fi
    fi
    
    if [ "$channel" = "telegram" ]; then
        EMOJI="✈️"
    else
        EMOJI="💬"
    fi
    
    TEXT="↪️ <b>София:</b>
$message"
    
    if [ -n "$THREAD_ID" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
          -H "Content-Type: application/json" \
          -d "{\"chat_id\": \"$OBSERVER_CHAT_ID\", \"message_thread_id\": $THREAD_ID, \"text\": \"$TEXT\", \"parse_mode\": \"HTML\"}" > /dev/null
    else
        curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
          -H "Content-Type: application/json" \
          -d "{\"chat_id\": \"$OBSERVER_CHAT_ID\", \"text\": \"$TEXT\", \"parse_mode\": \"HTML\"}" > /dev/null
    fi
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
        save_lead_type "telegram" "$CHAT_ID" "$LEAD_TYPE"
        echo "💾 Сохранено в БД (lead_type=$LEAD_TYPE)"
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
        save_lead_type "max" "$CHAT_ID" "$LEAD_TYPE"
        echo "💾 Сохранено в БД (lead_type=$LEAD_TYPE)"
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
