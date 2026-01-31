# Sofia-GPT — Контекст проекта

📅 **Обновлено:** 31.01.2026

## 🎯 Что это

Sofia-GPT — AI-бот для продажи недвижимости Oazis Estate в Сочи.
Работает в Telegram и Max через Radist.Online, квалифицирует лиды и записывает на видеоконсультации.

## 🖥 Инфраструктура

| Компонент | Значение |
|-----------|----------|
| Сервер | 72.56.64.91:2222 |
| Путь | /opt/sofia-gpt/ |
| Python | 3.11 |
| База данных | SQLite |

## 📱 Каналы связи

### Telegram Bot
| Параметр | Значение |
|----------|----------|
| Бот | @humanAINeural_bot |
| Сервис | sofia-gpt.service |

### Telegram через Radist
| Параметр | Значение |
|----------|----------|
| Номер | +79181038493 |
| Connection ID | 80200 |

### Max через Radist
| Параметр | Значение |
|----------|----------|
| Номер | +79284466701 |
| Connection ID | 80024 |

### Radist.Online
| Параметр | Значение |
|----------|----------|
| API | https://api-ru.radist.online/v2 |
| Company ID | 205054 |
| Gateway сервис | sofia-radist.service |
| Webhook | http://72.56.64.91:5001/webhook/radist |

## 🔧 Основные команды
```bash
# Проактивная отправка (первый контакт с клиентом)
/opt/sofia-gpt/sofia_outreach.sh telegram @username [Имя]
/opt/sofia-gpt/sofia_outreach.sh max 79001234567 [Имя]

# Перезапуск сервисов
systemctl restart sofia-gpt        # Telegram Bot
systemctl restart sofia-radist     # Radist Gateway (Max + Telegram)

# Логи
tail -f /opt/sofia-gpt/sofia_bot.log      # Telegram Bot
tail -f /opt/sofia-gpt/sofia_radist.log   # Radist Gateway

# Статус
systemctl status sofia-gpt
systemctl status sofia-radist
```

## 📊 Observer Chat

Группа "Диалоги Софья" — все диалоги из всех каналов в одном месте.
Chat ID: -5206139579

## 🧠 Архитектура
```
Сообщение → Extractor (GPT-5.2) → State Manager → Planner → RAG → Generator → Ответ
```

Подробнее: SOFIA_ARCHITECTURE.md

## 📁 Ключевые файлы

| Файл | Назначение |
|------|------------|
| bot_server.py | Telegram Bot |
| sofia_radist_gateway.py | Gateway для Max/Telegram через Radist |
| sofia_outreach.sh | Проактивная отправка |
| message_processor.py | Единая логика обработки |
| extractor.py | NLU — понимание сообщений |
| planner.py | Выбор действия |
| state_manager.py | Состояние клиента |
| sofia_prompt.py | Промпт генератора |
| rag_module.py | RAG с примерами |

## 📚 Документация

- SOFIA_CONTEXT.md — этот файл
- SOFIA_CURRENT.md — текущий статус
- SOFIA_ARCHITECTURE.md — архитектура
- SOFIA_TASKS.md — задачи
- SOFIA_BUGS.md — известные баги
- SOFIA_KNOWLEDGE.md — база знаний
