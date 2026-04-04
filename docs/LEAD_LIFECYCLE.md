# Lead Lifecycle — полная архитектура

> Документ описывает весь процесс от заявки на сайте до раздачи лида менеджеру.
> Актуален на 2026-04-04. При масштабировании на новые сайты — использовать как чеклист.

## 1. Общая схема (ATL flow)

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

## 2. Компоненты и файлы

| Компонент | Файл | Строки | Что делает |
|-----------|------|--------|-----------|
| /start ATL handler | bot_server.py | 1146-1223 | Парсит параметр, ищет лид, привязывает, запускает таймаут |
| Таймаут A (нет ответа) | bot_server.py | 845-868 | 15 мин без ответа → finalize |
| Таймаут B (напоминание) | bot_server.py | 799-842 | 60 мин → напоминание → ещё 15 мин → finalize |
| delayed_response | bot_server.py | 871-1000 | Обработка сообщения, Bitrix update, проверка meeting_agreed |
| _finalize_timeout | bot_server.py | 762-796 | Финализация по таймауту: update лид + finalize_lead |
| _is_bitrix_session | bot_server.py | 156-159 | Проверка: source_object установлен? |
| create_or_update_lead | core/bitrix.py | 378-415 | Создать/обновить лид + дедупликация по телефону |
| find_lead_by_phone | core/bitrix.py | 179-214 | Поиск дубля по телефону через crm.lead.list |
| find_recent_atlantis_lead | core/bitrix.py | 219-251 | Поиск последнего лида Тильды (SOURCE_ID=397) |
| finalize_lead | core/bitrix.py | 621-625 | Смена ответственного на 24932 + запуск БП 152 |
| start_distribution_bp | core/bitrix.py | 581-618 | bizproc.workflow.start для БП 152 |
| set_lead_assigned | core/bitrix.py | 281-299 | crm.lead.update ASSIGNED_BY_ID |
| Bitrix webhook | web_api.py | 605-681 | Перехват менеджером → manager_active=1 |
| state_manager | state_manager.py | 269-355 | Хранение состояния клиента (включая manager_active) |

## 3. Таймауты

| Сценарий | Константа | Время | Условие | finish_type |
|----------|-----------|-------|---------|-------------|
| A: Нет ответа | TIMEOUT_NO_RESPONSE | 15 мин | 0 сообщений от клиента | no_response |
| B: Напоминание | TIMEOUT_REMINDER | 60 мин | Клиент отвечал, потом замолчал | (напоминание) |
| B+: После напоминания | TIMEOUT_AFTER_REMINDER | 15 мин | Молчание после напоминания | no_response_after_reminder |
| Созвон согласован | — | Сразу | meeting_agreed=True | meeting |
| LLM завершил | — | Сразу | Генератор вернул [END] | llm_end |

## 4. Битрикс интеграция

### Константы (.env)

| Переменная | Значение | Назначение |
|------------|----------|-----------|
| BITRIX_BASE_URL | https://oazisestate.bitrix24.ru/rest/426/uviwr0b350u3m6gf/ | Webhook URL (нужны права: crm, bizproc) |
| BITRIX_BP_TEMPLATE_ID | 152 | ID бизнес-процесса раздачи |
| BITRIX_BP_ASSIGNED_ID | 24932 | Ответственный перед запуском БП |
| BITRIX_SOURCE_ID | 504 | Источник для новых лидов (default) |
| BITRIX_ASSIGNED_ID | 426 | Fallback ответственный |

### Хардкод (core/bitrix.py)

| Константа | Значение | Назначение |
|-----------|----------|-----------|
| SOFIA_AI_USER_ID | 428 | Ответственный на время квалификации |
| BITRIX_ATLANTIS_SOURCE_ID | "397" | SOURCE_ID лидов от Тильды/Атлантис |

### Права webhook-токена

Минимальные скоупы: `crm` (лиды), `bizproc` (бизнес-процессы).

## 5. БД таблицы (ключевые для flow)

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
finish_type TEXT            -- Причина завершения
manager_active INTEGER      -- 1 = менеджер перехватил, София молчит
```

## 6. Source objects — маппинг

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

## 7. Каналы и их возможности

| Канал | Файл | Bitrix лиды | finalize_lead | Таймауты | Дедупликация |
|-------|------|-------------|---------------|----------|-------------|
| Telegram бот | bot_server.py | Да (source-сессии) | Да | Да (15/60/15) | Да |
| Web виджет | web_api.py | Да (каждое сообщение) | Да (по [END]) | Нет | Да |
| Radist | sofia_radist_gateway.py | Нет | Нет | Нет | — |

## 8. Чеклист для нового сайта

При масштабировании на новый объект (например "crimea_spa"):

### Тильда
- [ ] Создать форму на Тильде
- [ ] Настроить webhook Тильда → Битрикс (с уникальным SOURCE_ID)
- [ ] Success page: редирект на `t.me/humanAINeural_bot?start=CRIMSPA`

### Битрикс
- [ ] Зарегистрировать новый SOURCE_ID (например "505") для лидов с этого сайта
- [ ] Убедиться что webhook-токен имеет права crm + bizproc
- [ ] БП 152 обрабатывает лиды с новым SOURCE_ID

### Код Sofia
- [ ] Добавить объект в `config/source_objects.py`:
  ```python
  "crimea_spa": {
      "key": "crimea_spa",
      "keywords": ["крымспа", "crimea_spa", "#CRIMSPA"],
      "context": "objects/crimea_spa_context.md",
      "prompt_addon": "...",
      "source_id": "505",
  }
  ```
- [ ] Создать файл контекста `objects/crimea_spa_context.md`
- [ ] Обновить `find_recent_atlantis_lead()` или создать универсальный `find_recent_lead_by_source(source_id)` — сейчас хардкод на SOURCE_ID=397
- [ ] Тест: форма → Telegram → 15 мин → BP started

### Критичные нюансы
- `find_recent_atlantis_lead()` ищет **последний** лид с SOURCE_ID=397. Если два клиента заполнят форму одновременно — второй может привязаться к лиду первого. При масштабировании нужен более точный поиск (по телефону или имени из Тильды)
- Дедупликация `find_lead_by_phone()` ищет только лиды со STATUS_ID=NEW. Если лид переведён — дубль возможен
- Таймауты есть только в Telegram. Web-виджет не финализирует лиды по таймауту
- `manager_active` и `finance_interested` должны быть в state_manager.py (были баги)

## 9. Уроки из внедрения (2026-04-04)

| Проблема | Причина | Фикс |
|----------|---------|------|
| Дубли лидов | Нет проверки по телефону перед созданием | find_lead_by_phone() в create_or_update_lead() |
| БП не запускался | Код не задеплоен в прод | Деплой finalize_lead + start_distribution_bp |
| Ответственный 428 блокировал БП | БП требует ASSIGNED_BY_ID=24932 | finalize_lead ставит 24932 перед БП |
| Таймаут крашился | manager_active не в state_manager.py | Добавлен в ClientState, get_state, _save_state, CREATE TABLE |
| Логи бота не в journalctl | bot_server.py пишет в файл через print | Логи в /opt/sofia-gpt/sofia_bot.log |
| Тильда редиректила на dev-бота | Неправильная ссылка в Тильде | Замена на t.me/humanAINeural_bot |
| Webhook без прав на bizproc | Старый токен без скоупа | Новый токен с правами crm+bizproc |
