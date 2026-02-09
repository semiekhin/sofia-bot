# Sofia-GPT v3.0

AI-бот для продажи курортной недвижимости Oazis Estate. Квалифицирует лидов через мессенджеры, конвертирует в видео-консультации.

## Инфраструктура
- **Сервер:** 72.56.64.91:2222 (SSH)
- **Путь:** /opt/sofia-gpt/
- **Бот:** @humanAINeural_bot
- **Сервис:** sofia-radist.service (порт 5001)
- **База:** sofia_gpt.db (SQLite)

## Каналы (на 07.02.2026)
- **Max:** ❌ ЗАБАНЕН (номер заблокирован после массовой рассылки)
- **Telegram:** ⚠️ работает для входящих, не может писать первым
- **WABA:** ⏳ не подключен — приоритет №1 (Radist.Online + 360Dialog)
- **Виджет на сайте:** ⏳ планируется

## Стек
- Python 3 + aiohttp (webhook сервер, порт 5001)
- OpenAI API (gpt-5.2, Responses API)
- ChromaDB (RAG, 2001 пример)
- Radist.Online (Max, Telegram; вопрос — нужен ли Radist вообще?)

## Архитектура v3.0
```
Webhook → Extractor (gpt-5.2) → State → Analyzer (gpt-5.2) → RAG → Generator (gpt-5.2) → Ответ
```

Философия: доверяем LLM с полным контекстом (state_summary + RAG + промпт) вместо жёсткого Planner.

## Ключевые файлы
- `sofia_radist_gateway.py` — webhook сервер (порт 5001), Analyzer, RAG, Generator
- `message_processor.py` — Extractor → State → Signals
- `extractor.py` — NLU, извлечение фактов из сообщений
- `state_manager.py` — состояние клиента (SQLite)
- `sofia_prompt_v2.py` — промпт генератора (включая блок "ЭКСПЕРТ")
- `rag_module.py` — векторный поиск примеров (ChromaDB)
- `sofia_outreach.sh` — скрипт для outreach (cold/warm/hot)
- `config/radist_config.py` — конфигурация каналов и вебхука

## Быстрые команды
```bash
# Рестарт
systemctl restart sofia-radist

# Логи
tail -f /opt/sofia-gpt/sofia_radist.log

# Статус
systemctl status sofia-radist

# Секции промпта (ВСЕГДА проверяй перед патчем!)
grep -A1 "═══" /opt/sofia-gpt/sofia_prompt_v2.py | grep -v "═══" | grep -v "^--$" | grep .

# Состояние клиента
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT * FROM client_state WHERE user_id = -(1000000 + CHAT_ID);"

# Диалог клиента
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT role, content FROM radist_messages WHERE chat_id = CHAT_ID ORDER BY timestamp;"
```

## Документация
- `docs/SOFIA_CONTEXT.md` — этот файл
- `docs/SOFIA_CURRENT.md` — текущий статус
- `docs/SOFIA_ARCHITECTURE.md` — детальная архитектура v3.0
- `docs/SOFIA_KNOWLEDGE.md` — база знаний
- `docs/SOFIA_TASKS.md` — задачи
- `docs/SESSION_END_TEMPLATE.md` — шаблон завершения сессии
