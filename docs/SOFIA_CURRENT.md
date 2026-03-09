# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 09.03.2026 (вечер)

## ✅ Что сделано

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
- ufw порт 5002 открыт

**CLAUDE.md:**
- Правило подтверждений (1/2/3) — объяснять контекст и последствия
- Автоматический approve для безопасных команд (python3, curl, black, etc.)

### Сессия 09.03.2026 (утро) — Кэш Claude и session-end протокол
- SESSION_END_TEMPLATE.md — генерация ссылок через date +%Y%m%d_%H%M
- CLAUDE.md — восстановлен после reset --hard, добавлен в git
- Session-end протокол обновлён: обновление доков + свежие ссылки
- Кэш-проблема решена: ссылки теперь включают время, не только дату
- Модель работы финализирована

### Сессия 08.03.2026 — Dev-окружение
- Dev-каталог /opt/sofia-gpt-dev/ — изолирован, порт 8081
- systemd сервис sofia-web-api-dev.service
- deploy.sh, Claude Code, SQLite MCP (.mcp.json)

## 🔄 Текущее состояние
- ✅ Web API, Telegram бот, Radist — работают
- ✅ core/pipeline.py — все 3 канала используют единый пайплайн
- ✅ Dev Radist на порту 5002 (DEV_MODE, send disabled)
- ✅ Dev Web API на порту 8081
- ✅ Dev Bot (@SofiaDev01_bot) — проверен
- ⚠️ Bitrix НЕ подключён в bot_server.py и radist_gateway.py
- ⚠️ Observer ОТКЛЮЧЁН в dev
- ⚠️ ASSIGNED_BY_ID = 426 (тест), нужно 24932 (прод)
- ⚠️ web_api.py: Atlantis context hardcoded (нужно перенести в source_objects)

## 🔜 Следующие шаги
1. **P1:** Retell AI — голосовой промпт (Шаг 1)
2. **P1:** Bitrix в bot_server.py и radist_gateway.py при [END]
3. **P2:** core/channel.py, core/bitrix.py, core/observer.py (Шаг 3 продолжение)
4. **P2:** Atlantis context → config/source_objects.py (убрать hardcode из web_api.py)

## 📁 Ключевые файлы этой сессии
- `core/__init__.py` — новый
- `core/pipeline.py` — новый, единый пайплайн
- `bot_server.py` — generate_response_with_rag → run_pipeline()
- `web_api.py` — generate_response → run_pipeline()
- `sofia_radist_gateway.py` — generate_response → run_pipeline(), DEV_MODE guard
- `config/radist_config.py` — DEV_MODE, порт 5002
- `/etc/systemd/system/sofia-radist-dev.service` — новый сервис
