# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 09.03.2026

## ✅ Что сделано

### Сессия 09.03.2026 — Кэш Claude и session-end протокол
- SESSION_END_TEMPLATE.md — генерация ссылок через date +%Y%m%d_%H%M
- CLAUDE.md — восстановлен после reset --hard, добавлен в git
- Session-end протокол обновлён: обновление доков + свежие ссылки
- Кэш-проблема решена: ссылки теперь включают время, не только дату

### Сессия 08.03.2026 — Dev-окружение
- Dev-каталог /opt/sofia-gpt-dev/ — изолирован, порт 8081
- systemd сервис sofia-web-api-dev.service
- deploy.sh, Claude Code, SQLite MCP (.mcp.json)
- CLAUDE.md, KNOWLEDGE_INDEX.md, SESSION_GUIDE.md — созданы

## 🔄 Текущее состояние
- ✅ Web API, Telegram бот, Radist — работают
- ✅ Dev-окружение, Claude Code, SQLite MCP — настроены
- ✅ CLAUDE.md — в git, session-end актуален
- ⚠️ Bitrix НЕ подключён в bot_server.py и radist_gateway.py
- ⚠️ Observer ОТКЛЮЧЁН
- ⚠️ ASSIGNED_BY_ID = 426 (тест), нужно 24932 (прод)
- 📞 Михаил @das19875 (chat_id=39125360) — ждём ответ

## 🔜 Следующие шаги
1. **P1:** Retell AI — голосовой промпт (Шаг 1)
2. **P1:** Bitrix в bot_server.py и radist_gateway.py при [END]
3. **P2:** Рефакторинг core/ (Шаг 3)

## 📁 Последние изменения
- CLAUDE.md — восстановлен, добавлен в git
- docs/SESSION_END_TEMPLATE.md — генерация ссылок с date+%H%M
