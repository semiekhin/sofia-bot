# Задачи Sofia-GPT

📅 Обновлено: 09.03.2026

## 🎙️ Шаг 1 — Тест голоса

- [ ] Написать промпт под Retell AI
- [ ] Настройка агента в Retell
- [ ] Протестировать

## 🏗️ Шаг 2 — Безопасная среда ✅ ЗАВЕРШЁН

- [x] /opt/sofia-gpt-dev/
- [x] Отдельная БД
- [x] Systemd сервис (порт 8081)
- [x] CLAUDE.md
- [x] deploy.sh
- [x] Claude Code по SSH
- [x] SQLite MCP
- [x] KNOWLEDGE_INDEX.md
- [x] Хуки flake8 + black

## ⚙️ Шаг 3 — Единое ядро

- [ ] core/pipeline.py
- [ ] core/channel.py
- [ ] core/bitrix.py
- [ ] core/observer.py
- [ ] Переключить web_api.py
- [ ] Переключить bot_server.py
- [ ] Переключить radist_gateway.py
- [ ] Удалить мёртвый импорт
- [ ] history limit 8→100

## 🔥 Технический долг

- [ ] Bitrix в bot_server.py
- [ ] Bitrix в radist_gateway.py
- [ ] Bitrix веб-виджет crm.lead.update
- [ ] Observer в .env
- [ ] Observer в bot_server.py
- [ ] ASSIGNED_BY_ID 426→24932
- [ ] ЦБ 16%→15.5%
- [ ] BUG-004 EN-раскладка

## 📈 Шаг 4 — Голос как канал

- [ ] channels/voice.py
- [ ] Retell + Задарма
- [ ] n8n оркестратор
- [ ] Голос в БД и Observer

## ⚡ Оптимизация

- [ ] Стриминг Generator
- [ ] Облегчить Analyzer
- [ ] 17-24с → <12с

## 🤖 Будущее

- [ ] Cerebras GLM-4
- [ ] Агенты
- [ ] Новые объекты
- [ ] WABA
