# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 09.03.2026

## ✅ Что сделано

### Сессия 09.03.2026 — Документация
- SOFIA_CALLBACKS.md — создан (паттерны диалогов, возражения, голосовые адаптации Retell AI)
- SOFIA_KNOWLEDGE.md — расширен (кэш Claude &v=, dev-среда обязательна, iOS deep links)
- SOFIA_ARCHITECTURE.md — обновлён (dev-окружение, Claude Code, SQLite MCP, deploy.sh) + загружен в Project Knowledge
- SESSION_END_TEMPLATE.md — ссылки с &v=YYYYMMDD + запрет генерации блока до обновления доков
- SESSION_GUIDE.md — обновлён с инструкцией по &v=
- Кэш Claude побеждён: обход через параметр &v=YYYYMMDD в ссылках

### Сессия 08.03.2026 — Dev-окружение
- Dev-каталог /opt/sofia-gpt-dev/ — изолирован, порт 8081, sofia_gpt_dev.db
- deploy.sh — rsync dev→prod с исключениями, рестарт сервисов, health check
- Claude Code + SQLite MCP (.mcp.json) — настроены
- CLAUDE.md, KNOWLEDGE_INDEX.md, SESSION_GUIDE.md — переписаны

## 🔄 Текущее состояние
- ✅ Web API (sofia-web-api) — работает, Bitrix подключён
- ✅ Telegram бот (@humanAINeural_bot) — работает, source routing, 2 сообщения greeting
- ✅ Radist gateway (@SofiaOazis, +79181038493) — работает
- ✅ Dev-окружение /opt/sofia-gpt-dev/ — порт 8081, изолировано
- ✅ Claude Code + SQLite MCP — настроены
- ✅ Документация актуализирована (09.03)
- ⚠️ Observer ОТКЛЮЧЁН (OBSERVER_CHAT_ID закомментирован в .env)
- ⚠️ ASSIGNED_BY_ID = 426 (тест), нужно 24932 (прод)
- ⚠️ Bitrix НЕ подключён в bot_server.py и radist_gateway.py
- 📞 Активный диалог: Михаил @das19875 (chat_id=39125360) — ждём ответ

## 🔜 Следующие шаги
1. **P1:** Bitrix в bot_server.py и radist_gateway.py при [END]
2. **P1:** Observer: раскомментировать .env + добавить в bot_server.py
3. **P2:** Retell AI — голосовой промпт (Шаг 1)
4. **P2:** Рефакторинг core/ — единый generate_response() (Шаг 3)

## 📁 Последние изменения
- docs/SOFIA_CALLBACKS.md — создан
- docs/SOFIA_KNOWLEDGE.md — расширен
- docs/SOFIA_ARCHITECTURE.md — обновлён + Project Knowledge
- docs/SESSION_END_TEMPLATE.md — запрет генерации блока до обновления доков
- docs/SESSION_GUIDE.md — инструкция по &v=
