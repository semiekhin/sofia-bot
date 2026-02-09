# Sofia-GPT v3.0

AI-бот для продажи курортной недвижимости Oazis Estate. Квалифицирует лидов через мессенджеры и сайт, конвертирует в видео-консультации.

## Инфраструктура
- **Сервер:** 72.56.64.91:2222 (SSH)
- **Путь:** /opt/sofia-gpt/
- **Бот:** @humanAINeural_bot
- **Сервисы:**
  - sofia-radist.service (порт 5001) — Radist gateway
  - sofia-web-api.service (порт 8080) — Web API для виджета
- **API:** https://api.atlantis-invest.ru
- **Сайт:** https://atlantis-invest.ru (reg.ru хостинг)
- **База:** sofia_gpt.db (SQLite)

## Каналы (на 10.02.2026)
- **Telegram:** ✅ входящие работают (@humanAINeural_bot)
- **Виджет на сайте:** ✅ работает (atlantis-invest.ru → api.atlantis-invest.ru)
- **Max:** ❌ ЗАБАНЕН
- **WABA:** ⏳ не подключен

## Стек
- Python 3 + aiohttp (Radist webhook, порт 5001)
- Python 3 + FastAPI/uvicorn (Web API, порт 8080)
- OpenAI API (gpt-5.2, Responses API)
- ChromaDB (RAG, 2001 пример)
- Nginx + Let's Encrypt (SSL для api.atlantis-invest.ru)

## Архитектура v3.0
```
[Каналы]                              [Сервер 72.56.64.91]
                                      
Telegram Bot ─────────────┐
                          ├──→ process_message() → Analyzer → RAG → Generator → Ответ
Radist Webhook (Max) ─────┤
                          │
Web Widget (сайт) ── nginx/SSL ──→ web_api.py (:8080) ─┘
```

Философия: доверяем LLM с полным контекстом (state_summary + RAG + промпт) вместо жёсткого Planner.

## Ключевые файлы
- `web_api.py` — FastAPI сервер для виджета (порт 8080)
- `sofia_radist_gateway.py` — Radist webhook сервер (порт 5001)
- `message_processor.py` — Extractor → State → Signals
- `extractor.py` — NLU, извлечение фактов
- `state_manager.py` — состояние клиента (SQLite)
- `sofia_prompt_v2.py` — промпт генератора
- `rag_module.py` — векторный поиск примеров (ChromaDB)

## Быстрые команды
```bash
# Web API
systemctl status sofia-web-api
systemctl restart sofia-web-api
tail -f /opt/sofia-gpt/web_api.log
curl -s https://api.atlantis-invest.ru/api/health

# Radist gateway
systemctl restart sofia-radist
tail -f /opt/sofia-gpt/sofia_radist.log

# Nginx
systemctl status nginx
cat /etc/nginx/sites-available/sofia-api

# Состояние веб-клиента
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT * FROM client_state WHERE user_id >= 9000000;"
```

## Документация
- `docs/SOFIA_CONTEXT.md` — этот файл
- `docs/SOFIA_CURRENT.md` — текущий статус
- `docs/SOFIA_ARCHITECTURE.md` — детальная архитектура v3.0
- `docs/SOFIA_KNOWLEDGE.md` — база знаний
- `docs/SOFIA_TASKS.md` — задачи
- `docs/SESSION_END_TEMPLATE.md` — шаблон завершения сессии
