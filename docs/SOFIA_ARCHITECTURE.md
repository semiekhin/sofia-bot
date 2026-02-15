# Архитектура Sofia-GPT v3.0

## Общая схема
```
Radist Webhook (Max/Telegram/WhatsApp)
           ↓
    sofia_radist_gateway.py
           ↓
┌──────────────────────────────────────┐
│  MESSAGE PROCESSOR                   │
│  message_processor.py                │
│                                      │
│  ┌─────────────────────────────────┐ │
│  │ EXTRACTOR (gpt-5.2)             │ │
│  │ extractor.py                    │ │
│  │ - Извлекает факты из сообщения  │ │
│  │ - goal, budget, location и др.  │ │
│  │ - signals (friction, readiness) │ │
│  └─────────────────────────────────┘ │
│              ↓                       │
│  ┌─────────────────────────────────┐ │
│  │ STATE MANAGER                   │ │
│  │ state_manager.py                │ │
│  │ - Мержит extraction в state     │ │
│  │ - Хранит в SQLite               │ │
│  │ - lead_type (cold/warm/hot)     │ │
│  └─────────────────────────────────┘ │
└──────────────────────────────────────┘
           ↓
┌──────────────────────────────────────┐
│  ANALYZER (gpt-5.2)                  │
│  Внутри gateway                      │
│  - Определяет stage диалога          │
│  - Формирует rag_query               │
│  Выход: stage + rag_query            │
└──────────────────────────────────────┘
           ↓
┌──────────────────────────────────────┐
│  RAG (ChromaDB)                      │
│  rag_module.py                       │
│  - 2001 пример из 124+ диалогов      │
│  - 10 примеров на запрос             │
│  - Фильтр по stage                   │
│  - 29 примеров ACTUALIZATION         │
└──────────────────────────────────────┘
           ↓
┌──────────────────────────────────────┐
│  GENERATOR (gpt-5.2)                 │
│  - Промпт: sofia_prompt_v2.py        │
│  - Получает state_summary + RAG      │
│  - reasoning=high                    │
│  Выход: текст ответа                 │
└──────────────────────────────────────┘
           ↓
    Radist API → Клиент

           ↓ (копия)
┌──────────────────────────────────────┐
│  OBSERVER (Telegram Forum Topics)    │
│  - Каждый клиент = отдельная тема    │
│  - БД: observer_topics               │
└──────────────────────────────────────┘
```

## Компоненты

### 1. Extractor (extractor.py)
- **Модель:** gpt-5.2 (Responses API)
- **Вход:** сообщение клиента + история
- **Выход:** JSON с полями:
  - goal, location, budget, payment_type, lpr + confidence
  - strategy (для инвесторов), usage (для "для себя"), family
  - question_type, objection, wants_materials
  - meeting_agreed, meeting_datetime
  - signals: friction, call_readiness, engagement, urgency

### 2. State Manager (state_manager.py)
- **БД:** SQLite, таблица `client_state`
- **Основные поля:** goal, location, budget, payment_type, lpr + confidence
- **v3.0 поля:** lead_type (cold/warm/hot), branch, strategy, usage, family
- **Счётчики:** call_proposal_count, materials_request_count
- **Завершение:** dialog_finished, finish_type

### 3. Analyzer (внутри gateway)
- **Модель:** gpt-5.2 (Responses API)
- **Вход:** история диалога + последнее сообщение + state_summary
- **Выход:** JSON {stage, rag_query}
- **Stages:** GREETING, ACTUALIZATION, QUALIFICATION, MEETING, OBJECTION, CLOSING

### 4. RAG (rag_module.py)
- **БД:** ChromaDB (chroma_db/)
- **Примеры:** 2001 из 124+ диалогов
- **Поиск:** semantic search по rag_query + фильтр по stage
- **Выход:** 10 релевантных примеров

### 5. Generator (sofia_prompt_v2.py + gpt-5.2)
- **Модель:** gpt-5.2 с reasoning=high
- **Промпт:** state_summary + RAG примеры + инструкции
- **Блоки:** КВАЛИФИКАЦИЯ, АКТУАЛИЗАЦИЯ (для cold), СОЗВОН, ЗАВЕРШЕНИЕ
- **Выход:** текст ответа клиенту

### 6. Observer (Telegram Forum Topics)
- **Группа:** Диалоги Софья
- **Механизм:** каждый клиент = отдельная тема
- **БД:** observer_topics (phone → thread_id)

## База данных

### Таблица: client_state
| Поле | Тип | Описание |
|------|-----|----------|
| user_id | INTEGER | PK (отрицательный для Radist) |
| lead_type | TEXT | cold/warm/hot |
| goal | TEXT | investment/personal |
| goal_confidence | TEXT | confirmed/mentioned |
| location | TEXT | sochi/crimea/altai/sea/mountains/all |
| budget | INTEGER | в рублях |
| payment_type | TEXT | full/mortgage/installment/any |
| strategy | TEXT | rental/growth/any (для инвесторов) |
| usage | TEXT | permanent/vacation/any (для "для себя") |
| dialog_finished | BOOLEAN | диалог завершён |
| finish_type | TEXT | meeting/materials/llm_end |

### Таблица: radist_messages
| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER | PK |
| channel | TEXT | max/telegram/whatsapp |
| chat_id | INTEGER | ID чата в Radist |
| phone | TEXT | телефон клиента |
| role | TEXT | user/assistant |
| content | TEXT | текст сообщения |
| timestamp | TIMESTAMP | время |

### Таблица: observer_topics
| Поле | Тип | Описание |
|------|-----|----------|
| phone | TEXT | PK |
| thread_id | INTEGER | ID темы в Telegram |
| user_name | TEXT | имя клиента |

## Формула user_id

Radist даёт chat_id (положительный). Для совместимости с client_state используем отрицательный user_id:
```
Max:      user_id = -(1000000 + chat_id)
Telegram: user_id = -(2000000 + chat_id)
WhatsApp: user_id = -(3000000 + chat_id)
```

## Потоки данных

### Поток: Холодный лид (ACTUALIZATION)
1. Outreach: `sofia_outreach.sh max 79... "" cold`
2. Клиент: "Кто это?" / "Откуда номер?"
3. Analyzer → stage=ACTUALIZATION
4. RAG → 10 примеров ACTUALIZATION
5. Generator → объясняет откуда контакт, мягко к квалификации
6. Клиент: "Не актуально" → Generator завершает с [END]

### Поток: Тёплый лид (QUALIFICATION → MEETING)
1. Outreach: `sofia_outreach.sh max 79... Имя`
2. Клиент отвечает → Analyzer → stage=QUALIFICATION
3. Generator квалифицирует (goal, budget, location)
4. Достаточно данных → Generator предлагает созвон
5. Клиент соглашается → CLOSING

## Конфигурация (.env)
```
OPENAI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
OBSERVER_CHAT_ID=...
```

## Конфигурация Radist (config/radist_config.py)
```python
CHANNELS = {
    "max": {"enabled": True, "connection_id": 80024},
    "telegram": {"enabled": True, "connection_id": 80200},
    "whatsapp": {"enabled": False, "connection_id": None}
}
```

## Статус каналов (15.02.2026)

| Канал | Статус | Примечание |
|-------|--------|------------|
| Max | ❌ ЗАБАНЕН | Номер заблокирован после массовой рассылки |
| Telegram | ⚠️ Ограничен | Работает, но бот не может писать первым |
| WhatsApp (WABA) | ⏳ Не подключен | Приоритет №1, через Radist.Online + 360Dialog |

## Стратегия каналов (решено 07.02.2026)
1. **WABA** — основной outreach (легальный, шаблоны, без банов)
2. **Telegram** — входящие (клиент сам приходит по ссылке)
3. **Max** — дополнительный после нового номера (10-15/день, ротация)
4. **Виджет на сайте** — ночные лиды без рассылки



## Web API (добавлено 10.02.2026)

### Схема
```
Браузер (atlantis-invest.ru)
    ↓ fetch()
Nginx (443, SSL) → api.atlantis-invest.ru
    ↓ proxy_pass
web_api.py (localhost:8080, FastAPI)
    ↓
process_message() → Analyzer → RAG → Generator
    ↓
JSON response → Браузер
```

### Компоненты
- **web_api.py** — FastAPI сервер, точка входа для виджета
- **nginx** — reverse proxy + SSL (Let's Encrypt)
- **sessionStorage** — хранение session_id в браузере

### Endpoints
| Метод | URL | Описание |
|-------|-----|----------|
| GET | /api/health | Проверка работоспособности |
| POST | /api/session | Создание сессии (возвращает session_id) |
| POST | /api/chat | Отправка сообщения (возвращает reply) |
| GET | /api/history/{session_id} | История сообщений |

### Формула user_id для Web
```
user_id = 9_000_000 + (hash(session_id) % 1_000_000)
```
Диапазон 9M–10M, не пересекается с Telegram и Radist ID.

### BUG-005 fix (13.02.2026)
Greeting сохраняется в историю через save_message() при create_session().
Без этого LLM не видел свой вопрос из greeting и неправильно интерпретировал ответы.

### Хранение данных
- Сообщения: общая таблица `messages` (chat_id = user_id)
- Состояние: общая таблица `client_state`
- Сессии: в памяти (dict), теряются при рестарте

### CORS
Разрешённые origins: atlantis-invest.ru, invest-apartmens.online, sochiremstroy.tilda.ws, localhost:3000

### Fallback
Если API недоступен — виджет показывает демо-ответы из getDemoResponse() (захардкожены в index.html).

## Битрикс CRM интеграция

### Как работает
1. LLM ставит маркер `[END]` когда диалог завершён
2. web_api.py перехватывает `[END]` (строка ~400)
3. Вызывает `send_lead_to_bitrix()` с данными:
   - Телефон: `extract_phone_from_history()` — ищет номер в сообщениях клиента (regex)
   - Квалификация из state: goal, budget, payment_type
   - Последние 10 сообщений переписки в COMMENTS
4. POST на webhook Битрикса → лид создан

### Endpoint
```
POST https://oazisestate.bitrix24.ru/rest/426/z61dwivdmdy9dk4f/crm.lead.add
```

### Поля лида
- TITLE: "AI-бот: {имя клиента}"
- NAME: имя
- PHONE: [{VALUE: телефон, VALUE_TYPE: MOBILE}]
- COMMENTS: цель + бюджет + оплата + переписка
- SOURCE_ID: "504" (источник "София ИИ")
- ASSIGNED_BY_ID: 426 (тест) → 24932 (прод)

### Где в коде
- `web_api.py` строка ~52: константы BITRIX_*
- `web_api.py` строка ~57: extract_phone_from_history()
- `web_api.py` строка ~81: send_lead_to_bitrix()
- `web_api.py` строка ~403: вызов при [END]

### Важно
- Только web-канал (web_api.py), Telegram и Max пока не отправляют
- Обёрнуто в try/except — если Битрикс недоступен, клиент получит ответ как обычно
- Без контакта лид всё равно уйдёт, но без телефона (PHONE будет пустым)
