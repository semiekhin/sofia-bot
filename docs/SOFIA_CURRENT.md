# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 11.03.2026

## Архитектурная карта: ПРОД vs DEV

### ПРОД (`/opt/sofia-gpt/`, порт 8080)
- `bot_server.py` — Telegram бот (@humanAINeural_bot)
- `web_api.py` — веб виджет (порт 8080)
- `sofia_radist_gateway.py` — Radist gateway (порт 5001)
- **Голосового канала НЕТ** — `voice_api.py` и `core/` не существуют в проде
- Пайплайн дублирован внутри каждого транспорта (старый код)

### DEV (`/opt/sofia-gpt-dev/`, порт 8081)
- Те же три канала + `voice_api.py` (голосовой адаптер Retell)
- **`core/pipeline.py`** — единый пайплайн, все 4 канала подключены через `run_pipeline()` / `stream_voice_response()`
- Nginx `/llm-websocket/` → порт 8081 (Retell агент смотрит на dev)
- БД: `sofia_gpt_dev.db` (для bot_server, radist) + **ПРОД БД** для web_api/voice (баг!)

### Критический баг: web_api.py → ПРОД БД
`web_api.py:26` — `SOFIA_PATH = "/opt/sofia-gpt"` (захардкожен на прод). `voice_api.py` импортирует `save_message`/`get_history` из web_api — **голосовые сессии пишут историю в ПРОД базу**. Не исправлено.

## ✅ Что сделано

### Сессия 11.03.2026 — Аудит + исследование собственного голосового сервиса

**Аудит проекта:**
- Полный аудит состояния прод/дев по каждому каналу
- Подтверждён баг SOFIA_PATH в web_api.py (voice пишет в прод БД)
- Проверено: `core/` не существует в проде, все изменения с 09.03 — только в dev
- Зафиксировано: незакоммиченный стриминг (stream_voice_response + буферизация) в pipeline.py и voice_api.py

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

**Стриминг (незакоммичен, в diff):**
- `stream_voice_response()` в `core/pipeline.py` — Generator с `stream=True`, yield чанков через asyncio.Queue
- `voice_api.py` — буферизация чанков (flush по `.!?,` или 20+ символов + пробел), 2-8 чанков вместо 74 микро-чанков

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

## 🔄 Текущее состояние сервисов

| Сервис | Где | Статус |
|--------|-----|--------|
| Web API prod | :8080 | running, старый пайплайн |
| Telegram бот prod | long polling | running, старый пайплайн |
| Radist prod | :5001 | running, старый пайплайн |
| Web API dev | :8081 | running, core/pipeline.py |
| Radist dev | :5002 | running, core/pipeline.py, DEV_MODE |
| Voice (Retell) | :8081 ws | running через dev, stream_voice_response |

**Ключевое:** прод на старом коде (пайплайн дублирован в каждом транспорте), dev на `core/pipeline.py`. Деплой `core/` в прод ещё не выполнялся.

## 🔜 Следующие шаги
1. **P0:** Починить SOFIA_PATH в web_api.py (dev должен использовать dev БД)
2. **P0:** Закоммитить стриминг (stream_voice_response) — сейчас в uncommitted diff
3. **P0:** Тест gpt-4.1-mini для voice (потенциал ~200мс vs ~800мс первый токен)
4. **P1:** Прототип собственного голосового сервиса на Pipecat
5. **P1:** Bitrix в bot_server.py и radist_gateway.py при [END]
6. **P2:** Деплой core/pipeline.py в прод (все 3 канала)
7. **P2:** core/channel.py, core/bitrix.py, core/observer.py
