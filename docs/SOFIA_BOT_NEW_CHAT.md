# SOFIA BOT — ПОЛНЫЙ КОНТЕКСТ ДЛЯ НОВОГО ЧАТА

## 🎯 О проекте

**Sofia Bot** — AI-продажник для компании Oazis Estate. Автоматически обрабатывает входящие лиды с сайта через Telegram, квалифицирует клиентов и назначает видеопрезентации.

**Компания:** Oazis Estate — продаёт только новостройки от застройщиков (без вторички и аренды)
**Локации:** Сочи, Крым, Анапа, Алтай
**Методология:** "Академия Белочкиной"

**Текущая статистика:** 57% GOOD / 43% BAD
**Цель:** 80% GOOD

---

## 🔗 GitHub репо

https://github.com/semiekhin/sofia-bot

### Документация:
- https://raw.githubusercontent.com/semiekhin/sofia-bot/main/CLAUDE.md
- https://raw.githubusercontent.com/semiekhin/sofia-bot/main/PROJECT_HISTORY.md
- https://raw.githubusercontent.com/semiekhin/sofia-bot/main/SOFIA_CURRENT_TASK.md
- https://raw.githubusercontent.com/semiekhin/sofia-bot/main/SOFIA_KNOWLEDGE.md
- https://raw.githubusercontent.com/semiekhin/sofia-bot/main/RESTORE.md

### Основные файлы:
- https://raw.githubusercontent.com/semiekhin/sofia-bot/main/bot_server.py
- https://raw.githubusercontent.com/semiekhin/sofia-bot/main/sofia_prompt.py
- https://raw.githubusercontent.com/semiekhin/sofia-bot/main/sofia_analyzer.py

### Вспомогательные:
- https://raw.githubusercontent.com/semiekhin/sofia-bot/main/morning_ping.py
- https://raw.githubusercontent.com/semiekhin/sofia-bot/main/prompt_health.py
- https://raw.githubusercontent.com/semiekhin/sofia-bot/main/requirements.txt

---

## 🖥️ Сервер

```bash
# Подключение
ssh -p 2222 root@72.56.64.91

# Рабочая директория
cd /opt/sofia-bot
```

### Управление ботом:
```bash
systemctl status sofia-bot    # Статус
systemctl start sofia-bot     # Запуск
systemctl stop sofia-bot      # Остановка
systemctl restart sofia-bot   # Перезапуск
```

### Логи:
```bash
journalctl -u sofia-bot -n 50 --no-pager   # Системные логи
tail -f /opt/sofia-bot/sofia_bot.log        # Логи бота
cat /opt/sofia-bot/analyzer.log             # Логи анализатора
```

---

## ⚙️ Как работает бот

### Модель:
```python
model = "gpt-5.2"
reasoning_effort = "xhigh"
verbosity = "low"
```

### Переменные окружения (.env):
```
OPENAI_API_KEY=...
TELEGRAM_BOT_TOKEN=...
ADMIN_CHAT_ID=...
```

### Venv:
Бот использует виртуальное окружение: `/opt/sofia-bot/venv/bin/python`

Установка пакетов:
```bash
/opt/sofia-bot/venv/bin/pip install [пакет]
```

---

## 🗄️ База данных

**Файл:** `/opt/sofia-bot/sofia_conversations.db` (SQLite)

### Таблица `messages` — диалоги:
| Поле | Описание |
|------|----------|
| chat_id | ID чата |
| user_name | Имя клиента |
| role | "user" или "assistant" |
| content | Текст сообщения |
| timestamp | Время |

### Таблица `feedback_v2` — оценки экспертов:
| Поле | Описание |
|------|----------|
| expert_name | Имя эксперта |
| rating | "good" или "bad" |
| comment | Комментарий |
| timestamp | Время оценки |

### Полезные SQL запросы:
```sql
-- Подключение к БД
sqlite3 /opt/sofia-bot/sofia_conversations.db

-- Диалоги с даты
SELECT * FROM messages WHERE timestamp >= '2025-12-13' ORDER BY chat_id, timestamp;

-- Оценки с даты
SELECT * FROM feedback_v2 WHERE timestamp >= '2025-12-13' ORDER BY timestamp;

-- Статистика
SELECT rating, COUNT(*) FROM feedback_v2 WHERE timestamp >= '2025-12-13' GROUP BY rating;
```

---

## 📊 Формат отчётов

**Сергей смотрит отчёты в формате Word (.docx)**

Структура отчёта:
- Диалоги сгруппированы по клиентам
- Каждая реплика с временной меткой
- **Оценка идёт СРАЗУ ПОД оценённой репликой** со стрелкой ↳
- Цветовое выделение: зелёный = GOOD, красный = BAD
- Комментарий эксперта курсивом

Пример:
```
[14:46:47] 🤖 София: Понимаю. Цены сильно зависят от локации...
    ↳ ✅ GOOD (Александр)

[14:55:15] 🤖 София: Поняла, спасибо. По семейной ипотеке...
    ↳ ❌ BAD (Александр) — Я сказал, что смотрю Крым и там есть возможность...
```

### Как создать отчёт:
1. Выгрузить данные из БД (messages + feedback_v2)
2. Сопоставить оценки с репликами по timestamp
3. Сгенерировать Word через docx-js

---

## 🔄 Система самообучения

**Анализатор:** `sofia_analyzer.py`
**Запуск:** ежедневно в 22:00 (cron)

Как работает:
1. Загружает новые оценки из feedback_v2
2. GPT-5.2 анализирует паттерны ошибок
3. Автоматически обновляет sofia_prompt.py
4. Отправляет отчёт в Telegram

Ручной запуск:
```bash
cd /opt/sofia-bot && /opt/sofia-bot/venv/bin/python sofia_analyzer.py
```

---

## 🎭 Персонаж Софии

- **Имя:** София
- **Возраст:** 38 лет
- **Опыт:** 15 лет в недвижимости
- **Роль:** Ассистент отдела продаж (НЕ бот!)
- **Стиль:** Тёплый, профессиональный, на "Вы"

---

## ❌ Известные проблемы (из оценок экспертов)

| Проблема | Решение |
|----------|---------|
| Нет "программирования" после первого "Да" | Перед вопросом объяснить зачем он нужен |
| "Под сдачу" непрофессионально | Использовать "пассивный доход" |
| Вопрос "для себя или как инвестицию" непонятен | Дать варианты: 1) для жизни/отдыха, 2) пассивный доход, 3) рост цены |
| Сообщения слишком длинные | Разбивать, убрать лишнее |
| Вопрос о ЛПР без пояснения | Объяснить: "чтобы подготовить материалы для всех" |
| После вопроса снова текст | Вопрос должен быть в конце, без продолжения |

---

## 👥 Эксперты-оценщики

- Оксана (главный эксперт, Академия Белочкиной)
- Дарья
- Lena
- Эмилия
- Владимир
- Анастасия
- Александр

---

## 📁 Скачать промпт на мак

```bash
scp -P 2222 root@72.56.64.91:/opt/sofia-bot/sofia_prompt.py '/Users/sergeysemiekhin/Downloads/prompt for sofya/'
```

---

## 🚀 Git workflow

```bash
cd /opt/sofia-bot
git status
git add -A
git commit -m "vX.X.X: описание"
git push
```

**Важно:** Не коммитить секреты! Ключи должны быть только в .env

---

## 📅 История сессий

### Сессия 17.12.2025
**Что сделано:**
- Исследование "пропавших" данных за 12 декабря (вывод: данных не было, клиенты не писали)
- Создан Word-отчёт с диалогами и оценками (оценки под репликами)
- Исправлен bot_server.py — ключи вынесены в .env (GitHub блокировал пуш)
- Установлен python-dotenv в venv
- Запушена версия v1.0.1

**Статус:**
- Бот остановлен (systemctl stop sofia-bot)
- Версия: v1.0.1
- GOOD: 57%, цель 80%

---

## ✅ ЗАВЕРШЕНИЕ СЕССИИ — ЧЕКЛИСТ

При завершении работы обнови документацию:

1. **SOFIA_CURRENT_TASK.md** — добавь новую сессию
2. **SOFIA_KNOWLEDGE.md** — добавь новые паттерны ошибок
3. **PROJECT_HISTORY.md** — обнови историю версий

```bash
cd /opt/sofia-bot
nano SOFIA_CURRENT_TASK.md
nano SOFIA_KNOWLEDGE.md
git add -A
git commit -m "vX.X.X: описание"
git push
```

---

## 🆘 Если что-то сломалось

```bash
# Проверить логи
journalctl -u sofia-bot -n 100 --no-pager

# Проверить что venv работает
/opt/sofia-bot/venv/bin/python -c "import openai; print('OK')"

# Проверить .env
cat /opt/sofia-bot/.env

# Восстановить из git
cd /opt/sofia-bot
git checkout -- файл.py
```

---

*Версия документа: 17.12.2025*
