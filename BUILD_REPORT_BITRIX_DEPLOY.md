# BUILD REPORT: Деплой БП + дедупликация + логирование

**Дата:** 2026-04-04
**Бэкап:** `/opt/sofia-gpt/backups/20260404_bitrix/`

## Acceptance Criteria

| AC | Описание | Статус | Доказательство |
|----|----------|--------|---------------|
| AC-1 | В prod `core/bitrix.py` есть `finalize_lead()` и `start_distribution_bp()` | PASS | `grep` подтвердил строки 578, 618 |
| AC-2 | Все точки завершения вызывают `finalize_lead()` | PASS | bot_server.py:790,986 + web_api.py:272 — все `finalize_lead`, не `restore_assigned` |
| AC-3 | В prod `.env` есть `BITRIX_BP_TEMPLATE_ID=152` | PASS | `grep` подтвердил |
| AC-4 | Дедупликация по телефону перед созданием лида | PASS | `find_lead_by_phone()` (bitrix.py:179) вызывается в `create_or_update_lead()` (bitrix.py:401) |
| AC-5 | Логирование создания, обновления, дедупликации, БП | PASS | info на успех, warning/error на ошибки — во всех функциях |
| AC-6 | Ошибка `bizproc.workflow.start` не ломает flow | PASS | `start_distribution_bp()` возвращает False + warning, `finalize_lead()` не пробрасывает исключение |
| AC-7 | Тест `/start ATL` → лог `BP 152 started` | PARTIAL | Деплой выполнен, сервисы живы, но ручной тест не прогнан — требуется реальный диалог |
| AC-8 | flake8 + black | PASS | `core/bitrix.py` — чистый; `web_api.py` — только pre-existing E402/E501 |

## Что изменено

### core/bitrix.py
- Добавлена `find_lead_by_phone()` — поиск лида по телефону через `crm.lead.list`
- `create_or_update_lead()` — дедупликация: если `lead_id=None` и есть телефон → ищет в Битрикс перед созданием
- `finalize_lead()` — добавлен info-лог
- Функции `start_distribution_bp()` и `finalize_lead()` были в DEV, теперь задеплоены в PROD

### bot_server.py
- Строки 790, 986: `restore_assigned()` → `finalize_lead()` (было в DEV, задеплоено в PROD)

### web_api.py
- Импорт: `restore_assigned` → `finalize_lead`
- Строка 272: `restore_assigned()` → `finalize_lead()`

### .env (PROD)
- Добавлен `BITRIX_BP_TEMPLATE_ID=152`

## Риски
- AC-7 не полностью проверен — нужен реальный тестовый диалог через `/start ATL` или веб-виджет
- `find_lead_by_phone()` ищет по STATUS_ID=NEW — не найдёт дубли если лид уже переведён в другую стадию
