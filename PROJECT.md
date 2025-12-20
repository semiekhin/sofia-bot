# PROJECT.md — Sofia Bot

> Единая точка входа. Этот файл содержит ВСЁ для продолжения работы.

---

## 🤖 CLAUDE: СТАРТ СЕССИИ

### 1. Прочитай HANDOFF (внизу документа)
Пойми: что горит, что сделали, что дальше.

### 2. Загрузи актуальный код

**Основные:**
```
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/bot_server.py
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/sofia_prompt.py
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/sofia_analyzer.py
```

**Вспомогательные:**
```
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/morning_ping.py
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/prompt_health.py
```

**Скрипты анализа:**
```
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/scripts/dialog_processor.py
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/scripts/batch_process.py
```

### 3. Скажи
"Изучил PROJECT.md и код. [Состояние из HANDOFF]. Что делаем?"

### Контрольные слова
| Команда | Действие |
|---------|----------|
| `актуализируем` | Обновить PROJECT.md (HANDOFF, TASKS, CHANGELOG) → commit → push |
| `переходим в новый чат` | Актуализация + выдать ссылку: `https://raw.githubusercontent.com/semiekhin/sofia-bot/main/PROJECT.md` |

### Стандарт разработки
Полные правила: `DEV_STANDARD.md` в этом репо.
Краткая суть: dev → тест → согласование → деплой prod → проверка → commit → push → обновить PROJECT.md

---

## 📋 QUICK INFO

| Параметр | Значение |
|----------|----------|
| **Проект** | Sofia Bot — AI-продажник недвижимости |
| **Компания** | Oazis Estate |
| **Стек** | Python 3.12, python-telegram-bot, OpenAI GPT-5.2, SQLite |
| **Версия** | 1.0.5 |
| **Статус** | ✅ Production |

### Ссылки

| Ресурс | URL |
|--------|-----|
| **GitHub** | https://github.com/semiekhin/sofia-bot |
| **PROJECT.md (raw)** | https://raw.githubusercontent.com/semiekhin/sofia-bot/main/PROJECT.md |
| **Сервер** | `ssh -p 2222 root@72.56.64.91` |
| **Рабочая директория** | `/opt/sofia-bot` |
| **Бот** | @SofiaOazisBot |

### Все файлы кода (raw ссылки для загрузки)
```
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/bot_server.py
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/sofia_prompt.py
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/sofia_analyzer.py
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/morning_ping.py
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/prompt_health.py
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/scripts/dialog_processor.py
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/scripts/batch_process.py
https://raw.githubusercontent.com/semiekhin/sofia-bot/main/requirements.txt
```

---

## 🔐 СЕКРЕТЫ

**Расположение:** `/opt/sofia-bot/.env` (chmod 600, не в git)

| Переменная | Описание |
|------------|----------|
| `OPENAI_API_KEY` | API ключ OpenAI |
| `TELEGRAM_BOT_TOKEN` | Токен бота |
| `ADMIN_CHAT_ID` | Chat ID для уведомлений |

---

## 🗄️ БАЗА ДАННЫХ

**Файл:** `/opt/sofia-bot/sofia_conversations.db` (SQLite, не в git)

### Таблицы

| Таблица | Назначение |
|---------|------------|
| `messages` | Все сообщения диалогов |
| `users` | Пользователи бота |
| `feedback_v2` | Оценки экспертов с контекстом и комментариями |

### Структура таблиц

```sql
-- Сообщения
CREATE TABLE messages (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER,
    user_id INTEGER,
    user_name TEXT,
    role TEXT,           -- 'user' или 'assistant'
    content TEXT,
    timestamp DATETIME,
    processed INTEGER
);

-- Пользователи
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    chat_id INTEGER,
    user_name TEXT,
    first_contact DATETIME,
    last_message DATETIME,
    messages_count INTEGER
);

-- Оценки экспертов
CREATE TABLE feedback_v2 (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER,
    user_id INTEGER,
    expert_name TEXT,
    context TEXT,        -- JSON: последние 8 сообщений
    rating TEXT,         -- 'good' или 'bad'
    comment TEXT,
    timestamp DATETIME
);
```

### Полезные SQL запросы

```bash
sqlite3 /opt/sofia-bot/sofia_conversations.db
```

```sql
-- Диалоги с даты
SELECT * FROM messages 
WHERE timestamp >= '2025-12-20' 
ORDER BY chat_id, timestamp;

-- Оценки с даты
SELECT * FROM feedback_v2 
WHERE timestamp >= '2025-12-20' 
ORDER BY timestamp;

-- Статистика оценок
SELECT rating, COUNT(*) as cnt 
FROM feedback_v2 
WHERE timestamp >= '2025-12-20' 
GROUP BY rating;

-- GOOD rate
SELECT 
    ROUND(100.0 * SUM(CASE WHEN rating='good' THEN 1 ELSE 0 END) / COUNT(*), 1) as good_rate
FROM feedback_v2;

-- Последние диалоги с оценками
SELECT f.timestamp, f.expert_name, f.rating, f.comment
FROM feedback_v2 f
ORDER BY f.timestamp DESC
LIMIT 20;
```

---

## 🏗️ АРХИТЕКТУРА

```
Telegram → bot_server.py → GPT-5.2 → Ответ клиенту
                │
                ▼
         sofia_prompt.py (промпт v3.5)
                │
                ▼
      sofia_conversations.db (SQLite)
                │
       ┌────────┴────────┐
       ▼                 ▼
 Оценки экспертов   22:00 cron
       │                 │
       └────────┬────────┘
                ▼
        sofia_analyzer.py
                │
                ▼
   Новый промпт → рестарт бота
```

### Ключевые файлы

| Файл | Назначение |
|------|------------|
| `bot_server.py` | Telegram бот, GPT, антифлуд, оценки экспертов |
| `sofia_prompt.py` | Промпт v3.5: квалификация, живая речь, объекты с ценами |
| `sofia_analyzer.py` | Ночной анализ (22:00) → обновление промпта → рестарт |
| `morning_ping.py` | Утренние напоминания клиентам |
| `prompt_health.py` | Мониторинг здоровья промпта |
| `sofia_conversations.db` | SQLite: диалоги, оценки, пользователи |
| `scripts/dialog_processor.py` | Парсинг RTF/TXT + LLM-оценка по 3 навыкам |
| `scripts/batch_process.py` | Пакетный анализ папки диалогов |
| `requirements.txt` | Зависимости Python |

### Структура
```
/opt/sofia-bot/
├── bot_server.py           # Главный бот
├── sofia_prompt.py         # Промпт v3.5
├── sofia_analyzer.py       # Ночной анализатор
├── morning_ping.py         # Утренние напоминания
├── prompt_health.py        # Мониторинг здоровья промпта
├── requirements.txt        # Зависимости Python
├── sofia_conversations.db  # SQLite база
├── .env                    # Секреты (не в git)
├── PROJECT.md              # ← Этот файл
├── DEV_STANDARD.md         # Стандарт разработки
├── backups/                # Бэкапы промптов (7 дней)
├── analyzer_logs/          # Логи анализатора
├── scripts/
│   ├── dialog_processor.py # Парсинг + LLM-оценка диалогов
│   └── batch_process.py    # Пакетная обработка
└── venv/                   # Python virtual environment
```

---

## ⚙️ УПРАВЛЕНИЕ

### Бот
```bash
systemctl status sofia-bot
systemctl restart sofia-bot
journalctl -u sofia-bot -f
tail -f /opt/sofia-bot/sofia_bot.log
```

### Анализатор (ручной запуск)
```bash
cd /opt/sofia-bot
export $(cat .env | xargs) && python3 sofia_analyzer.py
```

### Git
```bash
cd /opt/sofia-bot
git add -A && git commit -m "vX.X.X: описание" && git push
```

### Cron
```
0 22 * * * — sofia_analyzer.py (самообучение)
```

### Откат промпта
```bash
ls backups/
cp backups/sofia_prompt_XXXXXXXX.py sofia_prompt.py
systemctl restart sofia-bot
```

---

## 📊 МЕТРИКИ

### Текущее состояние (2025-12-20)

| Метрика | Значение | Цель | Статус |
|---------|----------|------|--------|
| GOOD rate | 57% | 80% | 🔴 |
| Квалификация | 3.1/10 | ≥7 | 🔴 |
| Закрытие | 6.1/10 | ≥7 | 🟡 |
| Возражения | 4.2/10 | ≥7 | 🟡 |

### Главная проблема
**95% диалогов без квалификации.** Бот спамит объектами, не выясняя:
1. Цель (инвестиция / для себя / сдавать)
2. Локация (Сочи, Крым, Анапа, Алтай)
3. Бюджет / платёж

---

## 🚨 РИСКИ

| Риск | Митигация |
|------|-----------|
| Промпт сломался | Бэкапы в `backups/`, откат вручную |
| OpenAI rate limit | Антифлуд 3 сек, мониторинг |
| Бот упал | systemd restart, алерт в Telegram |
| Клиент раздражён | Антиповтор в промпте |
| Потеря контекста | PROJECT.md + HANDOFF всегда актуальны |

### Резервирование
- **Код:** GitHub
- **Данные:** SQLite на сервере + бэкапы
- **Промпт:** `backups/` (7 дней)

### Быстрое восстановление (5 минут)

```bash
# Бот упал
systemctl restart sofia-bot
journalctl -u sofia-bot -f

# Промпт сломался
ls backups/
cp backups/sofia_prompt_XXXXXXXX.py sofia_prompt.py
systemctl restart sofia-bot
```

### Полное восстановление на новом сервере (30 минут)

```bash
# 1. Установка
apt update && apt install -y python3-venv python3-pip git ufw fail2ban

# 2. Клонировать
cd /opt
git clone git@github.com:semiekhin/sofia-bot.git sofia-bot
cd sofia-bot

# 3. Секреты
cat > .env << 'ENVEOF'
OPENAI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=...
ADMIN_CHAT_ID=512319063
ENVEOF
chmod 600 .env

# 4. Зависимости
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 5. Systemd
cat > /etc/systemd/system/sofia-bot.service << 'SVCEOF'
[Unit]
Description=Sofia Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/sofia-bot
ExecStart=/opt/sofia-bot/venv/bin/python bot_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF

systemctl daemon-reload
systemctl enable sofia-bot
systemctl start sofia-bot

# 6. Cron (анализатор 22:00)
crontab -e
# Добавить:
# 0 22 * * * cd /opt/sofia-bot && export $(cat .env | xargs) && python3 sofia_analyzer.py >> analyzer.log 2>&1

# 7. Проверка
systemctl status sofia-bot
```

### Обход блокировок
- Сервер в США — OpenAI работает напрямую
- Telegram — без ограничений

---

## 📝 TASKS

### 🔥 Сейчас
- [ ] Усилить квалификацию в промпте — Sofia ДОЛЖНА квалифицировать
- [ ] Создать синтетические примеры квалификации
- [ ] Интегрировать skill-based оценку в самообучение

### 📋 Backlog
- [ ] GOOD rate 57% → 80%
- [ ] RAG когда промпт > 15k токенов
- [ ] Fine-tuning при 500+ GOOD диалогов

### ✅ Сделано
- [x] v1.0.5: Skill-based assessment
- [x] v1.0.4: Промпт v3.5 — живая речь, цены
- [x] v1.0.3: Word-отчёты, .env
- [x] v1.0.0: Самообучение 22:00

---

## 🛠️ ИНСТРУМЕНТЫ

### Скачивание диалогов из CRM

Открой диалог в CRM → F12 → Console → вставь:

```javascript
let messages = [];
let currentDate = '';

document.querySelectorAll('.message-list__message-group-date, .base-message__message').forEach(el => {
    if (el.classList.contains('message-list__message-group-date')) {
        currentDate = el.innerText?.trim() || '';
    } else {
        let author = el.querySelector('.base-message__message-author .text-main')?.innerText?.trim() || '';
        let text = el.querySelector('.base-message__message-body .text-main')?.innerText?.trim() || '';
        let time = el.querySelector('.base-message__message-time time')?.innerText?.trim() || '';
        
        if (!text) return;
        if (text === author) return;
        if (text.length < 3 && !text.match(/^(да|ок|нет)$/i)) return;
        
        let [h, m] = (time || '00:00').split(':').map(Number);
        messages.push({ date: currentDate, time, minutes: h * 60 + m, author, text });
    }
});

let groups = {};
messages.forEach(m => {
    if (!groups[m.date]) groups[m.date] = [];
    groups[m.date].push(m);
});

let dates = Object.keys(groups).reverse();
let result = [];

dates.forEach(date => {
    groups[date].sort((a, b) => a.minutes - b.minutes);
    groups[date].forEach(m => {
        result.push(`[${m.date} ${m.time}] ${m.author}: ${m.text}`);
    });
});

copy(result.join('\n\n'));
console.log('✅ Скопировано! Сообщений: ' + result.length);
```

---

## 👥 ТЕСТИРОВЩИКИ

- **Оксана** — главный эксперт (Академия Белочкиной)
- Гульнара, Леся, Дарья, Эмилия, Владимир, Анастасия, Александр

---

## 🗣️ ТЕРМИНЫ СОФИИ

| ❌ Неправильно | ✅ Правильно |
|----------------|--------------|
| под сдачу | пассивный доход |
| сдача дома | срок ввода / передача ключей |
| данный объект | этот проект |
| стоимость составляет | порядка X миллионов |
| длинные сообщения | короткие, ёмкие |

---

## 📈 ПОРОГИ МЕТРИК

| Метрика | 🟢 Норма | 🟡 Внимание | 🔴 Проблема |
|---------|----------|-------------|-------------|
| GOOD rate | > 80% | 65-80% | < 65% |
| Квалификация | > 7/10 | 5-7 | < 5 |
| Закрытие | > 7/10 | 5-7 | < 5 |
| Токены промпта | < 8k | 8-15k | > 15k |

---

## 📜 CHANGELOG

### v1.0.5 (2025-12-20)
- Система skill-based assessment (квалификация, закрытие, возражения)
- Скрипты `dialog_processor.py`, `batch_process.py`
- Анализ 40 диалогов: квалификация 3.1, закрытие 6.1, возражения 4.2
- PROJECT.md + DEV_STANDARD.md

### v1.0.4 (2025-12-18)
- Промпт v3.5: живая речь, словарь замен
- База объектов с ценами

### v1.0.3 (2025-12-17)
- Word-отчёты
- Секреты в .env

### v1.0.0 (2025-12-11)
- Автоанализ GPT-5.1 (cron 22:00)
- prompt_health.py, morning_ping.py

### v0.1 (2025-12-10)
- MVP: бот + промпт + оценки

---

## 🔄 HANDOFF

> Последняя сессия: 2025-12-20

### Что горит
- Квалификация 3.1/10 — **критично**
- 95% диалогов без квалификации

### Что сделали в этой сессии
- Изучили всю кодовую базу
- Создали DEV_STANDARD.md (универсальный стандарт)
- Создали PROJECT.md (по стандарту)
- Сохранили стандарт в память Claude

### Что не успели
- Усилить квалификацию в промпте
- Создать синтетические примеры
- Задеплоить PROJECT.md и DEV_STANDARD.md в репо

### Следующий шаг
1. Залить PROJECT.md и DEV_STANDARD.md в репо
2. Усилить блок квалификации в sofia_prompt.py

### Контекст
- Есть 2 хороших диалога для примера: Дмитрий Оазис, 79246903398
- София должна ВСЕГДА квалифицировать перед отправкой объектов
- Бот на проде — осторожно с изменениями

---

*Последнее обновление: 2025-12-20*
