# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 26.03.2026

## Архитектурная карта: ПРОД vs DEV

### ПРОД (`/opt/sofia-gpt/`, порт 8080)
- `bot_server.py` — Telegram бот (@humanAINeural_bot) → `core/pipeline.py` + `core/bitrix.py` (**задеплоен 26.03.2026**)
- `web_api.py` — веб виджет (порт 8080) → `core/pipeline.py` + `core/bitrix.py` (**задеплоен 26.03.2026**)
- `sofia_radist_gateway.py` — Radist gateway (порт 5001) → `core/pipeline.py` (**без Bitrix**)
- **`core/pipeline.py`** — единый пайплайн, задеплоен 21.03.2026
- **`core/bitrix.py`** — модуль Битрикс с ASSIGNED_BY_ID=428, задеплоен 26.03.2026
- **Голосового канала НЕТ в проде** — voice только в dev
- Бэкапы: `/opt/sofia-gpt-backup-20260321_1355`, `/opt/sofia-gpt/backups/20260326_0724/`

### DEV (`/opt/sofia-gpt-dev/`, порт 8081)
- Все каналы: `bot_server.py`, `web_api.py`, `sofia_radist_gateway.py`, `voice_api.py`
- **`core/pipeline.py`** — единый пайплайн + voice Вариант 1 (gpt-4.1-mini, async Extractor)
- **`core/bitrix.py`** — модуль Битрикс с ASSIGNED_BY_ID=428, lead_assigned таблица, restore_assigned()
- **bot_server.py** — Битрикс только для source-сессий (ATL), задеплоен в прод 26.03.2026
- **voice_api.py** — Retell AI WebSocket адаптер (Вариант 1)
- **voice_pipecat.py** — Pipecat + SmallWebRTC (НЕ РАБОТАЕТ — NAT блокирует ICE)
- **voice_pipecat_daily.py** — Pipecat + Daily WebRTC (В ПРОЦЕССЕ — pipeline работает, TTS задержка)
- Nginx: `/voice-v2/` → порт 8082, `/start` и `/sessions/` → порт 8082
- Coturn TURN сервер на порту 3478 (для SmallWebRTC, не помог)
- БД: `sofia_gpt_dev.db`

## ✅ Что сделано

### Сессия 26.03.2026 — Деплой P0 + Voice Вариант 1 + Pipecat V2

**P0 — ASSIGNED_BY_ID=428 (Sofia AI):**
- `SOFIA_AI_USER_ID = 428` — константа в core/bitrix.py
- `create_lead()` ставит ASSIGNED_BY_ID=428 при создании лида
- `find_recent_atlantis_lead()` возвращает dict с assigned_by_id, сохраняет original
- `restore_assigned()` возвращает ответственного при завершении (original → fallback 426)
- Таблица `lead_assigned`: lead_id → original_assigned_by_id (auto-migrate)
- 4 сценария завершения покрыты: meeting_agreed, двойной отказ, таймаут, перехват менеджером
- Webhook: проверяет ASSIGNED_BY_ID, игнорирует собственные обновления (428)
- Тест: лид #262784 → ASSIGNED_BY_ID=428 во время диалога → 426 после [END]

**P0 — Битрикс только для source-сессий:**
- `_is_bitrix_session()` проверяет source_object в client_state
- Обычный `/start` без параметра → без Битрикс API
- `/start ATL` → полная Битрикс интеграция

**P0 — Деплой в прод (26.03.2026):**
- Бэкап: `/opt/sofia-gpt/backups/20260326_0724/`
- Задеплоены: core/bitrix.py, bot_server.py, web_api.py
- Все 3 прод-сервиса перезапущены, ошибок нет
- E2E тест: лид #262794 → ASSIGNED_BY_ID=428 (прод веб-виджет)

**Voice Вариант 1 — оптимизация stream_voice_response():**
- Модель: gpt-5.2 → gpt-4.1-mini (~0.7с TTFT)
- RAG: 3 → 10 примеров (ChromaDB ~50ms)
- Промпт: развёрнутый VOICE_PROMPT_ADDON (7 правил, без "всегда заканчивай вопросом")
- max_output_tokens: 4000 → 800
- Async Extractor: extract_sync + merge после стрима (asyncio.create_task), не сбрасывает dialog_finished
- [END] проверка: post-stream по полному тексту

**Voice Вариант 2 — Pipecat бот (dev, В ПРОЦЕССЕ):**
- `voice_pipecat.py` — SmallWebRTC + OpenAI STT + gpt-4.1-mini + ElevenLabs TTS
  - SmallWebRTC НЕ РАБОТАЕТ из-за NAT (ICE checking → timeout)
  - Coturn TURN сервер установлен, не помог
- `voice_pipecat_daily.py` — Daily WebRTC транспорт
  - Pipeline работает: STT распознаёт, LLM генерирует, TTS озвучивает
  - **Блокер:** ElevenLabs TTS TTFB 5-13с → клиент не слышит ответ вовремя
  - Голос: Victoria (FZGeNF7bE3syeQOynDKC), eleven_multilingual_v2
  - Daily домен: sofia-oazis.daily.co

### Сессия 25.03.2026 — Исследование голосового агента

**Полное исследование голосового стека** (`docs/VOICE_RESEARCH_2026.md`):
- Проанализированы 8 направлений: STT (9 решений), TTS (10 решений), LLM (11 провайдеров), оркестрация (7 фреймворков), телефония (7 провайдеров), end-to-end модели (6), архитектурные паттерны (7), российская специфика
- **Целевой стек:** Pipecat + Yandex SpeechKit (STT+TTS) + Groq/Qwen3-32B (Extractor) + gpt-4.1-mini (Generator) + Задарма (телефония)

### Сессия 22.03.2026 — Битрикс в bot_server.py + таймауты + Тильда

- core/bitrix.py подключён к bot_server.py
- Таймауты: сценарий А (15 мин) и Б (60 мин + 15 мин)
- Привязка к лиду Тильды (SOURCE_ID=397)
- Битрикс: сотрудник Sofia AI (User ID 428)

### Сессия 21.03.2026 — SOFIA_PATH fix + полный деплой dev→prod

- Все 9 файлов исправлены, деплой core/ в прод, ответ ~7с

## 🔄 Текущее состояние сервисов (проверено 26.03.2026)

| Сервис | Порт | Статус | Пайплайн |
|--------|------|--------|----------|
| sofia-gpt.service (Telegram bot prod) | — | running | core/pipeline.py + core/bitrix.py (ATL only) |
| sofia-web-api.service (prod) | 8080 | running | core/pipeline.py + core/bitrix.py |
| sofia-radist.service (prod) | 5001 | running | core/pipeline.py |
| sofia-web-api-dev.service (dev) | 8081 | running | core/pipeline.py |
| sofia-radist-dev.service (dev) | 5002 | running | core/pipeline.py |
| voice_pipecat_daily.py (dev) | 8083 | running (manual) | Pipecat + Daily WebRTC |

## .env: dev (обновлено 26.03.2026)

| Ключ | Dev | Prod |
|------|-----|------|
| OPENAI_API_KEY | + | + |
| TELEGRAM_BOT_TOKEN | + | + |
| ELEVENLABS_API_KEY | + | — |
| YANDEX_SPEECHKIT_API_KEY | + | — |
| GROQ_API_KEY | + | — |
| DAILY_API_KEY | + | — |

## 🔜 Следующие шаги

### P0 — срочно
1. **Ссылка в Тильде** — URL успеха: `https://t.me/humanAINeural_bot?start=ATL`
2. **Voice V2: починить TTS латенси** — ElevenLabs TTFB 5-13с, нужно отладить или сменить на Yandex TTS

### P1 — следующая итерация
3. Подключить core/bitrix.py к radist_gateway.py
4. Voice V2: подключить наш pipeline (core/pipeline.py) к Pipecat
5. Voice V2: Yandex SpeechKit STT (кастомный Pipecat процессор)
6. deploy.sh скрипт

### P2 — голосовой агент (целевая архитектура)
7. Yandex SpeechKit TTS (вместо ElevenLabs)
8. Задарма SIP телефония
9. WebRTC кнопка "голосовой звонок" в веб-виджете

### P3 — техдолг
10. Очистка мусора в проде (40+ backup файлов, legacy)
11. core/channel.py, core/observer.py
12. Atlantis context → config/source_objects.py
13. BUG-004 EN-раскладка
