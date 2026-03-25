# Задачи Sofia-GPT

📅 Обновлено: 25.03.2026

## 🚀 P0 — Ближайший деплой

- [ ] **Битрикс: ASSIGNED_BY_ID=428 (Sofia AI)** — при привязке к лиду ставить ответственным Sofia AI, при завершении диалога менять на стандартного. Предотвращает автораздачу лида менеджерам
- [ ] **Деплой bot_server.py в прод** — dev готов (коммит 4214a17b). Включает: Bitrix интеграция, таймауты, привязка к лиду Тильды (SOURCE_ID=397), prompt_addon Атлантис
- [ ] **Ссылка в Тильде** — URL успеха: `https://t.me/humanAINeural_bot?start=ATL`

## 🎙️ Голосовой агент

### Исследование ✅ ЗАВЕРШЕНО (25.03.2026)
- [x] Полное исследование: 8 направлений, 50+ решений → `docs/VOICE_RESEARCH_2026.md`
- [x] Целевой стек определён: Pipecat + Yandex SpeechKit + Groq/Qwen3 + gpt-4.1-mini + Задарма
- [x] End-to-end модели (OpenAI Realtime, Gemini Live) — не подходят для русского

### Вариант 1 — Быстрый (1-2 дня, ~2с, $0.08-0.15/мин)
- [ ] Заменить gpt-5.2 на gpt-4.1-mini в stream_voice_response() (0.7с TTFT, нет reasoning overhead)
- [ ] Voice-specific prompt: "1-2 предложения, заканчивай вопросом"
- [ ] Async Extractor после ответа (gpt-5.2, обновляет state в фоне)
- [ ] Post-stream проверка [END] и обновление state

### Вариант 2 — Целевая архитектура (2-3 недели, ~1-1.5с, $0.035/мин)
- [ ] Pipecat фреймворк: базовый голосовой бот
- [ ] Yandex SpeechKit STT (gRPC streaming, лучший русский)
- [ ] Yandex SpeechKit TTS (Premium voice, ~100ms TTFB)
- [ ] Groq + Qwen3-32B для Extractor (~0.3с TTFT)
- [ ] gpt-4.1-mini Generator (streaming)
- [ ] Параллельный запуск: Extractor + RAG + State одновременно
- [ ] Async state updates (БД, Bitrix, Observer — после начала стриминга)
- [ ] Задарма SIP телефония

### Вариант 3 — Максимальный (4-6 недель, ~0.5-1с, $0.07-0.10/мин)
- [ ] Предиктивный контекст: RAG pre-fetch по partial transcript
- [ ] Каскадная генерация: быстрая модель → первая фраза, полная → содержание
- [ ] Спекулятивное выполнение: pre-generate 2-3 вероятных ответа
- [ ] Кастомный голос "Софии" (Fish Audio S2 Pro voice clone)

### Retell AI (текущая интеграция, dev-only)
- [x] Создать voice_api.py — WebSocket адаптер
- [x] Маршрут в web_api.py
- [x] Nginx location /llm-websocket/
- [x] Агент в Retell Dashboard
- [x] Браузерный тест — Sofia отвечает
- [x] Оптимизация латенси: voice_mode в pipeline (~2с вместо 6-10с)
- [x] Стриминг: stream_voice_response + буферизация чанков (закоммичен)

### Voice общее
- [ ] Голос в БД и Observer
- [ ] WebRTC кнопка "голосовой звонок" в веб-виджете

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
- [x] core/bitrix.py — создан и подключён к web_api.py (прод) и bot_server.py (dev)
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
- [x] **Bitrix в bot_server.py — ГОТОВ в dev** (коммит 4214a17b). Лиды создаются, комменты стримятся, таймауты, привязка к Тильде. Ждёт деплоя.
- [ ] Bitrix в radist_gateway.py — подключить core/bitrix.py — **P1**
- [ ] Bitrix: ASSIGNED_BY_ID=428 (Sofia AI) — **P0**
- [ ] Унификация source_object: web виджет определяет atlantis по page_url, а не через config/source_objects.py как бот и radist
- [ ] Observer в .env
- [ ] Observer в bot_server.py
- [ ] BUG-004 EN-раскладка
- [ ] Очистка мусора в проде (40+ backup файлов, legacy, файл `ystemctl enable sofia-userbot`)

## ⚡ Оптимизация

- [x] Стриминг Generator (voice — stream_voice_response)
- [x] **Деплой core/pipeline.py в прод** — ответ ~7с (было ~25с)
- [ ] Стриминг Generator (текстовые каналы)
- [ ] Облегчить Analyzer
- [ ] gpt-4.1-mini для voice — Вариант 1 голосового агента

## 📄 Бизнес-документы (22.03.2026)

- [x] Манифест для команды
- [x] Дек для клиентов
- [x] Анализ рынка с конкурентами
- Позиционирование: четвёртый подход (LLM + RAG на реальных переписках) vs скриптовые боты / ChatGPT-обёртки / западный SaaS

## 🤖 Будущее

- [ ] Pipecat — собственный голосовой сервис (Вариант 2)
- [ ] Агенты
- [ ] Новые объекты
- [ ] WABA
