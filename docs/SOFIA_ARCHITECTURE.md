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
│  PLANNER (детерминированный)         │
│  planner.py                          │
│  - Выбирает action по состоянию      │
│  - НЕ СЧИТАЕТ ПОВТОРЫ (баг!)         │
│  Выход: Action + context             │
└──────────────────────────────────────┘
           ↓
    [WAIT check] — если WAIT, не отвечаем
           ↓
┌──────────────────────────────────────┐
│  RAG (ChromaDB)                      │
│  rag_module.py                       │
│  - 1095 примеров из 55 диалогов      │
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

## Компоненты

### 1. Extractor (extractor.py)
- **Модель:** gpt-5.2 (Responses API)
- **Вход:** сообщение клиента + история
- **Выход:** JSON с полями goal, location, budget, payment_type, lpr + confidence
- **Проблема:** Не понимает "не знаю", "где выгоднее" — возвращает null

### 2. State Manager (state_manager.py)
- **БД:** SQLite, таблица `client_state`
- **Поля:** goal, location, budget, payment_type, lpr + confidence для каждого
- **Проблема:** Нет счётчика ask_counts для лимита повторов

### 3. Planner (planner.py)
- **Тип:** Детерминированный (код, не LLM)
- **Actions:** WAIT, ASK_GOAL, ASK_LOCATION, ASK_BUDGET, ASK_PAYMENT, ASK_LPR, PROPOSE_MEETING, CONFIRM_MEETING
- **Логика:** Если поле пустое или confidence != "confirmed" → спрашивает
- **Проблема:** Нет лимита повторов — спрашивает бесконечно

### 4. Generator (sofia_prompt.py + gpt-5.2)
- **Промпт:** v4.6, блок "НЕ ПОВТОРЯЙСЯ"
- **RAG:** Получает 3 примера из ChromaDB

## База данных

### Таблица: client_state
| Поле | Тип | Описание |
|------|-----|----------|
| user_id | INTEGER | PK |
| goal | TEXT | investment/personal |
| goal_confidence | TEXT | confirmed/mentioned |
| location | TEXT | sochi/crimea/altai/... |
| location_confidence | TEXT | confirmed/mentioned |
| budget | INTEGER | в рублях |
| budget_confidence | TEXT | confirmed/mentioned |
| payment_type | TEXT | full/mortgage/installment |
| lpr | TEXT | alone/with_spouse |
| meeting_agreed | BOOLEAN | договорились о созвоне |
| meeting_datetime | TEXT | время созвона |

### Таблица: messages
| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER | PK |
| user_id | INTEGER | ID клиента |
| role | TEXT | user/assistant |
| content | TEXT | текст сообщения |
| timestamp | TIMESTAMP | время |

### Таблица: feedback_v2
| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER | PK |
| user_id | INTEGER | ID тестера |
| dialog | JSON | история диалога |
| rating | TEXT | good/bad |
| comment | TEXT | комментарий тестера |

## Потоки данных

### Поток: Квалификация
1. Клиент пишет "Хочу в Сочи"
2. Extractor → {location: "sochi", location_confidence: "confirmed"}
3. State Manager → обновляет client_state
4. Planner → проверяет что ещё не заполнено → ASK_BUDGET
5. Generator → "Поняла, Сочи. На какой бюджет ориентируетесь?"

### Поток: Проблема повторов (текущий баг)
1. Клиент пишет "Не знаю"
2. Extractor → {location: null} (не понял)
3. State Manager → location остаётся пустым
4. Planner → location пустой → ASK_LOCATION (снова!)
5. Повторяется 4+ раз

## Конфигурация (.env)
```
TELEGRAM_BOT_TOKEN=...
OPENAI_API_KEY=sk-svcacct-...
MODEL_MODE=gpt-5.2
ADMIN_CHAT_ID=512319063
```
