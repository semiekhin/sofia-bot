# Задачи Sofia-GPT

📅 Обновлено: 21.03.2026

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
- [ ] Тест gpt-4.1-mini для voice — P1 (первый токен ~200мс vs ~800мс)

### Собственный голосовой сервис (исследование)
- [x] Анализ альтернатив: Dasha.ai, Яндекс Realtime, Voicyfy — не подходят
- [x] Архитектура: Pipecat + Deepgram STT + ElevenLabs/Yandex TTS + наш pipeline
- [ ] Прототип на Pipecat (~200-300 строк Python) — P1
- [ ] Интеграция с Задарма (SIP)

### Voice общее
- [ ] Вернуть Extractor для voice (async в фоне)
- [ ] Post-stream проверка [END] и обновление state — P1
- [ ] Голос в БД и Observer

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

## ⚙️ Шаг 3 — Единое ядро ✅ ЗАДЕПЛОЕНО В ПРОД (21.03.2026)

- [x] core/pipeline.py — Analyzer → RAG → Generator
- [x] stream_voice_response() — стриминг для voice (закоммичен)
- [ ] core/channel.py
- [x] core/bitrix.py — создан и подключён к web_api.py (прод)
- [ ] core/observer.py
- [x] Переключить bot_server.py → run_pipeline()
- [x] Переключить web_api.py → run_pipeline()
- [x] Переключить radist_gateway.py → run_pipeline()
- [x] Удалить мёртвый импорт (radist)
- [ ] Atlantis context → config/source_objects.py (убрать hardcode из web_api.py)
- [x] **Деплой core/ в прод — ВЫПОЛНЕН 21.03.2026** (pipeline.py, bitrix.py, __init__.py)

## 🔧 Dev-окружение Radist

- [x] sofia-radist-dev.service (порт 5002)
- [x] DEV_MODE — send disabled
- [x] Radist webhook зарегистрированы (Max + Telegram → :5002)
- [x] ufw порт 5002

## 🔥 Технический долг

- [x] **SOFIA_PATH баг — ПОЧИНЕН 21.03.2026.** Все 9 файлов исправлены. grep чистый, логи подтверждают.
- [ ] Bitrix в bot_server.py — подключить core/bitrix.py (чтобы ?start=ATL лиды попадали в CRM) — **P1**
- [ ] Bitrix в radist_gateway.py — подключить core/bitrix.py — **P1**
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
- [x] **Деплой core/pipeline.py в прод** — ответ ~7с (было ~25с)
- [ ] Стриминг Generator (текстовые каналы)
- [ ] Облегчить Analyzer
- [ ] gpt-4.1-mini для voice (тест)

## 🤖 Будущее

- [ ] Pipecat — собственный голосовой сервис
- [ ] Cerebras GLM-4
- [ ] Агенты
- [ ] Новые объекты
- [ ] WABA
