# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 09.03.2026

## ✅ Что сделано

### Сессия 09.03.2026 — Кэш Claude и session-end протокол
- SESSION_END_TEMPLATE.md — добавлена генерация ссылок через `date +%Y%m%d_%H%M`
- CLAUDE.md — восстановлен после `reset --hard`, добавлен в git, session-end протокол со свежими ссылками
- Выявлено: CLAUDE.md не был в git → уязвим к `reset --hard`. Исправлено.
- Кэш-проблема решена: ссылки теперь включают время, не только дату

### Сессия 08.03.2026 — Dev-окружение
- Dev-каталог /opt/sofia-gpt-dev/ — изолирован, порт 8081, sofia_gpt_dev.db
- systemd сервис sofia-web-api-dev.service (порт 8081)
- deploy.sh — rsync dev→prod с исключениями, рестарт сервисов, health check
- Claude Code установлен и настроен
- SQLite MCP (.mcp.json) — прямой доступ к dev БД
- CLAUDE.md, KNOWLEDGE_INDEX.md, SESSION_GUIDE.md — созданы

### Сессия 07.03.2026 — Документация
- SOFIA_CALLBACKS.md — создан (паттерны диалогов, возражения, Retell AI)
- SOFIA_KNOWLEDGE.md — расширен (кэш &v=, dev-среда, iOS deep links)
- SOFIA_ARCHITECTURE.md — обновлён + загружен в Project Knowledge

## 🔄 Текущее состояние
- ✅ Web API (sofia-web-api) — работает, Bitrix подключён
- ✅ Telegram бот (@humanAINeural_bot) — работает, source routing
- ✅ Radist gateway (@SofiaOazis, +79181038493) — работает
- ✅ Dev-окружение /opt/sofia-gpt-dev/ — порт 8081, изолировано
- ✅ Claude Code + SQLite MCP — настроены
- ✅ CLAUDE.md — в git, session-end протокол актуален
- ⚠️ Observer ОТКЛЮЧЁН (OBSERVER_CHAT_ID закомментирован в .env)
- ⚠️ ASSIGNED_BY_ID = 426 (тест), нужно 24932 (прод)
- ⚠️ Bitrix НЕ подключён в bot_server.py и radist_gateway.py
- 📞 Активный диалог: Михаил @das19875 (chat_id=39125360) — ждём ответ

## 🔜 Следующие шаги
1. **P1:** Retell AI — голосовой промпт (Шаг 1)
2. **P1:** Bitrix в bot_server.py и radist_gateway.py при [END]
3. **P2:** Рефакторинг core/ — единый generate_response() (Шаг 3)
4. **P2:** Observer: раскомментировать .env + добавить в bot_server.py

## 📁 Последние изменения
- `CLAUDE.md` — восстановлен, добавлен в git
- `docs/SESSION_END_TEMPLATE.md` — генерация ссылок с date+%H%M
