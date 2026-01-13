# Архитектура Sofia-GPT

## Общая схема

```
Telegram (сообщение клиента)
           ↓
    bot_server.py / delayed_response()
           ↓
┌──────────────────────────────────────┐
│  EXTRACTOR (gpt-5.2)                 │
│  extractor.py                        │
│  - Извлекает факты из сообщения      │
│  - Различает confirmed/mentioned     │
│  Выход: JSON                         │
└──────────────────────────────────────┘
           ↓
┌──────────────────────────────────────┐
│  STATE MANAGER                       │
│  state_manager.py                    │
│  - Мержит extraction в состояние     │
│  - Хранит в БД (client_state)        │
└──────────────────────────────────────┘
           ↓
┌──────────────────────────────────────┐
│  PLANNER (детерминированный, код)    │
│  planner.py                          │
│  - Выбирает action по состоянию      │
│  - WAIT только если meeting_agreed   │
│  Выход: Action + context             │
└──────────────────────────────────────┘
           ↓
    [WAIT check] — если WAIT, не отвечаем
           ↓
┌──────────────────────────────────────┐
│  RAG (ChromaDB)                      │
│  rag_module.py                       │
│  - 1095 примеров                     │
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
    Telegram (ответ клиенту)
```

## Ключевые компоненты

### Extractor
- **Модель:** gpt-5.2 (Responses API, без temperature)
- **Выход:** goal, location, budget, payment_type, lpr (+ confidence)
- **Особенности:** Синонимы локаций, "all"/"any" как валидные ответы

### State Manager
- **БД:** SQLite, таблица `client_state`
- **Поля:** goal, location, budget, payment_type, lpr + confidence для каждого
- **Методы:** get_state(), update_state(), reset_state()

### Planner
- **Тип:** Детерминированный (код, не LLM)
- **Actions:** WAIT, ASK_GOAL, ASK_LOCATION, ASK_BUDGET, ASK_PAYMENT, ASK_LPR, PROPOSE_MEETING, CONFIRM_MEETING
- **WAIT:** Только если state.meeting_agreed AND короткое подтверждение

### Generator
- **Модель:** gpt-5.2 (Responses API)
- **Промпт:** sofia_prompt.py с блоком "НЕ ПОВТОРЯЙСЯ"

## Конфигурация

```
TELEGRAM_BOT_TOKEN=...
OPENAI_API_KEY=sk-svcacct-...
MODEL_MODE=gpt-5.2
ADMIN_CHAT_ID=512319063
```
