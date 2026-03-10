# KNOWLEDGE_INDEX.md — база знаний Sofia-GPT

📅 Создан: 08.03.2026

## Формат записи
### [Дата] Название задачи
- **Что сделано:** ...
- **Почему:** ...
- **Файлы:** ...
- **Как откатить:** ...

---

## 10.03.2026 (вечер) — voice_mode: оптимизация латенси голосового канала

- **Что сделано:** Добавлен параметр `voice_mode` в `run_pipeline()` — отключает reasoning, Analyzer, Extractor, уменьшает RAG до 3 примеров, добавляет инструкцию "коротко"
- **Почему:** Голосовой ответ занимал 6-10с, некомфортно для живого разговора
- **Результат:** ~2с на ответ
- **Файлы:**
  - `core/pipeline.py` — `voice_mode: bool = False` в сигнатуре run_pipeline(). При True: без reasoning, без Analyzer, RAG limit=3, инструкция "2 предложения", без проверки обрезки
  - `voice_api.py` — `run_pipeline(voice_mode=True)`, Extractor (process_message) закомментирован
- **Баг найден:** `rag_stage` не определён при voice_mode=True — дефолты были внутри блока `if not skip_analyzer`. Фикс: вынесены до условия.
- **Что отключено для voice:** Reasoning, Analyzer, Extractor, проверка обрезки. RAG работает (3 примера). Generator работает (без reasoning).
- **⚠️ Компромисс:** Без Extractor state клиента не обновляется при голосовых звонках. TODO: вернуть async или после оптимизации.
- **Как откатить:** В pipeline.py убрать все `voice_mode` условия. В voice_api.py раскомментировать process_message, убрать `voice_mode=True`. Или восстановить из backup_* файлов.

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
- **Почему:** Код пайплайна (~150 строк) копировался в bot_server.py, web_api.py, sofia_radist_gateway.py. Изменение в одном не попадало в другие. Source routing работал только в bot_server.
- **Файлы:**
  - `core/__init__.py` — пустой
  - `core/pipeline.py` — `run_pipeline()`, `PipelineResult`
  - `bot_server.py` — `generate_response_with_rag()` → обёртка вокруг `run_pipeline()`
  - `web_api.py` — `generate_response()` → `run_pipeline()` + Bitrix при dialog_finished
  - `sofia_radist_gateway.py` — `generate_response()` → `run_pipeline()`
- **Что унифицировано:** Analyzer prompt, Analyzer call, RAG search, Generator call, [END] check, stop_reason check, source routing (skip analyzer + context injection), was_offline
- **Что осталось в транспортах:** save_message, Observer notify, Bitrix (web_api), set_user_stage/save_rag_log (bot_server), send_message (radist)
- **Как откатить:** `git revert` коммита, или восстановить из .bak файлов (bot_server.py.bak.20260309_1303, web_api.py.bak.20260309_1334, sofia_radist_gateway.py.bak.20260309_1342)

## 09.03.2026 — Dev-окружение Radist

- **Что сделано:** Полное dev-окружение для radist_gateway: сервис, webhook, DEV_MODE
- **Почему:** Radist gateway не имел dev-среды, правки тестировались только в проде
- **Файлы:**
  - `config/radist_config.py` — `DEV_MODE` из env, порт 5002 при DEV
  - `sofia_radist_gateway.py` — `send_message()` пропускает отправку при DEV_MODE
  - `.env` — `RADIST_DEV_MODE=true`
  - `/etc/systemd/system/sofia-radist-dev.service`
- **Radist webhooks (API):**
  - Dev Max: `fc77a7e2-7502-4968-bf45-41fb4e38769e`
  - Dev Telegram: `f1902629-ab9f-420d-880e-1cc06f26ba3a`
  - Удаление: `DELETE /v2/companies/205054/webhooks/{id}/` с X-Api-Key
- **Как откатить:** `systemctl stop sofia-radist-dev && systemctl disable sofia-radist-dev`, удалить webhook через Radist API

## 08.03.2026 — Создание dev-окружения

- **Что сделано:** Поднята безопасная среда разработки
- **Почему:** Всё было только в проде, правки шли напрямую с риском сломать клиентов
- **Что создано:**
  - `/opt/sofia-gpt-dev/` — копия прода
  - `sofia_gpt_dev.db` — отдельная БД (чистая схема)
  - `sofia-web-api-dev.service` — dev сервис на порту 8081
  - `deploy.sh` — деплой dev→prod с подтверждением
  - `CLAUDE.md` — инструкция для Claude Code
  - flake8 + black установлены
- **Как откатить:** Dev полностью изолирован, прод не менялся

## 08.03.2026 — Настройка SQLite MCP сервера

- **Что сделано:** Добавлен и настроен SQLite MCP сервер для доступа к dev БД из Claude Code
- **Почему:** Для удобной работы с БД прямо из чата (просмотр таблиц, запросы)
- **Файлы:** `.mcp.json`
- **Детали:** Переключён с `npx @modelcontextprotocol/server-sqlite` на прямой вызов `mcp-server-sqlite`
- **Как откатить:** Удалить `.mcp.json` или вернуть npx-вариант
