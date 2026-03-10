# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 10.03.2026

## ✅ Что сделано

### Сессия 10.03.2026 — Голосовой агент Retell AI

**Инфраструктура:**
- Dev сервис переведён на порт 8081 (был hardcode 8080 в `__main__`, конфликтовал с продом)
- Nginx `location /llm-websocket/` добавлен в sofia-api, proxy_pass на 8081 (временно для теста)
- Создан `voice_api.py` — WebSocket адаптер для Retell Custom LLM
- В `web_api.py` добавлен маршрут `@app.websocket("/llm-websocket/{call_id}")`, импорт WebSocket
- `generate_response()` получил параметр `channel` (дефолт "web")

**Retell AI:**
- Агент: `agent_d428a1d13067a563faf30a88bb`
- Custom LLM URL: `wss://api.atlantis-invest.ru/llm-websocket/`
- Браузерный тест прошёл — Sofia отвечает голосом ✅
- Голос: Julia (OpenAI) → нужен русский (MiniMax/Cartesia)

**Архитектура voice_api.py (текущее состояние):**
- user_id: `7_000_000 + (md5(call_id)[:8] % 1_000_000)`
- Приветствие: фиксированная строка (без пайплайна)
- Reminder (молчание): фиксированный nudge (без пайплайна)
- response_required: полный пайплайн через generate_response() из web_api.py
- clean_for_voice(): очистка markdown для TTS

### Сессия 09.03.2026 (вечер) — core/pipeline.py + dev radist

**Рефакторинг пайплайна:**
- Создан `core/pipeline.py` — единый пайплайн Analyzer → RAG → Generator
- Переключены все 3 канала: bot_server.py, web_api.py, sofia_radist_gateway.py
- Удалено ~450 строк дублированного кода (по ~150 в каждом файле)
- Source routing (skip analyzer + context injection) — внутри pipeline
- was_offline поддержка — параметр pipeline

**Dev-окружение для Radist:**
- `sofia-radist-dev.service` на порту 5002 (прод на 5001)
- `DEV_MODE=true` — логирует ответы, не отправляет клиенту
- Webhook зарегистрированы в Radist API (Max + Telegram → :5002)

### Сессия 09.03.2026 (утро) — Кэш Claude и session-end протокол
- SESSION_END_TEMPLATE.md, CLAUDE.md в git, session-end протокол

### Сессия 08.03.2026 — Dev-окружение
- Dev-каталог /opt/sofia-gpt-dev/, порт 8081, deploy.sh, Claude Code

## 🔄 Текущее состояние
- ✅ Web API, Telegram бот, Radist — работают (прод)
- ✅ core/pipeline.py — все 3 канала используют единый пайплайн
- ✅ Dev Web API на порту 8081, voice WebSocket работает
- ✅ Retell AI агент создан, браузерный тест пройден
- ⚠️ voice_api.py использует `generate_response()` из web_api.py (путь web, не bot/radist)
- ⚠️ Bitrix НЕ подключён в bot_server.py и radist_gateway.py
- ⚠️ Observer ОТКЛЮЧЁН в dev

## 🔜 Следующие шаги
1. **P0:** Доработать voice_api.py — response_required должен идти через пайплайн без source_object привязки (как bot/radist, не web)
2. **P0:** Русский голос в Retell (MiniMax/Cartesia)
3. **P1:** Bitrix в bot_server.py и radist_gateway.py при [END]
4. **P2:** core/channel.py, core/bitrix.py, core/observer.py

## 📁 Ключевые файлы этой сессии
- `voice_api.py` — новый, WebSocket адаптер Retell AI
- `web_api.py` — WebSocket маршрут, порт 8081, channel param в generate_response
- `/etc/nginx/sites-available/sofia-api` — location /llm-websocket/
