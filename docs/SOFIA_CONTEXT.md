# Sofia-GPT v3.0

AI-бот для продажи курортной недвижимости Oazis Estate. Квалифицирует лидов через Max и Telegram, конвертирует в видео-консультации.

## Инфраструктура
- **Сервер:** 72.56.64.91:2222 (SSH)
- **Путь:** /opt/sofia-gpt/
- **Бот:** @humanAINeural_bot
- **Сервис:** sofia-radist.service
- **База:** sofia_gpt.db (SQLite)

## Стек
- Python 3 + aiohttp (webhook сервер)
- OpenAI API (gpt-5.2, Responses API)
- ChromaDB (RAG, 2001 пример)
- Radist.Online (Max, Telegram, WhatsApp)

## Архитектура v3.0
```
Webhook → Extractor (gpt-5.2) → State → Analyzer (gpt-5.2) → RAG → Generator (gpt-5.2) → Ответ
```

Философия: доверяем LLM с полным контекстом (state_summary + RAG + промпт) вместо жёсткого Planner.

## Ключевые файлы
- `sofia_radist_gateway.py` — webhook сервер, Analyzer, RAG, Generator
- `message_processor.py` — Extractor → State → Signals
- `extractor.py` — NLU, извлечение фактов из сообщений
- `state_manager.py` — состояние клиента (SQLite)
- `sofia_prompt_v2.py` — промпт генератора
- `rag_module.py` — векторный поиск примеров (ChromaDB)
- `sofia_outreach.sh` — скрипт для outreach (cold/warm/hot)

## Быстрые команды
```bash
# Outreach тёплый
bash /opt/sofia-gpt/sofia_outreach.sh max 79XXXXXXXXX Имя

# Outreach холодный
bash /opt/sofia-gpt/sofia_outreach.sh max 79XXXXXXXXX "" cold

# Рестарт
systemctl restart sofia-radist

# Логи
tail -f /opt/sofia-gpt/sofia_radist.log

# Статус
systemctl status sofia-radist

# Состояние клиента
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT * FROM client_state WHERE user_id = -(1000000 + CHAT_ID);"

# Диалог клиента
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT role, content FROM radist_messages WHERE chat_id = CHAT_ID ORDER BY timestamp;"

# Остановить диалог
sqlite3 /opt/sofia-gpt/sofia_gpt.db "UPDATE client_state SET dialog_finished = 1 WHERE user_id = -(1000000 + (SELECT chat_id FROM radist_chats WHERE phone LIKE '%79XXXXXXXXX%'));"
```

## Документация
- `docs/SOFIA_CONTEXT.md` — этот файл
- `docs/SOFIA_CURRENT.md` — текущий статус
- `docs/SOFIA_ARCHITECTURE.md` — детальная архитектура v3.0
- `docs/SOFIA_KNOWLEDGE.md` — база знаний
- `docs/SOFIA_TASKS.md` — задачи
- `docs/SESSION_END_TEMPLATE.md` — шаблон завершения сессии
