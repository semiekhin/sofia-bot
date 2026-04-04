# София-GPT — Архитектура интеграции с CRM

> AI-менеджер квалификации лидов для недвижимости. Клиент оставляет заявку на сайте →
> попадает в CRM и в диалог с Софией → София квалифицирует → передаёт менеджеру.
>
> Первый клиент: Oazis Estate (Атлантис, Сочи). Документ описывает рабочую схему
> для масштабирования на другие сайты.
>
> Актуален на 2026-04-04.

---

## 1. Полная схема (Атлантис)

### Шаг 1: Клиент заполняет форму на Тильде
- Сайт: invest-apartmens.online/atlantis
- Тильда отправляет данные в Битрикс24 через встроенный webhook
- В Битрикс создаётся лид: источник "Атлантис SSV" (SOURCE_ID=397), ответственный "София AI" (ASSIGNED_BY_ID=428)

### Шаг 2: Тильда редиректит клиента в Telegram
- Вместо success page — ссылка: `https://t.me/humanAINeural_bot?start=ATL`
- Параметр ATL = идентификатор источника (Атлантис)
- Клиент попадает в Telegram бот и начинает диалог с Софией

### Шаг 3: София квалифицирует
- Бот находит лид в Битрикс по SOURCE_ID=397 (`find_recent_atlantis_lead`)
- Привязывает лид к Telegram user в таблице `telegram_leads`
- Сохраняет оригинального ответственного в `lead_assigned`
- Ставит ASSIGNED_BY_ID=428 (София AI) — защита от робота-распределителя
- Каждое сообщение обновляет комментарии к лиду
- Квалификация по скрипту: цель → бюджет → оплата → предложение созвона

### Шаг 4: Завершение диалога
Пять сценариев:

| finish_type | Триггер | Где в коде |
|-------------|---------|-----------|
| `meeting` | Клиент согласился на созвон (meeting_agreed=True) | bot_server.py:958 |
| `no_response` | Клиент не ответил 15 мин после /start | bot_server.py:863 |
| `no_response_after_reminder` | 60 мин молчания → напоминание → ещё 15 мин | bot_server.py:842 |
| `llm_end` | LLM вернул токен [END] (включая двойной отказ, уход клиента) | pipeline.py:300 |
| (перехват) | Менеджер сменил ASSIGNED_BY_ID в Битрикс | web_api.py:605 — manager_active=1, София молчит. **finalize_lead НЕ вызывается** |

При завершении (кроме перехвата) → `finalize_lead()`:
1. ASSIGNED_BY_ID меняется с 428 на **24932** (ID для запуска БП)
2. Вызывается `bizproc.workflow.start` (TEMPLATE_ID=152)
3. В комментарий лида записан итог: причина завершения + цель + бюджет + оплата

### Шаг 5: Бизнес-процесс Битрикс (сторона клиента)
- БП 152 проверяет дубли
- Уникальный лид → стадия "В раздачу" → менеджер получает
- Дубль → стадия "Найден дубль" → контроль качества

```
Тильда форма (invest-apartmens.online/atlantis)
    │
    ├─ 1. Webhook Тильда → Битрикс: создаёт лид (SOURCE_ID=397)
    │
    └─ 2. Success page → редирект: t.me/humanAINeural_bot?start=ATL
                                    │
                                    ▼
                        Telegram бот: /start ATL
                            │
                            ├─ find_recent_atlantis_lead() → находит лид по SOURCE_ID
                            ├─ save_bitrix_lead_id() → привязка user↔lead в БД
                            ├─ save_original_assigned() → запомнить текущего ответственного
                            ├─ set_lead_assigned(428) → София AI берёт лид
                            └─ запуск таймаута 15 мин
                                    │
                            ┌───────┴────────┐
                            │                │
                    Клиент ответил     Клиент молчит
                            │                │
                    Квалификация        15 мин → finalize
                    (диалог)                │
                            │                │
                    Завершение ──────► finalize_lead()
                                        │
                                        ├─ set_lead_assigned(24932)
                                        └─ start_distribution_bp(152)
                                                │
                                            Битрикс БП:
                                            проверка дублей →
                                            раздача менеджеру
```

---

## 2. Компоненты

### Наша сторона (сервер Sofia-GPT)

| Компонент | Файл | Что делает |
|-----------|------|-----------|
| Telegram бот | bot_server.py | Принимает сообщения, ведёт диалог, таймауты, Bitrix |
| Web API | web_api.py | Веб-виджет, Bitrix webhook (перехват менеджером) |
| Ядро диалога | core/pipeline.py | LLM генерация ответов (OpenAI gpt-5.2) |
| Bitrix интеграция | core/bitrix.py | Создание/обновление лидов, finalize_lead, БП |
| State manager | state_manager.py | Хранение состояния клиента (SQLite) |
| Source objects | config/source_objects.py | Маппинг объектов: ключевые слова, контекст, промпты |

### Сторона клиента (Битрикс24)

| Компонент | Значение | Описание |
|-----------|----------|----------|
| SOURCE_ID | 397 | Источник лидов с Тильды Атлантис |
| ASSIGNED_BY_ID (квалификация) | 428 | Сотрудник "София AI" — защита от робота-распределителя |
| ASSIGNED_BY_ID (раздача) | 24932 | ID для запуска БП |
| TEMPLATE_ID | 152 | Бизнес-процесс проверки дублей и раздачи |
| Webhook URL | rest/426/uviwr0b350u3m6gf/ | С правами CRM + bizproc |

### Тильда

| Настройка | Значение |
|-----------|----------|
| Webhook в Битрикс | Стандартная интеграция Тильда → Б24 |
| Success redirect | `https://t.me/humanAINeural_bot?start=ATL` |

---

## 3. Конфигурация

### Переменные окружения (.env)

| Переменная | Значение (Атлантис) | Назначение |
|------------|---------------------|-----------|
| BITRIX_BASE_URL | https://oazisestate.bitrix24.ru/rest/426/uviwr0b350u3m6gf/ | Webhook URL (права: crm + bizproc) |
| BITRIX_BP_TEMPLATE_ID | 152 | ID бизнес-процесса раздачи |
| BITRIX_BP_ASSIGNED_ID | 24932 | Ответственный перед запуском БП |
| BITRIX_SOURCE_ID | 504 | Источник для новых лидов (default, не Тильда) |
| BITRIX_ASSIGNED_ID | 426 | Fallback ответственный |

### Хардкод в коде (TODO: вынести в env при масштабировании)

| Константа | Файл | Строка | Значение | Назначение |
|-----------|------|--------|----------|-----------|
| SOFIA_AI_USER_ID | core/bitrix.py | 37 | 428 | Ответственный на время квалификации |
| BITRIX_ATLANTIS_SOURCE_ID | core/bitrix.py | 36 | "397" | SOURCE_ID лидов от Тильды/Атлантис |

При масштабировании на нового клиента эти значения будут другими. Нужно вынести в .env или в config/source_objects.py с маппингом по source_object.

### Права webhook-токена

Минимальные скоупы: `crm` (лиды), `bizproc` (бизнес-процессы).
Без `bizproc` — ошибка "The request requires higher privileges than provided by the webhook token".

---

## 4. Таймауты (только Telegram)

| Сценарий | Константа | Время | Условие | Результат |
|----------|-----------|-------|---------|-----------|
| A: Нет ответа | TIMEOUT_NO_RESPONSE | 15 мин | 0 сообщений от клиента после /start | finalize с "no_response" |
| B: Напоминание | TIMEOUT_REMINDER | 60 мин | Клиент отвечал, потом замолчал | Отправка напоминания |
| B+: После напоминания | TIMEOUT_AFTER_REMINDER | 15 мин | Молчание после напоминания | finalize с "no_response_after_reminder" |

Web-виджет таймаутов не имеет — лид финализируется только если LLM вернёт [END].

---

## 5. Дедупликация

При создании лида (`create_or_update_lead`) проверяется:
1. **Локальная БД** (telegram_leads / web_sessions) — есть ли уже lead_id для этого user
2. **Битрикс API** (`crm.lead.list` по PHONE, STATUS_ID=NEW) — есть ли лид с таким телефоном

Если найден — обновляем существующий, не создаём новый.

Ограничение: поиск только по STATUS_ID=NEW. Если лид переведён в другую стадию — дубль возможен.

---

## 6. БД таблицы (ключевые для flow)

### telegram_leads
```sql
user_id INTEGER PRIMARY KEY    -- Telegram user ID
bitrix_lead_id INTEGER         -- Привязанный лид в Битрикс
```

### lead_assigned
```sql
lead_id INTEGER PRIMARY KEY         -- Битрикс lead ID
original_assigned_by_id INTEGER     -- Кто был ответственным до Софии
```

### client_state (ключевые поля)
```sql
source_object TEXT          -- 'atlantis' → активирует Bitrix-интеграцию
dialog_finished BOOLEAN     -- Диалог завершён
finish_type TEXT            -- 'meeting' | 'no_response' | 'no_response_after_reminder' | 'llm_end'
manager_active INTEGER      -- 1 = менеджер перехватил, София молчит
```

### web_sessions
```sql
session_id TEXT PRIMARY KEY    -- UUID
user_id INTEGER UNIQUE         -- Web user ID (9M+)
bitrix_lead_id INTEGER         -- Привязанный лид
page_url TEXT                  -- URL страницы с виджетом
```

---

## 7. Source objects — маппинг

Файл: `config/source_objects.py`

Каждый объект определяет:
- `key` — идентификатор (например "atlantis")
- `keywords` — триггеры для /start (например ["атлантис", "atlantis", "#ATL"])
- `context` — путь к файлу с контекстом объекта
- `prompt_addon` — дополнение к системному промпту
- `source_id` — SOURCE_ID в Битрикс для поиска лида Тильды

### Текущие объекты

| Key | /start параметр | SOURCE_ID | Контекст |
|-----|-----------------|-----------|----------|
| atlantis | ATL | 397 | objects/atlantis_context.md |

---

## 8. Каналы и их статус

| Канал | Файл | Статус | Bitrix лиды | finalize_lead | Таймауты |
|-------|------|--------|-------------|---------------|----------|
| Telegram бот | bot_server.py | PROD | Да (source-сессии) | Да | Да (15/60/15) |
| Web-виджет | web_api.py | PROD (не используется) | Да (каждое сообщение) | Да (по [END]) | Нет |
| Radist (Max/TG/WA) | sofia_radist_gateway.py | PROD | Нет (P1 задача) | Нет | Нет |
| Voice (Retell) | voice_api.py | DEV | Нет | Нет | Нет |

Radist создаёт лиды через свою интеграцию с Битрикс — наш код их не видит, finalize_lead не вызывается.

---

## 9. Масштабирование на нового клиента

### Что нужно от клиента (Битрикс):
1. Битрикс24 аккаунт с webhook (права: CRM + bizproc)
2. SOURCE_ID для лидов с его сайта
3. ID сотрудника-"робота" (аналог 428) — чтобы лиды не уходили в распределение пока София квалифицирует
4. ID сотрудника для запуска БП (аналог 24932)
5. TEMPLATE_ID бизнес-процесса раздачи
6. Сайт на Тильде (или другой платформе) с формой захвата

### Что настраиваем мы (код):
1. Параметр /start для Telegram бота (например `/start NEWCLIENT`)
2. Объект в `config/source_objects.py`:
   ```python
   "crimea_spa": {
       "key": "crimea_spa",
       "keywords": ["крымспа", "crimea_spa", "#CRIMSPA"],
       "context": "objects/crimea_spa_context.md",
       "prompt_addon": "...",
       "source_id": "505",
   }
   ```
3. Файл контекста `objects/crimea_spa_context.md`
4. Переменные в .env: BITRIX_BASE_URL, BP_TEMPLATE_ID, BP_ASSIGNED_ID
5. Вынести хардкоды SOFIA_AI_USER_ID и BITRIX_ATLANTIS_SOURCE_ID в конфиг
6. Рефакторинг `find_recent_atlantis_lead()` → универсальный `find_recent_lead_by_source(source_id)`

### Что настраивает клиент (или его программист):
1. Webhook Тильда → Битрикс (создание лида с нужным SOURCE_ID)
2. Redirect с Тильды в Telegram бот (`t.me/humanAINeural_bot?start=PARAM`)
3. Сотрудник "AI" в Битрикс (ASSIGNED_BY_ID для квалификации)
4. Бизнес-процесс раздачи (или используем стандартный)
5. Права webhook на bizproc

### Тест-чеклист
- [ ] Форма на Тильде создаёт лид в Битрикс с правильным SOURCE_ID
- [ ] Redirect ведёт на PROD-бота (не dev!)
- [ ] /start PARAM находит лид и привязывает
- [ ] Через 15 мин: ASSIGNED_BY_ID сменился на BP_ASSIGNED_ID
- [ ] Через 15 мин: BP started в логах
- [ ] Лид ушёл в раздачу (статус изменился)

---

## 10. Известные ограничения

1. `find_recent_atlantis_lead()` ищет **последний** лид с SOURCE_ID=397. Если два клиента заполнят форму одновременно — второй может привязаться к лиду первого. Нужен поиск по телефону или имени
2. Дедупликация по телефону ищет только STATUS_ID=NEW. Переведённые лиды — дубль возможен
3. Web-виджет не имеет таймаута — если клиент бросил диалог, лид финализируется только по [END]
4. Если клиент не перешёл в Telegram после формы — лид в Битрикс есть, но квалификации нет
5. Radist-канал не интегрирован с Bitrix — лиды создаёт сам Radist, наш finalize_lead не вызывается

---

## 11. Уроки из внедрения (2026-04-04)

| Проблема | Причина | Фикс |
|----------|---------|------|
| Дубли лидов | Нет проверки по телефону перед созданием | `find_lead_by_phone()` в `create_or_update_lead()` |
| БП не запускался | Код finalize_lead не задеплоен в прод | Деплой finalize_lead + start_distribution_bp |
| Ответственный 428 блокировал БП | БП требует ASSIGNED_BY_ID=24932 | finalize_lead ставит 24932 перед БП |
| Таймаут крашился | manager_active не в state_manager.py, INSERT OR REPLACE затирал колонку | Добавлен в ClientState, get_state, _save_state, CREATE TABLE |
| Миграция только в web-api | bot_server.py не добавлял колонку manager_active | ALTER TABLE миграции в init_db() бота |
| Логи бота не в journalctl | bot_server.py пишет в файл через print() | Логи в /opt/sofia-gpt/sofia_bot.log (не journalctl!) |
| Тильда редиректила на dev-бота | Неправильная ссылка SofiaDev01_bot | Замена на t.me/humanAINeural_bot |
| Webhook без прав на bizproc | Старый токен z61d... без скоупа bizproc | Новый токен uviw... с правами crm+bizproc |
