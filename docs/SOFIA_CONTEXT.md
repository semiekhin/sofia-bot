# Sofia-GPT v2.1

AI-бот для продажи курортной недвижимости Oazis Estate. Квалифицирует лидов через Telegram и конвертирует в видео-консультации.

## Инфраструктура
- **Сервер:** 72.56.64.91:2222 (SSH)
- **Путь:** /opt/sofia-gpt/
- **Бот:** @humanAINeural_bot
- **База:** sofia_gpt.db (SQLite)

## Стек
- Python 3 + python-telegram-bot
- OpenAI API (gpt-5.2, Responses API)
- ChromaDB (RAG, 1939 примеров)

## Архитектура v2.0
```
Telegram → Extractor (gpt-5.2) → State Manager → Planner v2.0 (код) → Generator (gpt-5.2) → Telegram
```

## Ключевые файлы
- `bot_server.py` — главный файл, обработка сообщений
- `extractor.py` — NLU, извлечение фактов из сообщений
- `state_manager.py` — состояние клиента (SQLite)
- `planner.py` — детерминированная логика выбора действий (v2.0: две ветки)
- `sofia_prompt.py` — промпт генератора
- `rag_module.py` — векторный поиск примеров

## Логика v2.0
- **Две ветки:** INVESTMENT и PERSONAL с разным порядком вопросов
- **Два созвона:** PROPOSE_MEETING_1 (после базовой) и PROPOSE_MEETING_2 (после полной квалификации)
- **Счётчик отказов:** При 2 отказах → FINISH_WITH_MATERIALS

## Команды
```bash
# Перезапуск
systemctl restart sofia-gpt

# Логи
tail -f /opt/sofia-gpt/sofia_bot.log

# Статус
systemctl status sofia-gpt

# Состояние клиента
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT * FROM client_state WHERE user_id = ID;"

# Feedback
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT * FROM feedback_v2 ORDER BY timestamp DESC LIMIT 10;"
```

## Документация
- `docs/SOFIA_CONTEXT.md` — этот файл
- `docs/SOFIA_CURRENT.md` — текущий статус
- `docs/SOFIA_ARCHITECTURE.md` — детальная архитектура v2.0
- `docs/SOFIA_KNOWLEDGE.md` — база знаний
- `docs/SOFIA_TASKS.md` — задачи
- `docs/SESSION_END_TEMPLATE.md` — шаблон завершения сессии
