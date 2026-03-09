# Radist.Online API — Интеграция с Max

📅 **Настроено:** 28.01.2026

## 🔑 Учётные данные

| Параметр | Значение |
|----------|----------|
| API URL | `https://api-ru.radist.online/v2` |
| company_id | `205054` |
| connection_id | `80024` |
| Тип подключения | `max_personal` |
| Номер Max | `+79284466701` |
| user_id (Max) | `174742776` |
| radist_token | `b7615c82-9aeb-42a0-ae98-8eb62021890b` |
| Подписка до | `31.01.2026` |

## 🔐 API Ключ
```
-cCC1Lbcwc6Et-s8mClF8_qPkE7mNF35VmTVUoZEIKYAZurc_Oyjjf2AdXTHqjvWm8cMp_U6NzJD_xNzl4jOZA
```

Права: `connections`, `messaging`, `webhooks`

## 📡 API Эндпоинты

Все запросы требуют `company_id` в пути!

### Проверка авторизации
```bash
curl -X GET "https://api-ru.radist.online/v2/users/me" \
  -H 'X-Api-Key: {API_KEY}'
```

### Список подключений
```bash
curl -X GET "https://api-ru.radist.online/v2/companies/205054/connections/" \
  -H 'X-Api-Key: {API_KEY}'
```

### Создание чата (для нового контакта)
```bash
curl -X POST "https://api-ru.radist.online/v2/companies/205054/messaging/chats/" \
  -H 'X-Api-Key: {API_KEY}' \
  -H "Content-Type: application/json" \
  -d '{
    "connection_id": 80024,
    "phone": "+79001234567"
  }'
```

**Ответ:**
```json
{
  "created_chat": true,
  "created_contact": true,
  "chat_id": 38001832,
  "contact_id": 32498778
}
```

### Отправка сообщения
```bash
curl -X POST "https://api-ru.radist.online/v2/companies/205054/messaging/messages/" \
  -H 'X-Api-Key: {API_KEY}' \
  -H "Content-Type: application/json" \
  -d '{
    "connection_id": 80024,
    "chat_id": 38001832,
    "message_type": "text",
    "text": {"text": "Ваше сообщение"}
  }'
```

### Создание webhook (для входящих)
```bash
curl -X POST "https://api-ru.radist.online/v2/companies/205054/webhooks/" \
  -H 'X-Api-Key: {API_KEY}' \
  -H "Content-Type: application/json" \
  -d '{
    "url": "http://72.56.64.91:5001/webhook/radist",
    "events": ["messaging.message.received"]
  }'
```

## ⚠️ Важные особенности

1. **Все эндпоинты требуют company_id в URL** — без него возвращает 404
2. **chat_id — число**, не телефон. Сначала создать чат, потом отправлять
3. **Формат text** — объект `{"text": "сообщение"}`, не строка
4. **API URL для России** — `api-ru.radist.online` (не `api.radist.online`)
5. **Лимиты** — 5 запросов/сек, /chats/ и /contacts/ — 1 запрос/сек

## 📁 Связанные файлы

- `sofia_radist_gateway.py` — шлюз для Max (TODO)
- `.env` — хранить API_KEY

## 🔗 Документация

- Swagger: https://api-ru.radist.online/v2/docs
- Docs: https://docs.radist.online
