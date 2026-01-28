# Sofia-GPT — Контекст проекта

📅 **Обновлено:** 28.01.2026

## 🎯 Что это

Sofia-GPT — AI-бот для продажи недвижимости Oazis Estate в Сочи.
Работает в Telegram и Max, квалифицирует лиды и записывает на видеоконсультации.

## 🖥 Инфраструктура

| Компонент | Значение |
|-----------|----------|
| Сервер | 72.56.64.91:2222 |
| Путь | /opt/sofia-gpt/ |
| Python | 3.11 |
| База данных | SQLite |

## 📱 Каналы связи

### Telegram
| Параметр | Значение |
|----------|----------|
| Бот | @humanAINeural_bot |
| Userbot | @SofiaOazis |
| Номер userbot | +79676407597 |
| Сервис | sofia-bot.service |
| Сервис userbot | sofia-userbot.service |

### Max (через Radist.Online)
| Параметр | Значение |
|----------|----------|
| Номер | +79284466701 |
| API URL | https://api-ru.radist.online/v2 |
| company_id | 205054 |
| connection_id | 80024 |
| Подписка до | 31.01.2026 |

## 🧠 Архитектура
```
Telegram/Max → Extractor → State Manager → Planner → RAG → Generator → Ответ
```

- **Extractor** — NLU, извлекает интенты и сущности
- **State Manager** — SQLite, хранит состояние диалога
- **Planner** — LLM-Planner v2.2, выбирает действия
- **RAG** — ChromaDB, примеры из реальных продаж
- **Generator** — GPT-5.2, генерирует ответы

## 📁 Структура проекта
```
/opt/sofia-gpt/
├── bot_server.py           # Основной Telegram бот
├── sofia_userbot_pyrogram.py # Telegram userbot
├── state_manager.py        # Управление состоянием
├── extractor.py            # NLU
├── planner.py              # LLM-Planner
├── generator.py            # Генерация ответов
├── config/
│   └── radist_config.py    # Конфиг Radist API
├── docs/
│   ├── SOFIA_CONTEXT.md    # Этот файл
│   ├── SOFIA_CURRENT.md    # Текущий статус
│   ├── SOFIA_ARCHITECTURE.md
│   ├── SOFIA_KNOWLEDGE.md
│   ├── SOFIA_TASKS.md
│   └── RADIST_API.md       # Документация Radist
└── rag/
    └── training_data/      # Обучающие данные
```

## 🔧 Управление сервисами
```bash
# Статус
systemctl status sofia-bot sofia-userbot

# Перезапуск
systemctl restart sofia-bot
systemctl restart sofia-userbot

# Логи
journalctl -u sofia-bot -f
journalctl -u sofia-userbot -f
```

## 📋 Текущие задачи

1. ☐ Настроить webhook Radist для входящих из Max
2. ☐ Написать sofia_radist_gateway.py
3. ☐ Интегрировать Max gateway с основной Sofia
4. ☐ Продлить подписку Radist (до 31.01!)

## 🔗 Ссылки

- GitHub: https://github.com/semiekhin/sofia-bot
- Radist Docs: https://docs.radist.online
- Radist Swagger: https://api-ru.radist.online/v2/docs
