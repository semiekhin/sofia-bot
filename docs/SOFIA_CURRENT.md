# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 25.03.2026

## Архитектурная карта: ПРОД vs DEV

### ПРОД (`/opt/sofia-gpt/`, порт 8080)
- `bot_server.py` — Telegram бот (@humanAINeural_bot) → `core/pipeline.py` (**без Bitrix — деплой ожидается**)
- `web_api.py` — веб виджет (порт 8080) → `core/pipeline.py` + `core/bitrix.py`
- `sofia_radist_gateway.py` — Radist gateway (порт 5001) → `core/pipeline.py` (**без Bitrix**)
- **`core/pipeline.py`** — единый пайплайн, задеплоен 21.03.2026
- **`core/bitrix.py`** — модуль Битрикс, подключён только к web_api.py
- **Голосового канала НЕТ в проде** — `voice_api.py` только в dev (осознанное решение)
- Много мусора: 40+ `.backup_*` файлов, legacy файлы (planner.py, llm_planner.py, stage_detector.py, sofia_prompt.py)
- Файл-мусор: `ystemctl enable sofia-userbot` (опечатка при copy-paste)
- Бэкап до деплоя: `/opt/sofia-gpt-backup-20260321_1355` (НЕ УДАЛЯТЬ)

### DEV (`/opt/sofia-gpt-dev/`, порт 8081)
- Все 4 канала: `bot_server.py`, `web_api.py`, `sofia_radist_gateway.py`, `voice_api.py`
- **`core/pipeline.py`** — единый пайплайн, все 4 канала подключены через `run_pipeline()` / `stream_voice_response()`
- **`core/bitrix.py`** — модуль Битрикс, подключён к web_api.py и bot_server.py
- **bot_server.py** — Bitrix интеграция ГОТОВА (коммит 4214a17b), ждёт деплоя в прод
- Nginx `/llm-websocket/` → порт 8081 (Retell агент смотрит на dev)
- `stream_voice_response()` — закоммичен, async generator с asyncio.Queue bridge
- БД: `sofia_gpt_dev.db` — SOFIA_PATH починен, dev пишет в свою БД

### SOFIA_PATH — ПОЧИНЕН в DEV (21.03.2026)

Все 9 файлов с хардкодом `/opt/sofia-gpt` исправлены **в dev**. grep по dev чистый. Логи подтверждают: `Sofia path: /opt/sofia-gpt-dev`, `DB: sofia_gpt_dev.db`.

Исправленные файлы: web_api.py, sofia_userbot.py, sofia_userbot_pyrogram.py, test_smart_start.py, test_userbot.py, send_report.py, finance_calculator.py, add_actualization_examples.py, patch_bot_server.py.

**Прод — утилитные файлы:** sofia_userbot.py, sofia_userbot_pyrogram.py, test_smart_start.py, test_userbot.py, send_report.py, finance_calculator.py, add_actualization_examples.py, patch_bot_server.py — всё ещё содержат хардкод `/opt/sofia-gpt`. Это **корректно** для прода (путь совпадает). В прод деплоились только сервисные файлы (bot_server.py, web_api.py, sofia_radist_gateway.py, core/), утилиты не копировались.

## ✅ Что сделано

### Сессия 25.03.2026 — Исследование голосового агента

**Полное исследование голосового стека** (`docs/VOICE_RESEARCH_2026.md`):
- Проанализированы 8 направлений: STT (9 решений), TTS (10 решений), LLM (11 провайдеров), оркестрация (7 фреймворков), телефония (7 провайдеров), end-to-end модели (6), архитектурные паттерны (7), российская специфика
- **Вывод:** end-to-end модели (OpenAI Realtime, Gemini Live) НЕ подходят для русского sales-агента
- **Целевой стек:** Pipecat + Yandex SpeechKit (STT+TTS) + Groq/Qwen3-32B (Extractor) + gpt-4.1-mini (Generator) + Задарма (телефония)
- **Три варианта архитектуры:**
  - Быстрый (1-2 дня): gpt-4.1-mini в Retell + async Extractor → ~2с, $0.08-0.15/мин
  - Средний (2-3 нед): Pipecat + Yandex STT/TTS + Groq → ~1-1.5с, $0.035/мин (ЦЕЛЕВОЙ)
  - Максимальный (4-6 нед): + каскад + pre-fetch + кастом голос → ~0.5-1с

### Сессия 22.03.2026 — Битрикс в bot_server.py + таймауты + Тильда

**Битрикс в bot_server.py (DEV READY):**
- core/bitrix.py подключён к bot_server.py: лиды создаются, комменты стримятся, перехват менеджером работает
- Тест с реальными диалогами — лид в Битрикс с полным досье
- Коммит: 4214a17b (dev), НЕ задеплоен в прод

**Таймауты:**
- Сценарий А: нет ответа 15 мин → финализация
- Сценарий Б: 60 мин + напоминание + 15 мин → финализация

**Атлантис — доработки:**
- Не спрашивает контакт (форма Тильды уже содержит имя/телефон/email)
- Привязка к лиду Тильды: ищет последний лид с SOURCE_ID=397, привязывается к нему вместо создания нового

**Решения по архитектуре:**
- Тильда → всегда (24/7) редирект на Telegram бот ?start=ATL, без страницы "спасибо"
- Endpoint /go/atlantis-redirect — ОТМЕНЁН, не нужен

**Битрикс: сотрудник Sofia AI (User ID 428):**
- ID получен от программиста Битрикс
- Нужно: при привязке к лиду ставить ASSIGNED_BY_ID=428 (Sofia AI), при завершении менять обратно на стандартного
- Предотвращает автораздачу лида менеджерам до окончания квалификации

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

### Сессия 10.03.2026 (вечер) — Оптимизация латенси голосового канала

- voice_mode: отключены Extractor, Analyzer, reasoning, RAG 10→3
- Стриминг: stream_voice_response() + буферизация чанков (2-8 вместо 74)
- Результат: ответ ~2с вместо 6-10с

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

### P0 — ближайший деплой
1. **Битрикс: ASSIGNED_BY_ID=428 (Sofia AI)** — при привязке к лиду ставить Sofia AI ответственным, при завершении менять обратно. Предотвращает автораздачу лида менеджерам до окончания квалификации
2. **Деплой bot_server.py в прод** — dev готов (коммит 4214a17b), стандартная процедура: бэкап → копия → рестарт → проверка
3. **Ссылка в Тильде** — после деплоя поставить URL успеха: `https://t.me/humanAINeural_bot?start=ATL`

### P1 — следующая итерация
4. Подключить core/bitrix.py к radist_gateway.py
5. Голосовой агент — Вариант 1: gpt-4.1-mini в voice_mode + async Extractor (1-2 дня)
6. Очистка мусора в проде (40+ backup файлов, legacy)
7. deploy.sh скрипт

### P2 — голосовой агент (целевая архитектура)
8. Pipecat + Yandex SpeechKit STT/TTS + Groq/Qwen3 Extractor + gpt-4.1-mini Generator
9. Задарма SIP телефония
10. WebRTC кнопка "голосовой звонок" в веб-виджете

### P3 — техдолг
11. core/channel.py, core/observer.py
12. Atlantis context → config/source_objects.py
13. BUG-004 EN-раскладка
