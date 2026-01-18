# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 18.01.2026, 12:30 MSK

## ✅ Что сделано в этой сессии

### Userbot v2.0 — полностью восстановлен и улучшен
- Восстановлен из бэкапа `sofia_userbot_pyrogram.py.backup_20260117_132806`
- Добавлен `ACTION_TO_SLOT` маппинг (фикс slot_attempts: payment → payment_type)
- Добавлен `ACTION_TO_RAG_STAGE` маппинг (RAG ищет по action Planner'а)
- `RAG_EXAMPLES_COUNT = 10` (синхронизировано с bot_server.py)
- Переключен на `gpt-5.2 Responses API` (MODEL_MODE из .env)
- Добавлено сохранение v2.0 полей (branch, call_proposal_count, materials_request_count, dialog_finished)
- Добавлено логирование в файл `/opt/sofia-gpt/userbot.log`
- Создан systemd сервис `/etc/systemd/system/sofia-userbot.service`
- Версия обновлена до 2.0

### Extractor — связанное извлечение goal + strategy
- Добавлено правило: "сдавать в аренду" → goal: investment + strategy: rental (оба confirmed)
- Добавлено правило: "для перепродажи" → goal: investment + strategy: growth (оба confirmed)

## 🔄 Текущее состояние

### ✅ Работает
- Основной бот @humanAINeural_bot — active (running)
- Userbot v2.0 — работает в интерактивном режиме
- Команды: `/start @username`, `/start @username avito`, `/send @username Текст`
- Параллельные диалоги с несколькими клиентами
- Логирование в `/opt/sofia-gpt/userbot.log`
- RAG по action Planner'а (10 примеров)
- gpt-5.2 Responses API

### ⚠️ Требует тестирования
- Связанное извлечение goal + strategy (только что добавлено)
- Длительные диалоги через userbot

### ❌ Не реализовано
- Systemd автозапуск userbot (сервис создан, но интерактивный режим не подходит)
- HTTP API для автоматического старта диалогов из CRM/n8n
- Daemon режим userbot

## 🔜 Следующие шаги

### Приоритет 1: Дотестировать Userbot
- Полный цикл квалификации через userbot
- Проверить связанное извлечение goal + strategy
- Проверить v2.0 логику (две ветки, два созвона, счётчик отказов)

### Приоритет 2: Daemon режим + API (для автоматизации)
- Переделать userbot в daemon режим (без интерактивного input)
- Добавить HTTP API: `POST /api/new-lead` → Sofia пишет первой
- Интеграция с n8n для автоматической обработки лидов

### Приоритет 3: Финансовый консультант (БОЛЬШОЙ АПГРЕЙД)
- Парсинг ключевой ставки ЦБ
- Парсинг ставок депозитов
- Калькулятор доходности (депозит vs недвижимость)
- Новые Actions: CONSULT_FINANCE, COMPARE_DEPOSIT, CALCULATE_YIELD
- RAG по финансовым диалогам (30-50 примеров)
- Режим "консультант" (не заканчивать после FINISH_WITH_MATERIALS)

## 📁 Последние изменения

| Файл | Изменение |
|------|-----------|
| `sofia_userbot_pyrogram.py` | v2.0: ACTION_TO_SLOT, ACTION_TO_RAG_STAGE, gpt-5.2, логирование |
| `extractor.py` | Связанное извлечение goal + strategy |
| `/etc/systemd/system/sofia-userbot.service` | Создан (для будущего daemon режима) |

## 📊 Файлы Userbot

- **Основной:** `/opt/sofia-gpt/sofia_userbot_pyrogram.py` (v2.0)
- **Логи:** `/opt/sofia-gpt/userbot.log`
- **Сессия:** `/opt/sofia-gpt/sofia_pyrogram.session`
- **Systemd:** `/etc/systemd/system/sofia-userbot.service`

## 🚀 Как запустить Userbot
```bash
# Терминал 1 — логи
tail -F /opt/sofia-gpt/userbot.log

# Терминал 2 — userbot
cd /opt/sofia-gpt && ./venv/bin/python sofia_userbot_pyrogram.py

# Команды в userbot:
# /start @username — умный старт через Planner
# /start @username avito — старт с источником
# /send @username Текст — произвольное сообщение
# /quit — выход
```
