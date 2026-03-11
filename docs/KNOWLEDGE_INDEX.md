# KNOWLEDGE_INDEX.md — база знаний Sofia-GPT

📅 Создан: 08.03.2026

## Формат записи
### [Дата] Название задачи
- **Что сделано:** ...
- **Почему:** ...
- **Файлы:** ...
- **Как откатить:** ...

---

## 11.03.2026 — Аудит проекта + исследование собственного голосового сервиса

- **Что сделано:** Полный аудит состояния прод/дев, исследование альтернатив Retell
- **Ключевые находки:**
  - `core/` не существует в проде — все изменения с 09.03 только в dev
  - web_api.py:26 `SOFIA_PATH="/opt/sofia-gpt"` — voice пишет в прод БД (баг)
  - Незакоммиченный стриминг в pipeline.py + voice_api.py (stream_voice_response + буферизация)
- **Исследование голосового сервиса:**
  - Dasha.ai — Custom LLM только через Node.js SDK (старая версия), не подходит
  - Яндекс AI Studio Realtime — нет Custom LLM endpoint, их модель в цепочке
  - Voicyfy — no-code поверх OpenAI/Google, нет API для Custom LLM
  - **Pipecat (open-source, Python)** — лучший кандидат для собственного сервиса
  - Архитектура: SIP → Pipecat → Deepgram STT → наш pipeline → ElevenLabs/Yandex TTS
  - stream_voice_response() уже готов, нужен Pipecat LLM Service обёртка (~200-300 строк)
- **Не протестировано:** gpt-4.1-mini для voice (первый токен ~200мс vs ~800мс)

## 10.03.2026 (ночь) — stream_voice_response + буферизация чанков

- **Что сделано:** Стриминг ответа Generator для голоса — чанки идут по мере генерации, а не ждём полный ответ
- **Почему:** Даже с voice_mode (2с) пауза ощущается. Со стримингом первый звук уходит через ~0.8с
- **Файлы:**
  - `core/pipeline.py` — новая функция `stream_voice_response()`: Generator с `stream=True`, yield через asyncio.Queue
  - `voice_api.py` — буферизация: flush по знакам `.!?,` или при 20+ символов + пробел. Итог: 2-8 чанков вместо 74 микро-чанков
- **Проблема исправлена:** clean_for_voice() вызывался на каждом микро-чанке, .strip() убивал пробелы → слова склеивались. Фикс: чанки идут в буфер как есть (сырой), clean_for_voice() вызывается только на полном тексте для сохранения в БД
- **Статус:** Незакоммичен (в git diff), код работает
- **Как откатить:** `git checkout core/pipeline.py voice_api.py` — вернётся к run_pipeline(voice_mode=True) без стриминга

## 10.03.2026 (ночь) — Dasha.ai исследование

- **Что решено:** Параллельно с Retell AI изучить Dasha.ai (старая версия) для Custom LLM интеграции
- **Почему:** Retell работает, но Dasha может дать лучшее качество русского голоса / меньший латенси
- **Детали:** Blackbox-версия Dasha не подходит (нет кастомной LLM). Менеджер Dasha подтвердил возможность через старую платформу (DashaScript/API)
- **Статус:** Исследование, прототипа пока нет. Приоритет снижен — Pipecat перспективнее

## 10.03.2026 (вечер) — voice_mode: оптимизация латенси голосового канала

- **Что сделано:** Добавлен параметр `voice_mode` в `run_pipeline()` — отключает reasoning, Analyzer, Extractor, уменьшает RAG до 3 примеров, добавляет инструкцию "коротко"
- **Почему:** Голосовой ответ занимал 6-10с, некомфортно для живого разговора
- **Результат:** ~2с на ответ
- **Архитектурная заметка:** voice_mode — намеренное временное упрощение. Отключены: Extractor (state не обновляется), Analyzer, reasoning, RAG 10→3, ответ макс 2 предложения. По мере оптимизации — возвращать компоненты по одному.
- **Файлы:**
  - `core/pipeline.py` — `voice_mode: bool = False` в сигнатуре run_pipeline()
  - `voice_api.py` — `run_pipeline(voice_mode=True)` → заменён на `stream_voice_response()` (см. запись выше)
- **Как откатить:** В pipeline.py убрать все `voice_mode` условия. Или восстановить из backup_* файлов.

## 10.03.2026 (утро) — voice_api.py: Retell AI голосовой агент

- **Что сделано:** WebSocket адаптер для Retell AI Custom LLM, маршрут в web_api.py, nginx location
- **Почему:** Шаг 1 — голосовой канал для Sofia
- **Файлы:**
  - `voice_api.py` — новый: handle_voice_ws(), call_id_to_user_id(), clean_for_voice()
  - `web_api.py` — добавлен WebSocket маршрут `/llm-websocket/{call_id}`, порт 8081, channel param
  - `/etc/nginx/sites-available/sofia-api` — location /llm-websocket/ → 8081
- **Retell данные:**
  - API Key: `key_efd60e45e3721404e9239c41a9dd`
  - Agent ID: `agent_d428a1d13067a563faf30a88bb`
  - URL: `wss://api.atlantis-invest.ru/llm-websocket/`
- **User ID формула:** `7_000_000 + (md5(call_id)[:8] as int % 1_000_000)`
- **Как откатить:** Удалить voice_api.py, убрать WebSocket маршрут из web_api.py, убрать location из nginx, reload nginx

## 09.03.2026 — core/pipeline.py: единый пайплайн

- **Что сделано:** Вынесен дублированный пайплайн (Analyzer → RAG → Generator) из трёх транспортов в `core/pipeline.py`
- **Почему:** Код пайплайна (~150 строк) копировался в bot_server.py, web_api.py, sofia_radist_gateway.py. Изменение в одном не попадало в другие.
- **Файлы:**
  - `core/__init__.py` — пустой
  - `core/pipeline.py` — `run_pipeline()`, `PipelineResult`, `stream_voice_response()`
  - `bot_server.py` — `generate_response_with_rag()` → обёртка вокруг `run_pipeline()`
  - `web_api.py` — `generate_response()` → `run_pipeline()` + Bitrix при dialog_finished
  - `sofia_radist_gateway.py` — `generate_response()` → `run_pipeline()`
- **Что унифицировано:** Analyzer prompt, Analyzer call, RAG search, Generator call, [END] check, stop_reason check, source routing, was_offline
- **Что осталось в транспортах:** save_message, Observer notify, Bitrix (web_api), set_user_stage/save_rag_log (bot_server), send_message (radist)
- **ВАЖНО:** core/ НЕ существует в проде. Деплой core/ ещё не выполнялся.
- **Как откатить:** `git revert` коммита, или восстановить из .bak файлов

## 09.03.2026 — Dev-окружение Radist

- **Что сделано:** Полное dev-окружение для radist_gateway: сервис, webhook, DEV_MODE
- **Почему:** Radist gateway не имел dev-среды, правки тестировались только в проде
- **Файлы:**
  - `config/radist_config.py` — `DEV_MODE` из env, порт 5002 при DEV
  - `sofia_radist_gateway.py` — `send_message()` пропускает отправку при DEV_MODE
  - `.env` — `RADIST_DEV_MODE=true`
  - `/etc/systemd/system/sofia-radist-dev.service`
- **Как откатить:** `systemctl stop sofia-radist-dev && systemctl disable sofia-radist-dev`

## 08.03.2026 — Создание dev-окружения

- **Что сделано:** Поднята безопасная среда разработки
- **Почему:** Всё было только в проде, правки шли напрямую с риском сломать клиентов
- **Что создано:**
  - `/opt/sofia-gpt-dev/` — копия прода
  - `sofia_gpt_dev.db` — отдельная БД (чистая схема)
  - `sofia-web-api-dev.service` — dev сервис на порту 8081
  - `deploy.sh` — деплой dev→prod с подтверждением
  - `CLAUDE.md` — инструкция для Claude Code
- **Как откатить:** Dev полностью изолирован, прод не менялся

## 08.03.2026 — Настройка SQLite MCP сервера

- **Что сделано:** Добавлен и настроен SQLite MCP сервер для доступа к dev БД из Claude Code
- **Почему:** Для удобной работы с БД прямо из чата (просмотр таблиц, запросы)
- **Файлы:** `.mcp.json`
- **Как откатить:** Удалить `.mcp.json` или вернуть npx-вариант
