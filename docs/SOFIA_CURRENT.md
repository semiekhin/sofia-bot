# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 21.01.2026
🏷️ **Версия:** v2.1.1 — "Живая София" + Daemon

## ✅ Что сделано (21.01.2026)

### 1. Daemon-режим юзербота
- Добавлен `main_daemon()` — режим без интерактивных команд
- Флаг запуска: `python sofia_userbot_pyrogram.py --daemon`
- Использует `pyrogram.idle()` для поддержания процесса

### 2. Скрипт sofia_start.sh
- Умный старт диалога: `./sofia_start.sh @username [источник]`
- Автоматически останавливает daemon, запускает диалог, возвращает daemon

### 3. Правила форматирования
- Добавлен блок в промпт: БЕЗ markdown в Telegram
- Нет **звёздочек**, _подчёркиваний_, `бэктиков`

## ✅ Что сделано ранее (20.01.2026 — v2.1)

- Унификация промпта Generator (bot_server.py = userbot)
- Ситуативный контекст: situation + optional_hints (planner.py)
- Личность Софии: юмор, эмпатия, гибкость, теплота
- Расширены паттерны Extractor ("сдавать" → rental)
- Финансовый модуль v1.1 (question_type "profitability")
- Трансляция диалогов в группу наблюдателей (-5206139579)

## 🔄 Текущее состояние

### ✅ Работает
- Основной бот @humanAINeural_bot — active (systemd)
- Userbot — daemon-режим + интерактивный режим
- Две ветки квалификации (INVESTMENT/PERSONAL)
- Ситуативный контекст + hints
- Финансовый расчёт при вопросе о доходности
- Трансляция в группу наблюдателей
- Скрипт sofia_start.sh для быстрого старта

### ❌ Не реализовано
- HTTP API для автоматических лидов
- systemd сервис sofia-userbot.service (daemon работает, но не автозапуск)

## 🔜 Следующие шаги
1. Создать systemd сервис для userbot daemon
2. Тестирование финансового модуля на реальных диалогах
3. HTTP API для лидов из CRM

## 🚀 Как запустить
```bash
# Основной бот (автозапуск)
systemctl status sofia-gpt

# Userbot — интерактивный режим
cd /opt/sofia-gpt && ./venv/bin/python sofia_userbot_pyrogram.py

# Userbot — daemon режим
cd /opt/sofia-gpt && ./venv/bin/python sofia_userbot_pyrogram.py --daemon

# Быстрый старт диалога с лидом
./sofia_start.sh @username avito
```

## 📁 Ключевые файлы

| Файл | Назначение |
|------|------------|
| `bot_server.py` | Основной бот, обработка сообщений |
| `sofia_userbot_pyrogram.py` | Userbot (v2.1 + daemon) |
| `sofia_start.sh` | Скрипт быстрого старта диалога |
| `planner.py` | Детерминированная логика + ситуативный контекст |
| `sofia_prompt.py` | Промпт генератора + личность |
| `extractor.py` | NLU, извлечение фактов |
| `finance_calculator.py` | Финансовый модуль |
