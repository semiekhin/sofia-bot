# Sofia-GPT

AI-бот для продажи курортной недвижимости Oazis Estate. Квалифицирует лидов через Telegram и конвертирует в видео-консультации.

## Инфраструктура
- **Сервер:** 72.56.64.91:2222 (SSH)
- **Путь:** /opt/sofia-gpt/
- **Репозиторий:** GitHub (приватный)
- **Продакшен:** @humanAINeural_bot (Telegram)

## Стек
- Python 3 + python-telegram-bot
- SQLite (sofia_gpt.db)
- OpenAI API (gpt-5.2, Responses API)
- ChromaDB (RAG, 1095 примеров)

## Архитектура

```
Telegram → Extractor (gpt-5.2) → State Manager → Planner (код) → Generator (gpt-5.2) → Telegram
```

## Ключевые файлы
- `bot_server.py` — главный файл, обработка сообщений
- `extractor.py` — NLU, извлечение фактов
- `state_manager.py` — управление состоянием клиента
- `planner.py` — детерминированная логика выбора действий
- `sofia_prompt.py` — промпт генератора
- `rag_module.py` — векторный поиск примеров

## Команды
```bash
# Перезапуск
systemctl restart sofia-gpt

# Логи
tail -f /opt/sofia-gpt/sofia_bot.log

# Статус
systemctl status sofia-gpt
```

## Документация
- Архитектура: `docs/SOFIA_ARCHITECTURE.md`
- Знания: `docs/SOFIA_KNOWLEDGE.md`
- Задачи: `docs/SOFIA_TASKS.md`
