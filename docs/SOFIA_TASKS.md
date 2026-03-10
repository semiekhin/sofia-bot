# Задачи Sofia-GPT

📅 Обновлено: 10.03.2026 (вечер)

## 🎙️ Шаг 1 — Голосовой агент Retell AI (в процессе)

- [x] Создать voice_api.py — WebSocket адаптер
- [x] Маршрут в web_api.py
- [x] Nginx location /llm-websocket/
- [x] Агент в Retell Dashboard
- [x] Браузерный тест — Sofia отвечает ✅
- [x] Оптимизация латенси: voice_mode в pipeline (~2с вместо 6-10с)
- [ ] Русский голос (MiniMax или Cartesia в Retell)
- [ ] Вернуть Extractor для voice (async в фоне или после оптимизации)
- [ ] Голос в БД и Observer
- [ ] Интеграция с Задарма (SIP)

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

## ⚙️ Шаг 3 — Единое ядро (в процессе)

- [x] core/pipeline.py — Analyzer → RAG → Generator
- [ ] core/channel.py
- [ ] core/bitrix.py
- [ ] core/observer.py
- [x] Переключить bot_server.py → run_pipeline()
- [x] Переключить web_api.py → run_pipeline()
- [x] Переключить radist_gateway.py → run_pipeline()
- [x] Удалить мёртвый импорт (radist)
- [ ] Atlantis context → config/source_objects.py (убрать hardcode из web_api.py)

## 🔧 Dev-окружение Radist

- [x] sofia-radist-dev.service (порт 5002)
- [x] DEV_MODE — send disabled
- [x] Radist webhook зарегистрированы (Max + Telegram → :5002)
- [x] ufw порт 5002

## 🔥 Технический долг

- [ ] Bitrix в bot_server.py
- [ ] Bitrix в radist_gateway.py
- [ ] Bitrix веб-виджет crm.lead.update
- [ ] Observer в .env
- [ ] Observer в bot_server.py
- [ ] ASSIGNED_BY_ID 426→24932
- [ ] ЦБ 16%→15.5%
- [ ] BUG-004 EN-раскладка

## ⚡ Оптимизация

- [ ] Стриминг Generator
- [ ] Облегчить Analyzer
- [ ] 17-24с → <12с

## 🤖 Будущее

- [ ] Cerebras GLM-4
- [ ] Агенты
- [ ] Новые объекты
- [ ] WABA
