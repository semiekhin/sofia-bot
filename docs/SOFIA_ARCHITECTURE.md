# Архитектура Sofia-GPT v2.0

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
│  PLANNER v2.0 (детерминированный)    │
│  planner.py                          │
│  - Две ветки: INVESTMENT / PERSONAL  │
│  - Два созвона: MEETING_1, MEETING_2 │
│  - Счётчик отказов → FINISH          │
│  Выход: Action + context             │
└──────────────────────────────────────┘
           ↓
    [WAIT check] — если WAIT, не отвечаем
           ↓
┌──────────────────────────────────────┐
│  RAG (ChromaDB)                      │
│  rag_module.py                       │
│  - 1939 примеров из 100 диалогов     │
│  - 5 примеров на запрос              │
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

### 3. Planner v2.0 (planner.py)
- **Тип:** Детерминированный (код, не LLM)
- **Две ветки квалификации:**
  - INVESTMENT: goal → strategy → budget → MEETING_1 → payment → location → lpr → MEETING_2
  - PERSONAL: goal → usage → location → budget → MEETING_1 → family → payment → lpr → MEETING_2
- **Actions:** 
  - Квалификация: ASK_GOAL, ASK_LOCATION, ASK_BUDGET, ASK_PAYMENT, ASK_LPR, ASK_STRATEGY, ASK_USAGE, ASK_FAMILY
  - Помощь: HELP_GOAL, HELP_LOCATION, HELP_BUDGET, HELP_PAYMENT, HELP_LPR
  - Созвон: PROPOSE_MEETING_1, PROPOSE_MEETING_2, CONFIRM_MEETING
  - Завершение: FINISH_WITH_MATERIALS
  - Прочее: WAIT, ANSWER_QUESTION, HANDLE_OBJECTION
- **Защита от повторов:** slot_attempts (max 1 ask + 1 help)
- **Счётчик отказов:** materials_request_count >= 2 → FINISH_WITH_MATERIALS

### 4. Generator (sofia_prompt.py + gpt-5.2)
- **Промпт:** Директивы для каждого Action
- **RAG:** Получает 5 примеров из ChromaDB

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
| **branch** | TEXT | investment/personal (v2.0) |
| **strategy** | TEXT | rental/growth/any (v2.0) |
| **usage** | TEXT | permanent/vacation/any (v2.0) |
| **family** | TEXT | текст (v2.0) |
| meeting_agreed | BOOLEAN | договорились о созвоне |
| meeting_datetime | TEXT | время созвона |
| slot_attempts | JSON | счётчики попыток по слотам |
| call_refused | BOOLEAN | отказался от созвона |
| **call_proposal_count** | INTEGER | сколько раз предлагали созвон (v2.0) |
| **materials_request_count** | INTEGER | сколько раз просил подборку (v2.0) |
| **dialog_finished** | BOOLEAN | диалог завершён (v2.0) |
| **finish_type** | TEXT | meeting/materials (v2.0) |

### Таблица: messages
| Поле | Тип | Описание |
|------|-----|----------|
| id | INTEGER | PK |
| user_id | INTEGER | ID клиента |
| role | TEXT | user/assistant |
| content | TEXT | текст сообщения |
| timestamp | TIMESTAMP | время |

## Потоки данных v2.0

### Поток: INVESTMENT квалификация
1. Клиент: "Хочу инвестировать"
2. Extractor → {goal: "investment", goal_confidence: "confirmed"}
3. State Manager → branch = "investment"
4. Planner → _qualify_investment() → ASK_STRATEGY
5. Generator → "Что важнее: доход с аренды или рост стоимости?"
6. ... продолжение по ветке ...

### Поток: Два отказа от созвона
1. После PROPOSE_MEETING_1 клиент: "скиньте варианты"
2. Planner → materials_request_count = 1, продолжает квалификацию
3. После PROPOSE_MEETING_2 клиент: "нет, только в переписке"
4. Planner → materials_request_count = 2 → FINISH_WITH_MATERIALS
5. Generator → "Хорошо, вижу вашу занятость) Отправлю варианты..."
6. State → dialog_finished = True, finish_type = "materials"

## Конфигурация (.env)
```
TELEGRAM_BOT_TOKEN=...
OPENAI_API_KEY=...
MODEL_MODE=gpt-5.2
ADMIN_CHAT_ID=512319063
```
