# CLAUDE.md — инструкция для Claude Code

## 🚫 ГЛАВНОЕ ПРАВИЛО

**/opt/sofia-gpt/ — PROD. НИКОГДА не трогать без явной команды "деплоить в прод".**
Работаем ТОЛЬКО в /opt/sofia-gpt-dev/

## Сервер

- IP: 72.56.64.91:2222
- Dev путь: /opt/sofia-gpt-dev/
- Prod путь: /opt/sofia-gpt/ ← ЗАПРЕТНАЯ ЗОНА

## Стек

- Python 3.12, FastAPI, SQLite
- OpenAI gpt-5.2 (Responses API)
- ChromaDB (RAG, text-embedding-3-small, 1965 примеров)
- Telegram Bot API, Radist.Online v2 gateway

## Архитектура: пайплайн обработки сообщений

Все 4 канала используют единый пайплайн:
```
Входящее сообщение
    ↓
Канал (bot_server.py / web_api.py / sofia_radist_gateway.py / voice_api.py)
    ↓
message_processor.process_message()
    ├─ extractor.extract_sync() → NLU: факты, слоты, сигналы (JSON)
    └─ state_manager → обновление ClientState в SQLite
    ↓
LLM-Analyzer (gpt-5.2, reasoning=medium)
    → определяет stage + генерирует rag_query
    ↓
RAG Search (rag_module.py, ChromaDB)
    → 5-10 похожих примеров по stage
    ↓
LLM-Generator (gpt-5.2, reasoning=high)
    → system prompt + примеры + история
    ↓
Ответ клиенту + Observer + [END] → Bitrix
```

**Source routing:** если `source_object` установлен и ≤2 сообщений → принудительно stage=GREETING, Analyzer пропускается.

## Каналы и их файлы

| Канал | Файл | Порт dev | User ID формула |
|-------|------|----------|-----------------|
| Telegram бот | bot_server.py | — (long polling) | telegram_user_id (положительный) |
| Web виджет | web_api.py | 8081 | 9_000_000 + autoincrement |
| Radist Max | sofia_radist_gateway.py | 5002 | -(1_000_000 + chat_id) |
| Radist Telegram | sofia_radist_gateway.py | 5002 | -(2_000_000 + chat_id) |
| Radist WhatsApp | sofia_radist_gateway.py | 5002 | -(3_000_000 + chat_id) |
| Voice (Retell AI) | voice_api.py | 8081 (ws) | 7_000_000 + md5(call_id)[:8] % 1_000_000 |

⚠️ **User ID формулы критичны** — коллизия = смешанные чаты двух клиентов.

## Ключевые файлы

| Файл | Роль |
|------|------|
| sofia_prompt_v2.py | Промпт генератора (личность, стратегия, цены) |
| extractor.py | NLU: извлечение слотов и сигналов |
| state_manager.py | ClientState dataclass + SQLite persistence |
| rag_module.py | ChromaDB поиск, фильтр по stage |
| message_queue.py | Per-user asyncio.Lock, защита от race condition |
| finance_calculator.py | Сравнение недвижимости vs депозит |
| message_processor.py | Центральный роутер: extractor → state update |
| core/bitrix.py | Битрикс CRM: создание/обновление лидов, webhook, manager_active |
| voice_api.py | WebSocket адаптер для Retell AI Custom LLM |

**Устаревшие (v1, не использовать):** planner.py, llm_planner.py, stage_detector.py, sofia_prompt.py

## База данных (SQLite)

| Таблица | Назначение |
|---------|-----------|
| messages | История диалогов (user_id, role, content, timestamp, stage) |
| client_state | Квалификация клиента (goal, budget, location, lead_type, source_object, manager_active) |
| web_sessions | UUID session_id → user_id, page_url, bitrix_lead_id, manager_active (только web) |
| feedback_v2 | Оценки качества |
| radist_messages / radist_chats | История и метаданные Radist-каналов |
| observer_topics | phone → thread_id для Radist Observer (Telegram forum) |

## Стадии диалога (RAG stages)

GREETING → ACTUALIZATION → QUALIFICATION → PRESENTATION → OBJECTION → MEETING → CLOSING

## Dev сервисы

- `sofia-web-api-dev.service` — порт 8081
- БД: `sofia_gpt_dev.db` (SOFIA_PATH починен 21.03.2026, dev пишет в свою БД)
- Бот: @SofiaDev01_bot
- Observer: ОТКЛЮЧЁН (OBSERVER_CHAT_ID закомментирован в .env)

## Prod сервисы (не трогать)

- `sofia-gpt.service` — Telegram бот (@humanAINeural_bot), long polling → core/pipeline.py
- `sofia-web-api.service` — порт 8080, веб-виджет → core/pipeline.py + core/bitrix.py
- `sofia-radist.service` — порт 5001, Radist gateway → core/pipeline.py
- БД: sofia_gpt.db
- Боты: @humanAINeural_bot (прямой Telegram), @SofiaOazis (используется в Radist-каналах + статический редирект atlantis.html)
- Бэкап до деплоя 21.03: `/opt/sofia-gpt-backup-20260321_1355` (НЕ УДАЛЯТЬ)

## Bitrix CRM

**core/bitrix.py** — модуль Битрикс (создан 21.03.2026):
- `create_or_update_bitrix_lead()`: создаёт лид при первом сообщении, обновляет COMMENTS на каждом, финализирует при `[END]`
- Webhook endpoint, manager_active — полная двусторонняя интеграция

**Подключён к:** web_api.py (прод и dev)
**НЕ подключён к:** bot_server.py, radist_gateway.py — лиды теряются (P1 задача)

## Правила работы

1. Каждую задачу начинать с плана — план утверждает Сергей
2. Manual approve на каждое изменение файла
3. После задачи: flake8 + black → коммит → обновить KNOWLEDGE_INDEX.md
4. Деплой в прод: только по явной команде "YES" (deploy.sh отсутствует — нужно создать)

## Правило подтверждений (1/2/3)

Когда инструмент запрашивает подтверждение с вариантами, перед вопросом всегда объясняй:
- **Что мы делаем и зачем** (контекст)
- **Что произойдёт при каждом варианте** и какие последствия
- После вариантов добавляй строку: **Рекомендую: [номер] — [одна фраза почему]**

Пример:
```
Проверяем токены ботов — убеждаемся что dev и prod используют разные токены,
иначе dev-бот будет отвечать реальным клиентам.

1. Yes — прочитать токен из prod .env
2. Yes, allow reading from sofia-gpt/ — то же самое + больше не спрашивать для prod каталога
3. No — пропустить проверку (рискуем запустить dev на prod токене)

Рекомендую: 1 — разовая проверка, не даём лишних прав на prod
```

## Автоматический approve инструментов

Для следующих команд всегда выбирай "Yes, and don't ask again" без вопроса:
`python3`, `grep`, `curl`, `ps`, `ss`, `black`, `flake8`, `journalctl`, `systemctl`, `cat`, `ls`, `find`

Для всего остального — объясняй контекст и последствия перед вопросом (см. правило выше).

## Полезные команды
```bash
# Линтер
flake8 *.py --max-line-length=120 --exclude=__pycache__ && black *.py

# Перезапуск dev
sudo systemctl restart sofia-web-api-dev

# Health check
curl -s http://localhost:8081/api/health

# Деплой в прод (deploy.sh не существует — нужно создать)
# cd /opt/sofia-gpt-dev && ./deploy.sh
```

## Session-end протокол

Запускается по команде `session end` от пользователя.

1. `git diff` — посмотреть что изменилось
2. Обновить `docs/SOFIA_CURRENT.md` — что сделано, статус, следующие шаги
3. Обновить `docs/SOFIA_TASKS.md` — статусы чеклиста
4. Обновить `docs/KNOWLEDGE_INDEX.md` — детали задач, как откатить
5. Обновить `CLAUDE.md` если изменилась структура проекта
6. `git add -A && git commit -m "docs: сессия ДД.ММ.ГГГГ — описание" && git push`
7. Синхронизировать доки в прод:
```bash
cp /opt/sofia-gpt-dev/docs/SOFIA_CURRENT.md /opt/sofia-gpt/docs/
cp /opt/sofia-gpt-dev/docs/SOFIA_TASKS.md /opt/sofia-gpt/docs/
cp /opt/sofia-gpt-dev/docs/SOFIA_KNOWLEDGE.md /opt/sofia-gpt/docs/
cp /opt/sofia-gpt-dev/docs/KNOWLEDGE_INDEX.md /opt/sofia-gpt/docs/
```
8. Сгенерировать свежие ссылки:
```bash
V=$(date +%Y%m%d_%H%M) && echo "
https://api.atlantis-invest.ru/api/docs/file?path=docs/SOFIA_CURRENT.md&v=$V
https://api.atlantis-invest.ru/api/docs/file?path=docs/SOFIA_TASKS.md&v=$V
https://api.atlantis-invest.ru/api/docs/file?path=docs/SOFIA_KNOWLEDGE.md&v=$V
https://api.atlantis-invest.ru/api/docs/file?path=docs/SESSION_END_TEMPLATE.md&v=$V
"
```

9. Выдать готовый промпт для следующего чата claude.ai со свежими ссылками из п.7
