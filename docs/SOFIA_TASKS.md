# Задачи Sofia-GPT

📅 Обновлено: 15.03.2026

## 🎙️ Шаг 1 — Голосовой агент (в процессе)

### Retell AI (текущая интеграция)
- [x] Создать voice_api.py — WebSocket адаптер
- [x] Маршрут в web_api.py
- [x] Nginx location /llm-websocket/
- [x] Агент в Retell Dashboard
- [x] Браузерный тест — Sofia отвечает
- [x] Оптимизация латенси: voice_mode в pipeline (~2с вместо 6-10с)
- [x] Стриминг: stream_voice_response + буферизация чанков (закоммичен)
- [ ] Русский голос (MiniMax или Cartesia в Retell)
- [ ] Тест gpt-4.1-mini для voice — P0 (первый токен ~200мс vs ~800мс)

### Собственный голосовой сервис (исследование)
- [x] Анализ альтернатив: Dasha.ai, Яндекс Realtime, Voicyfy — не подходят
- [x] Архитектура: Pipecat + Deepgram STT + ElevenLabs/Yandex TTS + наш pipeline
- [ ] Прототип на Pipecat (~200-300 строк Python) — P1
- [ ] Интеграция с Задарма (SIP)

### Voice общее
- [ ] Вернуть Extractor для voice (async в фоне — P0)
- [ ] Post-stream проверка [END] и обновление state — P0
- [ ] Голос в БД и Observer
- [ ] Починить SOFIA_PATH в 5 файлах dev (web_api.py, sofia_userbot.py, sofia_userbot_pyrogram.py, test_smart_start.py, test_userbot.py) — P0

## 🏗️ Шаг 2 — Безопасная среда ✅ ЗАВЕРШЁН

- [x] /opt/sofia-gpt-dev/
- [x] Отдельная БД
- [x] Systemd сервис (порт 8081)
- [x] CLAUDE.md
- [ ] deploy.sh (файл не существует — нужно создать)
- [x] Claude Code по SSH
- [x] SQLite MCP
- [x] KNOWLEDGE_INDEX.md
- [x] Хуки flake8 + black

## ⚙️ Шаг 3 — Единое ядро (в процессе)

- [x] core/pipeline.py — Analyzer → RAG → Generator
- [x] stream_voice_response() — стриминг для voice (закоммичен)
- [ ] core/channel.py
- [ ] core/bitrix.py
- [ ] core/observer.py
- [x] Переключить bot_server.py → run_pipeline()
- [x] Переключить web_api.py → run_pipeline()
- [x] Переключить radist_gateway.py → run_pipeline()
- [x] Удалить мёртвый импорт (radist)
- [ ] Atlantis context → config/source_objects.py (убрать hardcode из web_api.py)
- [ ] Деплой core/ в прод — P2

## 🔧 Dev-окружение Radist

- [x] sofia-radist-dev.service (порт 5002)
- [x] DEV_MODE — send disabled
- [x] Radist webhook зарегистрированы (Max + Telegram → :5002)
- [x] ufw порт 5002

## 🔥 Технический долг

- [ ] **SOFIA_PATH баг (5 файлов, было 9)** — хардкод `/opt/sofia-gpt` в dev: web_api.py (строки 26, 476), sofia_userbot.py, sofia_userbot_pyrogram.py, test_smart_start.py, test_userbot.py — **P0**. Уже исправлены: send_report.py, finance_calculator.py, add_actualization_examples.py, patch_bot_server.py
- [ ] Bitrix в bot_server.py (в проде web_api.py уже имеет полную интеграцию: create+update+webhook+manager_active)
- [ ] Bitrix в radist_gateway.py
- [ ] Bitrix веб-виджет crm.lead.update
- [ ] Унификация source_object: web виджет определяет atlantis по page_url, а не через config/source_objects.py как бот и radist
- [ ] Observer в .env
- [ ] Observer в bot_server.py
- [ ] ASSIGNED_BY_ID 426→24932
- [ ] ЦБ 16%→15.5%
- [ ] BUG-004 EN-раскладка
- [ ] Очистка мусора в проде (40+ backup файлов, legacy, файл `ystemctl enable sofia-userbot`)

## ⚡ Оптимизация

- [x] Стриминг Generator (voice — stream_voice_response)
- [ ] Стриминг Generator (текстовые каналы)
- [ ] Облегчить Analyzer
- [ ] 17-24с → <12с
- [ ] gpt-4.1-mini для voice (тест)

## 🤖 Будущее

- [ ] Pipecat — собственный голосовой сервис
- [ ] Cerebras GLM-4
- [ ] Агенты
- [ ] Новые объекты
- [ ] WABA
