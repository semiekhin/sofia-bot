# KNOWLEDGE_INDEX.md — база знаний Sofia-GPT

📅 Создан: 08.03.2026

## Формат записи
### [Дата] Название задачи
- **Что сделано:** ...
- **Почему:** ...
- **Файлы:** ...
- **Как откатить:** ...

---

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
