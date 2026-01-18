# Sofia Userbot — Документация

## Идея и задумка

### Проблема
Telegram-боты НЕ могут писать первыми. Клиент должен нажать /start или написать боту.

### Решение
**Userbot** — обычный аккаунт Telegram (+79676407597), управляемый скриптом через Pyrogram. Может писать первым любому пользователю.

### Бизнес-логика
1. Приходит лид (с сайта, Avito, CRM)
2. Userbot пишет первым: "Здравствуйте, это София..."
3. Клиент отвечает
4. Дальше работает та же логика квалификации что и в основном боте
5. Результат: созвон или подборка

---

## Техническая реализация

### Стек
- **Pyrogram** — библиотека для userbot'ов
- **OpenAI gpt-5.2** — Responses API
- **Та же БД** (sofia_gpt.db)
- **Импорт логики** из модулей Sofia

### Credentials
```python
API_ID = 32374021
API_HASH = "6dc50b91611d636fcc22f5ecb8c96bc6"
SESSION_NAME = "sofia_pyrogram"
Номер: +79676407597 (аккаунт Sofia)
```

### Файлы
- `/opt/sofia-gpt/sofia_userbot_pyrogram.py` — основной код (v2.0)
- `/opt/sofia-gpt/sofia_pyrogram.session` — файл сессии Telegram
- `/opt/sofia-gpt/userbot.log` — логи
- `/etc/systemd/system/sofia-userbot.service` — systemd сервис

---

## Архитектура v2.0
```
┌─────────────────────────────────────────────────────────────────┐
│ Команда: /start @username                                       │
│ или                                                              │
│ Входящее сообщение от клиента                                   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ process_with_sofia(user_id, user_name, message)                 │
│                                                                  │
│ 1. extract_sync() — извлечь факты (из extractor.py)            │
│ 2. merge_extraction_to_state() — обновить состояние            │
│ 3. get_next_action() — выбрать действие (из planner.py)        │
│ 4. ACTION_TO_SLOT маппинг + increment_slot_attempt()           │
│ 5. Сохранить v2.0 поля (branch, счётчики, dialog_finished)     │
│ 6. search_examples() — RAG по ACTION_TO_RAG_STAGE              │
│ 7. get_system_prompt() + gpt-5.2 Responses API                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ Отправить ответ клиенту через Pyrogram                          │
└─────────────────────────────────────────────────────────────────┘
```

### Что ИМПОРТИРУЕТСЯ (общий код с ботом)
```python
from extractor import extract_sync, merge_extraction_to_state
from state_manager import StateManager
from planner import get_next_action, get_action_context, Action, increment_slot_attempt
from sofia_prompt import get_system_prompt, BOT_NAME, PRICE_CATALOG
from rag_module import search_examples, format_examples_for_prompt, init_vector_store
```

### Что ДУБЛИРУЕТСЯ (константы из bot_server.py)
```python
RAG_EXAMPLES_COUNT = 10
MODEL_MODE = os.getenv("MODEL_MODE", "gpt-5.2")
ACTION_TO_SLOT = {"payment": "payment_type"}
ACTION_TO_RAG_STAGE = {
    "ask_goal": "QUALIFICATION",
    "ask_strategy": "QUALIFICATION",
    "propose_meeting_1": "MEETING",
    # ... и т.д.
}
```

---

## Запуск и использование

### Интерактивный режим (текущий)
```bash
# Терминал 1 — логи
tail -F /opt/sofia-gpt/userbot.log

# Терминал 2 — userbot
cd /opt/sofia-gpt && ./venv/bin/python sofia_userbot_pyrogram.py
```

### Команды
| Команда | Описание |
|---------|----------|
| `/start @username` | Умный старт через Planner (сброс state) |
| `/start @username avito` | Старт с указанием источника лида |
| `/send @username Текст` | Отправить произвольный текст |
| `/quit` | Выход |

### Пример сессии
```
Sofia> /start @sergey_7in
============================================================
🚀 START_SMART_DIALOG: @sergey_7in
============================================================
📱 Telegram user: Сергей (ID: 512319063)
🗑️ State reset для user_id=512319063
🎯 PLANNER DECISION: ask_goal
📝 GENERATED MESSAGE: Сергей, добрый день! Это София...
✅ SENT TO TELEGRAM → @sergey_7in

📩 Сергей: добрый могу
📊 State updated: Квалификация: не начата
🎯 PLANNER: help_goal
📚 RAG: 10 примеров для QUALIFICATION
📤 София: Супер 😊 Чтобы подобрать вам...
```

---

## Логирование

Все события записываются в `/opt/sofia-gpt/userbot.log`:
- 📩 Входящие сообщения
- 📊 Обновления State
- 🎯 Решения Planner
- 📚 RAG запросы
- 📤 Исходящие сообщения
- ❌ Ошибки

---

## TODO

### Daemon режим + HTTP API
1. Убрать интерактивный input()
2. Добавить HTTP API:
```
POST /api/new-lead
{"target": "@username", "name": "Иван", "source": "avito"}
```
3. Интеграция с n8n
4. Systemd автозапуск

---

## История версий

### v2.0 (18.01.2026)
- ACTION_TO_SLOT маппинг
- ACTION_TO_RAG_STAGE маппинг
- RAG_EXAMPLES_COUNT = 10
- gpt-5.2 Responses API
- Сохранение v2.0 полей
- Логирование в файл

### v1.0 (17.01.2026)
- Базовая версия (откачена)
- Упрощённая логика
- gpt-4o-mini
