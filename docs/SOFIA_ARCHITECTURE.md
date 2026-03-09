# Sofia-GPT v3.0 — Архитектура проекта

> Единый документ. Заменяет: SOFIA_CONTEXT.md, SOFIA_ARCHITECTURE.md, SOFIA_PROJECT_MAP.md.
> Обновлён: 09.03.2026

---

## §1. Продукт

**Oazis Estate** — агентство курортной недвижимости. Регионы: Сочи, Крым.
**Sofia-GPT** — AI-бот для квалификации лидов и конвертации в видео-консультацию с живым экспертом.

Ключевой объект: **ЖК "Атлантис"** (Сочи, Хостинский район). Цены от 16.8 млн ₽. Прайс → `docs/ATLANTIS_PRICES.md`.

Философия: доверяем LLM с полным контекстом (state_summary + RAG + промпт) вместо жёсткого Planner. Принцип "ЭКСПЕРТ, НЕ ОБСЛУГА" — София не соглашается со всеми возражениями, а контраргументирует с позиции эксперта.

---

## §2. Инфраструктура

### Серверы
| Среда | Путь | Порты | БД |
|-------|------|-------|-----|
| **Прод** | `/opt/sofia-gpt/` | 8080 (web), 5001 (radist) | `sofia_gpt.db` |
| **Dev** | `/opt/sofia-gpt-dev/` | 8081 (web-dev) | `sofia_gpt_dev.db` |

- **IP:** 72.56.64.91:2222 (SSH)
- **Python:** 3.x, OpenAI API (gpt-5.2, Responses API)
- **RAG:** ChromaDB, text-embedding-3-small, 1965 примеров

### Сервисы (systemd)
| Сервис | Порт | Среда | Назначение |
|--------|------|-------|------------|
| `sofia-web-api.service` | 8080 | Прод | Web API для виджета |
| `sofia-web-api-dev.service` | 8081 | Dev | Web API для разработки |
| `sofia-radist.service` | 5001 | Прод | Radist gateway (Telegram outreach) |
| Telegram бот | — | Прод | Long polling через Bot API |

### Внешние сервисы
- **Nginx** — reverse proxy, SSL (Let's Encrypt, certbot автообновление)
- **DNS:** `api.atlantis-invest.ru` → 72.56.64.91 (A-запись в reg.ru)
- **Сайты:** atlantis-invest.ru, invest-apartmens.online/atlantis, sochiremstroy.tilda.ws
- **Bitrix CRM:** oazisestate.bitrix24.ru
- **Radist.Online:** api-ru.radist.online/v2 (company_id: 205054, connection_id: 80200)

### Инструменты разработки
- **Claude Code** — AI-ассистент в терминале, запускается в `/opt/sofia-gpt-dev/`
- **SQLite MCP** — прямой доступ к `sofia_gpt_dev.db` из Claude Code (`.mcp.json`)
- **deploy.sh** — rsync dev→prod с исключениями (.db, .env, __pycache__), рестарт prod-сервисов, health check
- **flake8 + black** — линтер и форматтер

### Защита userbot от рестартов
systemd: `StartLimitBurst=5`, `StartLimitIntervalSec=600`. Бесконечные рестарты блокируют Telegram аккаунт на 1-24ч.

---

## §3. Архитектура v3.0

### Три сценария использования

Sofia работает в трёх базовых сценариях:

1. **Telegram-бот** (`@humanAINeural_bot`) — входящие лиды пишут боту, София квалифицирует и конвертирует в созвон. Работает через Bot API бесплатно.

2. **Radist gateway** (исходящие) — через Radist.Online подключены номерные аккаунты Telegram для cold outreach. Max мессенджер ЗАБАНЕН (массовая рассылка → перманентный бан номера). Планируется замена на WABA.

3. **Web-виджет** (сайты недвижимости) — чат-виджет на сайтах со своими надстройками: localStorage persistence, укороченная квалификация (макс 3 вопроса), обязательный сбор контакта перед [END]. Установлен на atlantis-invest.ru, invest-apartmens.online, sochiremstroy.tilda.ws. Установка → `docs/WIDGET_INSTALL.md`.

### Пайплайн обработки сообщений

Единый для всех трёх сценариев:

```
Клиент → [Канал] → process_message()
                         ↓
                    Extractor (gpt-5.2)     — NLU, извлечение фактов
                         ↓
                    State Manager           — обновление client_state в БД
                         ↓
                    state_summary            — текстовое описание состояния
                         ↓
                    Analyzer (gpt-5.2)       — читает ВСЮ историю, решает что делать
                         ↓
                    RAG (ChromaDB)           — 5-10 релевантных примеров
                         ↓
                    Generator (gpt-5.2)      — финальный ответ
                         ↓
                    Observer                 — трансляция в группу наблюдения
                         ↓
                    [END] → Bitrix CRM       — автоотправка лида
```

### Ключевые файлы

| Файл | Роль |
|------|------|
| `message_processor.py` | Extractor → State → Signals |
| `extractor.py` | NLU, извлечение фактов из сообщения |
| `state_manager.py` | ClientState, SQLite persistence |
| `sofia_prompt_v2.py` | Промпт генератора (включая финансовую экспертизу) |
| `rag_module.py` | Векторный поиск примеров (ChromaDB) |
| `finance_calculator.py` | Сравнение недвижимости vs депозит |
| `finance_data.json` | Ставка ЦБ 15.5%, прогнозы, параметры расчётов |
| `web_api.py` | FastAPI сервер для виджета (порт 8080) |
| `sofia_radist_gateway.py` | Radist webhook сервер (порт 5001) |
| `bot_server.py` | Telegram бот (long polling) |
| `message_queue.py` | Lock + очередь (защита от race condition) |
| `deploy.sh` | Деплой dev→prod |
| `CLAUDE.md` | Инструкция для Claude Code (в dev-каталоге) |
| `.mcp.json` | SQLite MCP конфиг для Claude Code |

### Архитектурный долг
Логика Analyzer→RAG→Generator продублирована в трёх файлах (bot_server.py, web_api.py, radist_gateway.py). TODO: единый `core/` модуль — транспорты только получают/отправляют сообщения.

---

## §4. База данных (SQLite)

### Таблицы

| Таблица | Назначение |
|---------|------------|
| `messages` | История диалогов (role, content, user_id, timestamp) |
| `client_state` | Состояние клиента (goal, budget, location, branch, lead_type...) |
| `feedback_v2` | Оценки качества (rating, comment) |
| `web_sessions` | Маппинг session_id → user_id для веб-виджета |
| `observer_topics` | Маппинг phone → thread_id для тем в группе наблюдения |

### Формулы user_id

**Критично** — все части системы должны использовать одинаковые формулы:

| Канал | Формула | Диапазон |
|-------|---------|----------|
| Telegram бот | `user_id = telegram_user_id` | положительные |
| Max (Radist) | `user_id = -(1_000_000 + chat_id)` | -1_000_001... |
| Telegram (Radist) | `user_id = -(2_000_000 + chat_id)` | -2_000_001... |
| WhatsApp (Radist) | `user_id = -(3_000_000 + chat_id)` | -3_000_001... |
| Web-виджет | `user_id = 9_000_000 + autoincrement` | 9_000_001... |

⚠️ **Опасность:** Коллизия user_id = смешанные переписки двух клиентов. Раньше использовался hash() — давал коллизии при рестарте Python (менялся seed). Исправлено на автоинкремент.

---

## §5. Каналы — детали

### Telegram бот (@humanAINeural_bot)
- Файл: `bot_server.py`
- Статус: ✅ работает, source routing, 2 сообщения greeting
- Входящие через Bot API (бесплатно)
- ⚠️ Bitrix интеграция НЕ подключена (лиды теряются)

### Radist Gateway (Telegram outreach)
- Файл: `sofia_radist_gateway.py`
- Порт: 5001
- API: `https://api-ru.radist.online/v2`
- company_id: 205054, connection_id: 80200
- Номер: +79181038493 (@SofiaOazis)
- Статус: ✅ работает, source routing
- ⚠️ Bitrix интеграция НЕ подключена
- Max: ❌ ЗАБАНЕН (массовая рассылка)

**API Radist — ключевые моменты:**
- Все эндпоинты требуют `/companies/{company_id}/` в пути
- `chat_id` — число, не телефон. Сначала создать чат, потом отправлять
- Формат text — объект `{"text": "сообщение"}`, не строка

### Web API (виджет на сайтах)
- Файл: `web_api.py`
- Порт: 8080, через nginx → `api.atlantis-invest.ru`
- SSL: Let's Encrypt
- CORS: atlantis-invest.ru, invest-apartmens.online, sochiremstroy.tilda.ws
- Статус: ✅ работает, обновлённый промпт
- ✅ Bitrix интеграция подключена (единственный канал!)
- localStorage persistence + `/api/session/resume`
- `/api/docs/file` — эндпоинт для чтения документации Claude'ом

### WABA (план)
- Замена Max для массовых рассылок
- Подключение через 360Dialog напрямую (без Radist — экономия ~5000₽/мес)
- Ограничения Meta: не работает для Крыма, Донецка, Луганска, Турции
- Первое сообщение — только через одобренный шаблон (HSM), после ответа — 24ч свободный диалог

### Observer (наблюдение за диалогами)
- Telegram группа с включёнными темами (супергруппа)
- Каждый клиент = отдельная тема (таблица `observer_topics`)
- Функция `broadcast_to_observers()` после каждого ответа
- ⚠️ ОТКЛЮЧЁН (OBSERVER_CHAT_ID закомментирован в .env)

---

## §6. Bitrix CRM

### Webhook
- URL: `oazisestate.bitrix24.ru/rest/426/z61dwivdmdy9dk4f/`
- SOURCE_ID: 504
- ASSIGNED_BY_ID: 426 (тест) → **24932 (прод)** ⚠️ ждём программиста
- Механизм: POST `crm.lead.add` с полями из client_state при маркере [END]

### Текущее состояние
- ✅ Работает в `web_api.py` (send_lead_to_bitrix)
- ❌ НЕ подключен в `bot_server.py` — лиды из Telegram теряются
- ❌ НЕ подключен в `radist_gateway.py` — лиды из outreach теряются

---

## §7. Промпт и поведение

### Веб-стратегия (анонимные клиенты)
- Макс 3 вопроса (цель/бюджет/оплата)
- Давать ценность сразу, не допрашивать
- Контакт обязателен перед [END]
- Конкретные цены — только после сбора контакта

### Холодные vs горячие лиды
- `lead_type` (cold/warm/hot) в БД — устанавливается при outreach
- Cold → "ещё актуально?" (мягко)
- Warm → "удобно пообщаться?" (уверенно)
- Hot → "подготовили подборку" (конкретно)

### Source routing
- `detect_source()` определяет объект по referrer/параметрам
- Клиент с atlantis-invest.ru → source_object=atlantis → контекст Атлантиса без вопроса "где смотрите?"
- `skip_analyzer` при первых сообщениях с source_object → force GREETING
- Инструкции объекта → `objects/{объект}_context.md`

### Финансовая экспертиза
- Готовый расчёт в промпте: 17 млн → недвижимость 41 млн (+139%) vs депозит 24 млн (+40%)
- Ставка ЦБ: **15.5%** (finance_data.json актуален)
- Бесплатная экспертиза = доверие

---

## §8. Рабочий процесс (dev → prod)

```
1. Открыть новый чат claude.ai со ссылками &v=YYYYMMDD
2. Обсудить задачу, получить план
3. ssh root@72.56.64.91 -p 2222
4. cd /opt/sofia-gpt-dev && claude   ← Claude Code
5. Выполнить задачу в dev, протестировать на порту 8081
6. ./deploy.sh                        ← деплой в прод
7. Проверить prod: curl https://api.atlantis-invest.ru/api/health
8. Обновить документацию (SOFIA_CURRENT.md, SOFIA_TASKS.md)
9. git add -A && git commit && git push
```

---

## §9. Быстрые команды

```bash
# === Сервисы ===
systemctl status sofia-web-api
systemctl restart sofia-web-api
systemctl status sofia-web-api-dev
systemctl restart sofia-web-api-dev
systemctl status sofia-radist

# === Логи ===
tail -f /opt/sofia-gpt/web_api.log
tail -f /opt/sofia-gpt/sofia_radist.log
journalctl -u sofia-web-api -f

# === Health check ===
curl -s https://api.atlantis-invest.ru/api/health          # прод
curl -s http://localhost:8081/api/health                   # dev

# === БД прод ===
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT * FROM client_state WHERE user_id = ID;"
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT role, content, timestamp FROM messages WHERE user_id = ID ORDER BY timestamp;"
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT * FROM client_state WHERE user_id >= 9000000;"

# === БД dev ===
sqlite3 /opt/sofia-gpt-dev/sofia_gpt_dev.db "SELECT * FROM client_state;"

# === Деплой ===
cd /opt/sofia-gpt-dev && ./deploy.sh

# === Поиск в коде ===
grep -rn "ТЕКСТ" /opt/sofia-gpt/*.py

# === Промпт: проверить секции перед патчем ===
grep -A1 "═══" /opt/sofia-gpt/sofia_prompt_v2.py
```

---

## §10. Правила работы

### Перед любыми изменениями
1. **Работать в dev** `/opt/sofia-gpt-dev/` — не трогать прод напрямую
2. **Бэкап** с таймштампом: `cp file.py file.py.backup_$(date +%Y%m%d_%H%M%S)`
3. **git commit** с описательным сообщением
4. **Тест на dev** (порт 8081) перед деплоем

### Инкрементальный подход
- Одна проблема за раз
- Тест после каждого изменения
- Не трогать работающие сервисы без необходимости

### Чего НЕ делать
- **Не использовать gpt-5.2 с temperature** — не поддерживается
- **Не полагаться на LLM для счёта** — выносить в код
- **Не проверять WAIT по тексту** — только через state
- **Не добавлять общие слова в маркеры** — ложные срабатывания
- **Для reasoning моделей** нужен 3-5x запас по max_output_tokens (BUG-003)
- **Не давать ссылки без &v=YYYYMMDD** — Claude закэширует старую документацию
- **Не патчить промпт без cat** — названия секций могут отличаться

---

## §11. Документация

| Файл | Назначение | Обновление |
|------|------------|------------|
| `SOFIA_ARCHITECTURE.md` | Этот файл. Полная карта проекта | При изменениях архитектуры → обновить в Project Knowledge |
| `SOFIA_CURRENT.md` | Статус последней сессии | Каждую сессию |
| `SOFIA_TASKS.md` | Задачи и приоритеты | При изменении задач |
| `SOFIA_KNOWLEDGE.md` | Уроки и принципы | При новых открытиях |
| `SOFIA_CALLBACKS.md` | Паттерны диалогов и возражений | При изменении скрипта продаж |
| `SOFIA_BUGS.md` | Баги с деталями и откатом | При новых багах |
| `KNOWLEDGE_INDEX.md` | Хронологический лог изменений | Каждую сессию |
| `ATLANTIS_PRICES.md` | Прайс Атлантиса | При изменении цен |
| `WIDGET_INSTALL.md` | Установка виджета | При изменении API |
| `SESSION_END_TEMPLATE.md` | Шаблон закрытия сессии | Редко |
| `SESSION_GUIDE.md` | Чеклист начала/конца сессии | Редко |
