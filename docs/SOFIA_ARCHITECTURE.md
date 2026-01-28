# Архитектура Sofia-GPT v2.1

📅 **Обновлено:** 28.01.2026

## Общая схема
```
┌─────────────────────────────────────────────────────────────┐
│                     ВХОДЯЩИЕ КАНАЛЫ                         │
├─────────────────────────────────────────────────────────────┤
│  Telegram Bot        Telegram Userbot       Max (Radist)    │
│  @humanAINeural_bot  @SofiaOazis            +79284466701    │
│  bot_server.py       sofia_userbot.py       (TODO gateway)  │
└─────────────┬─────────────────┬─────────────────┬───────────┘
              │                 │                 │
              └────────────────┬┴─────────────────┘
                               ↓
┌──────────────────────────────────────┐
│  EXTRACTOR (gpt-5.2)                 │
│  extractor.py                        │
│  - Извлекает факты из сообщения      │
│  - Различает confirmed/mentioned     │
│  - Поля: goal, location, budget,     │
│    payment_type, lpr, strategy,      │
│    usage, family                     │
│  Выход: JSON                         │
└──────────────────────────────────────┘
              ↓
┌──────────────────────────────────────┐
│  STATE MANAGER                       │
│  state_manager.py                    │
│  - Мержит extraction в состояние     │
│  - Хранит в БД (client_state)        │
│  - Счётчики: slot_attempts,          │
│    call_proposal_count,              │
│    materials_request_count           │
└──────────────────────────────────────┘
              ↓
┌──────────────────────────────────────┐
│  PLANNER v2.2 + LLM-Planner          │
│  planner.py + llm_planner.py         │
│  - Две ветки: INVESTMENT / PERSONAL  │
│  - Два созвона: MEETING_1, MEETING_2 │
│  - LLM выбирает из allowed_actions   │
│  Выход: Action + context             │
└──────────────────────────────────────┘
              ↓
       [WAIT check] — если WAIT, не отвечаем
              ↓
┌──────────────────────────────────────┐
│  RAG (ChromaDB)                      │
│  rag_module.py                       │
│  - 1939 примеров из 100 диалогов     │
│  - 5-10 примеров на запрос           │
│  - Фильтр по stage + quality         │
└──────────────────────────────────────┘
              ↓
┌──────────────────────────────────────┐
│  GENERATOR (gpt-5.2)                 │
│  - Промпт: sofia_prompt.py           │
│  - Получает action_context           │
│  Выход: текст ответа                 │
└──────────────────────────────────────┘
              ↓
┌─────────────────────────────────────────────────────────────┐
│                     ИСХОДЯЩИЕ КАНАЛЫ                        │
├─────────────────────────────────────────────────────────────┤
│  Telegram Bot        Telegram Userbot       Max (Radist)    │
│  python-telegram-bot Pyrogram              REST API         │
└─────────────────────────────────────────────────────────────┘
```

## Каналы связи

### Telegram Bot (@humanAINeural_bot)
- **Файл:** bot_server.py
- **Библиотека:** python-telegram-bot
- **Особенность:** Клиенты пишут первыми
- **Сервис:** sofia-bot.service

### Telegram Userbot (@SofiaOazis)
- **Файл:** sofia_userbot_pyrogram.py
- **Библиотека:** Pyrogram
- **Номер:** +79676407597
- **Особенность:** Может писать первым (холодные лиды)
- **Сервис:** sofia-userbot.service

### Max (через Radist.Online)
- **Файл:** sofia_radist_gateway.py (TODO)
- **API:** https://api-ru.radist.online/v2
- **Номер:** +79284466701
- **company_id:** 205054
- **connection_id:** 80024
- **Особенность:** Может писать первым через API

## Компоненты

### 1. Extractor (extractor.py)
- **Модель:** gpt-5.2 (Responses API)
- **Вход:** сообщение клиента + история
- **Выход:** JSON с полями:
  - goal, location, budget, payment_type, lpr + confidence
  - strategy (для инвесторов), usage (для "для себя"), family
  - question_type, objection, wants_materials
  - meeting_agreed, meeting_datetime

### 2. State Manager (state_manager.py)
- **БД:** SQLite, таблица `client_state`
- **Основные поля:** goal, location, budget, payment_type, lpr + confidence
- **v2.0 поля:** branch, strategy, usage, family
- **Счётчики:** slot_attempts, call_proposal_count, materials_request_count
- **Завершение:** dialog_finished, finish_type

### 3. Planner v2.2 + LLM-Planner (planner.py, llm_planner.py)
- **Тип:** Гибридный (детерминированный + LLM)
- **Две ветки квалификации:**
  - INVESTMENT: goal → strategy → budget → MEETING_1 → payment → location → lpr → MEETING_2
  - PERSONAL: goal → usage → location → budget → MEETING_1 → family → payment → lpr → MEETING_2
- **LLM-Planner:** Выбирает лучший action из allowed_actions с учётом контекста
- **Actions:** 
  - Квалификация: ASK_GOAL, ASK_LOCATION, ASK_BUDGET, ASK_PAYMENT, ASK_LPR, ASK_STRATEGY, ASK_USAGE, ASK_FAMILY
  - Помощь: HELP_GOAL, HELP_LOCATION, HELP_BUDGET, HELP_PAYMENT, HELP_LPR
  - Созвон: PROPOSE_MEETING_1, PROPOSE_MEETING_2, CONFIRM_MEETING
  - Завершение: FINISH_WITH_MATERIALS
  - Прочее: WAIT, ANSWER_QUESTION, HANDLE_OBJECTION

### 4. Generator (sofia_prompt.py + gpt-5.2)
- **Промпт:** Директивы для каждого Action + "ТВОЯ ЛИЧНОСТЬ"
- **RAG:** Получает 5-10 примеров из ChromaDB
- **Финансы:** Обогащение контекста расчётами (если question_type=profitability)

## База данных

### Таблица: client_state (v2.0)
| Поле | Тип | Описание |
|------|-----|----------|
| user_id | INTEGER | PK |
| goal | TEXT | investment/personal |
| goal_confidence | TEXT | confirmed/mentioned |
| location | TEXT | sochi/crimea/altai/sea/mountains/all |
| location_confidence | TEXT | confirmed/mentioned |
| budget | INTEGER | в рублях |
| budget_confidence | TEXT | confirmed/mentioned |
| payment_type | TEXT | full/mortgage/installment/any |
| lpr | TEXT | alone/with_spouse/with_partner |
| branch | TEXT | investment/personal |
| strategy | TEXT | rental/growth/any |
| usage | TEXT | permanent/vacation/any |
| family | TEXT | текст |
| meeting_agreed | BOOLEAN | договорились о созвоне |
| meeting_datetime | TEXT | время созвона |
| slot_attempts | JSON | счётчики попыток по слотам |
| call_refused | BOOLEAN | отказался от созвона |
| call_proposal_count | INTEGER | сколько раз предлагали созвон |
| materials_request_count | INTEGER | сколько раз просил подборку |
| dialog_finished | BOOLEAN | диалог завершён |
| finish_type | TEXT | meeting/materials |

### Таблица: messages
| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER | PK |
| user_id | INTEGER | ID клиента |
| role | TEXT | user/assistant |
| content | TEXT | текст сообщения |
| timestamp | TIMESTAMP | время |

## Конфигурация

### .env
```
TELEGRAM_BOT_TOKEN=...
OPENAI_API_KEY=...
MODEL_MODE=gpt-5.2
ADMIN_CHAT_ID=512319063
USE_LLM_PLANNER=true
```

### config/radist_config.py
```python
RADIST_CONFIG = {
    "api_url": "https://api-ru.radist.online/v2",
    "api_key": "...",
    "company_id": 205054,
    "connection_id": 80024,
    "phone": "+79284466701",
}
```

## Сервисы systemd
```bash
# Telegram бот
/etc/systemd/system/sofia-bot.service

# Telegram userbot  
/etc/systemd/system/sofia-userbot.service

# Max gateway (TODO)
/etc/systemd/system/sofia-radist.service
```
