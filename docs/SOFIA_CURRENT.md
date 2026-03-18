# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 15.03.2026

## Архитектурная карта: ПРОД vs DEV

### ПРОД (`/opt/sofia-gpt/`, порт 8080)
- `bot_server.py` — Telegram бот (@humanAINeural_bot)
- `web_api.py` — веб виджет (порт 8080)
- `sofia_radist_gateway.py` — Radist gateway (порт 5001)
- **Голосового канала НЕТ** — `voice_api.py` и `core/` не существуют в проде
- Пайплайн дублирован внутри каждого транспорта (старый код)
- Много мусора: 40+ `.backup_*` файлов, legacy файлы (planner.py, llm_planner.py, stage_detector.py, sofia_prompt.py)
- Файл-мусор: `ystemctl enable sofia-userbot` (опечатка при copy-paste)

### DEV (`/opt/sofia-gpt-dev/`, порт 8081)
- Все 4 канала: `bot_server.py`, `web_api.py`, `sofia_radist_gateway.py`, `voice_api.py`
- **`core/pipeline.py`** — единый пайплайн, все 4 канала подключены через `run_pipeline()` / `stream_voice_response()`
- Nginx `/llm-websocket/` → порт 8081 (Retell агент смотрит на dev)
- `stream_voice_response()` — закоммичен, async generator с asyncio.Queue bridge
- БД: `sofia_gpt_dev.db` (для bot_server, radist) + **ПРОД БД** для web_api/voice (баг!)

### Критический баг: SOFIA_PATH хардкод → ПРОД (5 файлов, было 9)

Хардкод `/opt/sofia-gpt` в dev. Проверено 18.03.2026: 4 файла уже исправлены (send_report.py, finance_calculator.py, add_actualization_examples.py, patch_bot_server.py). Осталось 5:

| Файл | Мест | Риск |
|------|------|------|
| `web_api.py` (строки 26, 476) | 2 | **КРИТИЧЕСКИЙ** — активный сервис, пишет в прод БД, загружает прод .env |
| `sofia_userbot.py` (строка 20) | 1 | Средний |
| `sofia_userbot_pyrogram.py` (строка 21) | 1 | Средний |
| `test_smart_start.py` (строка 6) | 1 | Средний |
| `test_userbot.py` (строки 6, 15) | 2 | Средний |

Только **`voice_api.py`** делает правильно: `SOFIA_PATH = os.path.dirname(os.path.abspath(__file__))`

**Подтверждено логами:** `sofia-web-api-dev` сервис пишет `Sofia path: /opt/sofia-gpt`, `DB: /opt/sofia-gpt/sofia_gpt.db`.

## ✅ Что сделано

### Сессия 15.03.2026 — Полный аудит проекта

- Аудит структуры файлов прод/дев
- Аудит пайплайнов по каждому каналу (dev → core/pipeline.py, prod → старый)
- Выявлен масштаб SOFIA_PATH бага: 9 файлов, не 1 (к 18.03 осталось 5 — 4 уже исправлены)
- Подтверждено: стриминг закоммичен (ранее документировался как незакоммиченный)
- Проверка всех 5 systemd сервисов — все running
- Проверка .env: секретов в коде нет, все через os.getenv()
- Проверка логов: только транзиентная ошибка Telegram (Bad Gateway, авто-восстановление)
- Обновлена документация по результатам аудита

### Сессия 11.03.2026 — Аудит + исследование собственного голосового сервиса

**Аудит проекта:**
- Полный аудит состояния прод/дев по каждому каналу
- Подтверждён баг SOFIA_PATH в web_api.py (voice пишет в прод БД)
- Проверено: `core/` не существует в проде, все изменения с 09.03 — только в dev

**Исследование альтернатив Retell — собственный голосовой сервис:**
- Retell: единственная платформа с Custom LLM WebSocket, но $0.07-0.14/мин + сетевой хоп
- Dasha.ai: Custom LLM только через старую версию (Node.js SDK), архитектурно хуже
- Яндекс AI Studio Realtime: нет Custom LLM, их модель остаётся в цепочке
- Voicyfy: no-code поверх OpenAI/Google, нет кастомизации
- **Вывод: можно построить свой сервис через Pipecat (open-source Python)**
  - Архитектура: SIP (Задарма/Twilio) → Pipecat → Deepgram STT → наш pipeline → ElevenLabs/Yandex TTS
  - `stream_voice_response()` уже готов — отдаёт чанки
  - Стоимость: Deepgram ~$0.004/мин + ElevenLabs ~$0.01/мин + LLM = дешевле Retell
  - Прототип: ~200-300 строк Python

**Ещё не протестировано:** gpt-4.1-mini для voice (первый токен ~200мс vs ~800мс у gpt-5.2)

### Сессия 10.03.2026 (вечер) — Оптимизация латенси голосового канала

**Проблема:** голосовой ответ ~6-10с — некомфортно для живого разговора.

**Оптимизации в `voice_mode=True` (только голосовой канал):**
- Reasoning отключён для Analyzer и Generator (без `{"effort": "..."}`)
- Analyzer пропущен целиком — один LLM-вызов убран
- Extractor (process_message) пропущен — ещё один LLM-вызов убран
- RAG: 10→3 примера — меньше токенов в промпте
- Инструкция Generator: "максимум 2 предложения, без списков"

**Стриминг (закоммичен):**
- `stream_voice_response()` в `core/pipeline.py` — Generator с `stream=True`, yield чанков через asyncio.Queue
- `voice_api.py` — буферизация чанков (flush по `.!?,` или 20+ символов + пробел), 2-8 чанков вместо 74 микро-чанков
- Замечание: нет post-stream проверки `[END]` и обновления state

**Результат:** ответ ~2с вместо 6-10с. Стриминг даёт первый звук ещё раньше.

### Сессия 10.03.2026 (утро) — Голосовой агент Retell AI

- `voice_api.py` — WebSocket адаптер для Retell Custom LLM
- Nginx `location /llm-websocket/` → порт 8081
- Retell агент: `agent_d428a1d13067a563faf30a88bb`
- Голос: Nastya (ElevenLabs `YjESejviApN7SHrbfnA2`), ru-RU, eleven_v3

### Сессия 09.03.2026 — core/pipeline.py + dev radist

- `core/pipeline.py` — единый пайплайн Analyzer → RAG → Generator
- Переключены все 3 канала: bot_server.py, web_api.py, sofia_radist_gateway.py
- Dev-окружение Radist: порт 5002, DEV_MODE, webhooks

## 🔄 Текущее состояние сервисов (проверено 15.03.2026)

| Сервис | Порт | Статус | Uptime | Пайплайн |
|--------|------|--------|--------|----------|
| sofia-gpt.service (Telegram bot prod) | — | running | ~2 дня | старый |
| sofia-web-api.service (prod) | 8080 | running | ~2 дня | старый |
| sofia-radist.service (prod) | 5001 | running | ~2 дня | старый |
| sofia-web-api-dev.service (dev) | 8081 | running | ~2 дня | core/pipeline.py |
| sofia-radist-dev.service (dev) | 5002 | running | ~6 дней | core/pipeline.py |

**Ключевое:** прод на старом коде (пайплайн дублирован в каждом транспорте), dev на `core/pipeline.py`. Деплой `core/` в прод ещё не выполнялся.

## .env: dev vs prod (проверено 15.03.2026)

| Ключ | Dev | Prod |
|------|-----|------|
| OPENAI_API_KEY | + | + |
| TELEGRAM_BOT_TOKEN | + | + |
| ADMIN_CHAT_ID | + | + |
| MODEL_MODE | + | + |
| USE_LLM_PLANNER | + | + |
| SOFIA_PATH | + | — |
| DB_PATH | + | — |
| WEB_API_PORT | + | — |
| RADIST_DEV_MODE | + | — |

Секретов в коде нет — все через `os.getenv()`.

## 🔜 Следующие шаги
1. **P0:** Починить SOFIA_PATH в оставшихся 5 файлах dev (критический — dev пишет в прод БД)
2. **P0:** Тест gpt-4.1-mini для voice (потенциал ~200мс vs ~800мс первый токен)
3. **P0:** Post-stream проверка [END] в stream_voice_response()
4. **P1:** Прототип собственного голосового сервиса на Pipecat
5. **P1:** Bitrix в bot_server.py и radist_gateway.py при [END]
6. **P2:** Деплой core/pipeline.py в прод (все 3 канала)
7. **P2:** core/channel.py, core/bitrix.py, core/observer.py
8. **P2:** Очистка мусора в проде (40+ backup файлов, legacy)
