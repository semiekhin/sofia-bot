# Sofia Bot — AI-продажник недвижимости

## Что это
AI-менеджер по продажам курортной недвижимости для Oazis Estate. Общается с клиентами в Telegram, квалифицирует и выводит на видеопрезентацию. Самообучается каждую ночь на основе оценок экспертов.

## Бот
- Prod: @SofiaOazisBot

## Сервер
```bash
ssh -p 2222 root@72.56.64.91
cd /opt/sofia-bot
```

## Стек
- Python 3.12
- python-telegram-bot
- OpenAI GPT-5.2 (reasoning: xhigh, verbosity: low)
- SQLite

## Версия: 1.0.4 (промпт v3.5)

## Ключевые файлы
```
/opt/sofia-bot/
├── bot_server.py           # Главный бот
├── sofia_prompt.py         # Промпт v3.5 (автообновляется)
├── sofia_analyzer.py       # Ночной анализатор (22:00)
├── prompt_health.py        # Мониторинг здоровья
├── morning_ping.py         # Утренние напоминания
├── sofia_conversations.db  # База диалогов и оценок
├── .env                    # Секреты (не в git!)
├── backups/                # Бэкапы промптов (7 дней)
├── analyzer_logs/          # Логи анализатора
└── scripts/                # Скрипты анализа диалогов
    ├── dialog_processor.py # Парсинг RTF + LLM-оценка
    └── batch_process.py    # Пакетная обработка
```

## Последняя сессия: 2025-12-20
- ✅ Промпт v3.5 — живая речь, база объектов с ценами
- ✅ Система оценки диалогов менеджеров (skill-based)
- ✅ Анализ 40 диалогов: квалификация 3.1/10, закрытие 6.1/10
- ✅ Word-отчёт с детальным разбором

## Текущие метрики
- GOOD rate: 57% (цель 80%)
- Квалификация менеджеров: 3.1/10 (95% без квалификации!)
- Закрытие на созвон: 6.1/10 (50% хороших примеров)

## Команды
```bash
# Статус бота
systemctl status sofia-bot

# Логи
journalctl -u sofia-bot -f
tail -f sofia_bot.log

# Здоровье промпта
python3 prompt_health.py

# Ручной анализ
export $(cat .env | xargs) && python3 sofia_analyzer.py

# Анализ диалогов менеджеров
cd scripts && python3 batch_process.py "../диалоги" --llm --provider openai

# Git
git add -A && git commit -m "описание" && git push
```

---

## 📥 Скачивание диалогов из CRM

Открой диалог в CRM, нажми F12 → Console, вставь код:
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
        
        // Фильтруем мусор
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

Результат будет в буфере обмена — вставь в .txt или .rtf файл.

---

## Документация
- `SOFIA_CURRENT_TASK.md` — текущие задачи
- `SOFIA_KNOWLEDGE.md` — база знаний
- `PROJECT_HISTORY.md` — история проекта
- `RESTORE.md` — восстановление

---
*Обновлено: 20.12.2025*
