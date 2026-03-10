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
| voice_api.py | WebSocket адаптер для Retell AI Custom LLM |

**Устаревшие (v1, не использовать):** planner.py, llm_planner.py, stage_detector.py, sofia_prompt.py

## База данных (SQLite)

| Таблица | Назначение |
|---------|-----------|
| messages | История диалогов (user_id, role, content, timestamp, stage) |
| client_state | Квалификация клиента (goal, budget, location, lead_type, source_object) |
| web_sessions | UUID session_id → user_id (только web) |
| feedback_v2 | Оценки качества |
| radist_messages / radist_chats | История и метаданные Radist-каналов |

## Стадии диалога (RAG stages)

GREETING → ACTUALIZATION → QUALIFICATION → PRESENTATION → OBJECTION → MEETING → CLOSING

## Dev сервисы

- `sofia-web-api-dev.service` — порт 8081, БД: sofia_gpt_dev.db
- Бот: @SofiaDev01_bot
- Observer: ОТКЛЮЧЁН (OBSERVER_CHAT_ID закомментирован в .env)

## Prod сервисы (не трогать)

- `sofia-web-api.service` — порт 8080
- `sofia-radist.service` — порт 5001
- БД: sofia_gpt.db, Бот: @humanAINeural_bot

## Bitrix CRM

`send_lead_to_bitrix()` вызывается при маркере `[END]`. Сейчас работает только в web_api.py.
bot_server.py и radist_gateway.py — НЕ подключены (лиды теряются).

## Правила работы

1. Каждую задачу начинать с плана — план утверждает Сергей
2. Manual approve на каждое изменение файла
3. После задачи: flake8 + black → коммит → обновить KNOWLEDGE_INDEX.md
4. Деплой в прод: только через deploy.sh и только по явной команде "YES"

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

# Деплой в прод
cd /opt/sofia-gpt-dev && ./deploy.sh
```

## Session-end протокол

Запускается по команде `session end` от пользователя.

1. `git diff` — посмотреть что изменилось
2. Обновить `docs/SOFIA_CURRENT.md` — что сделано, статус, следующие шаги
3. Обновить `docs/SOFIA_TASKS.md` — статусы чеклиста
4. Обновить `docs/KNOWLEDGE_INDEX.md` — детали задач, как откатить
5. Обновить `CLAUDE.md` если изменилась структура проекта
6. `git add -A && git commit -m "docs: сессия ДД.ММ.ГГГГ — описание" && git push`
7. Сгенерировать свежие ссылки:
```bash
V=$(date +%Y%m%d_%H%M) && echo "
https://api.atlantis-invest.ru/api/docs/file?path=docs/SOFIA_CURRENT.md&v=$V
https://api.atlantis-invest.ru/api/docs/file?path=docs/SOFIA_TASKS.md&v=$V
https://api.atlantis-invest.ru/api/docs/file?path=docs/SOFIA_KNOWLEDGE.md&v=$V
https://api.atlantis-invest.ru/api/docs/file?path=docs/SESSION_END_TEMPLATE.md&v=$V
"
```

8. Выдать готовый промпт для следующего чата claude.ai со свежими ссылками из п.7
