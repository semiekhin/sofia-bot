# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 21.03.2026

## Архитектурная карта: ПРОД vs DEV

### ПРОД (`/opt/sofia-gpt/`, порт 8080)
- `bot_server.py` — Telegram бот (@humanAINeural_bot) → `core/pipeline.py`
- `web_api.py` — веб виджет (порт 8080) → `core/pipeline.py` + `core/bitrix.py`
- `sofia_radist_gateway.py` — Radist gateway (порт 5001) → `core/pipeline.py`
- **`core/pipeline.py`** — единый пайплайн, задеплоен 21.03.2026
- **`core/bitrix.py`** — модуль Битрикс, подключён к web_api.py
- **Голосового канала НЕТ в проде** — `voice_api.py` только в dev (осознанное решение)
- Много мусора: 40+ `.backup_*` файлов, legacy файлы (planner.py, llm_planner.py, stage_detector.py, sofia_prompt.py)
- Файл-мусор: `ystemctl enable sofia-userbot` (опечатка при copy-paste)
- Бэкап до деплоя: `/opt/sofia-gpt-backup-20260321_1355` (НЕ УДАЛЯТЬ)

### DEV (`/opt/sofia-gpt-dev/`, порт 8081)
- Все 4 канала: `bot_server.py`, `web_api.py`, `sofia_radist_gateway.py`, `voice_api.py`
- **`core/pipeline.py`** — единый пайплайн, все 4 канала подключены через `run_pipeline()` / `stream_voice_response()`
- **`core/bitrix.py`** — модуль Битрикс
- Nginx `/llm-websocket/` → порт 8081 (Retell агент смотрит на dev)
- `stream_voice_response()` — закоммичен, async generator с asyncio.Queue bridge
- БД: `sofia_gpt_dev.db` — SOFIA_PATH починен, dev пишет в свою БД

### SOFIA_PATH — ПОЧИНЕН в DEV (21.03.2026)

Все 9 файлов с хардкодом `/opt/sofia-gpt` исправлены **в dev**. grep по dev чистый. Логи подтверждают: `Sofia path: /opt/sofia-gpt-dev`, `DB: sofia_gpt_dev.db`.

Исправленные файлы: web_api.py, sofia_userbot.py, sofia_userbot_pyrogram.py, test_smart_start.py, test_userbot.py, send_report.py, finance_calculator.py, add_actualization_examples.py, patch_bot_server.py.

**Прод — утилитные файлы:** sofia_userbot.py, sofia_userbot_pyrogram.py, test_smart_start.py, test_userbot.py, send_report.py, finance_calculator.py, add_actualization_examples.py, patch_bot_server.py — всё ещё содержат хардкод `/opt/sofia-gpt`. Это **корректно** для прода (путь совпадает). В прод деплоились только сервисные файлы (bot_server.py, web_api.py, sofia_radist_gateway.py, core/), утилиты не копировались.

## ✅ Что сделано

### Сессия 21.03.2026 — SOFIA_PATH fix + полный деплой dev→prod

**SOFIA_PATH — полное исправление:**
- Все 9 файлов с хардкодом `/opt/sofia-gpt` исправлены (было задокументировано 5, реально нашлось 9)
- grep чистый, логи подтверждают правильный путь

**Полный деплой dev → prod:**
- `core/` скопирован в прод (pipeline.py, bitrix.py, __init__.py)
- bot_server.py, web_api.py, sofia_radist_gateway.py — обновлены из dev
- Все 3 прод-сервиса перезапущены и работают на `core/pipeline.py`
- Скорость ответа: ~7с (было ~25с на старом коде)
- Бэкап: `/opt/sofia-gpt-backup-20260321_1355`

**core/bitrix.py создан и подключён:**
- Модуль создан в dev и задеплоен в прод
- Подключён к web_api.py (прод)
- Лид #261924 создан и обновлён через новый модуль
- Webhook, manager_active — всё работает

**voice_api.py НЕ деплоился** — остался только в dev (осознанное решение).

### Сессия 18.03.2026 — Битрикс интеграция + аудит Атлантиса

- Аудит трёх точек входа Атлантиса: /go/atlantis.html (статика Nginx → @SofiaOazis), веб-виджет (web_api.py по page_url), ?start=ATL (bot_server.py через source_objects.py)
- Реализована двусторонняя Битрикс-интеграция в ПРОД web_api.py: лид при первом сообщении, обновление COMMENTS при каждом сообщении, финализация при [END], перехват менеджером через manager_active + endpoint /api/bitrix/webhook
- Спроектирован ночной редирект через Тильду: поле "URL успеха" → /go/atlantis-redirect → по времени МСК (21:00-08:00 → виджет Софии, 08:00-21:00 → страница спасибо). Ждём URL от программиста Битрикса
- Замена OpenAI ключа во всех сервисах, исправлен load_dotenv(override=True) в bot_server.py и rag_module.py

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

## 🔄 Текущее состояние сервисов (проверено 21.03.2026)

| Сервис | Порт | Статус | Пайплайн |
|--------|------|--------|----------|
| sofia-gpt.service (Telegram bot prod) | — | running | core/pipeline.py |
| sofia-web-api.service (prod) | 8080 | running | core/pipeline.py + core/bitrix.py |
| sofia-radist.service (prod) | 5001 | running | core/pipeline.py |
| sofia-web-api-dev.service (dev) | 8081 | running | core/pipeline.py |
| sofia-radist-dev.service (dev) | 5002 | running | core/pipeline.py |

**Все 5 сервисов на `core/pipeline.py`.** Скорость ответа прод: ~7с (было ~25с).

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
1. **P1:** Подключить core/bitrix.py к bot_server.py (чтобы ?start=ATL лиды попадали в CRM)
2. **P1:** Подключить core/bitrix.py к radist_gateway.py
3. **P1:** Endpoint /go/atlantis-redirect с логикой времени МСК — ждём URL от Битрикс-программиста
4. **P1:** Тест gpt-4.1-mini для voice (потенциал ~200мс vs ~800мс первый токен)
5. **P1:** Post-stream проверка [END] в stream_voice_response()
6. **P1:** Прототип собственного голосового сервиса на Pipecat
7. **P2:** core/channel.py, core/observer.py
8. **P2:** Очистка мусора в проде (40+ backup файлов, legacy)
