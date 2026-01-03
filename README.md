# Sofia Bot — Hybrid System v1.0

## Концепция

**Проблема:** LLM не умеет считать и следовать жёстким правилам. Даже с подробным промптом модель интерпретирует инструкции как хочет.

**Решение:** Гибридная система:
- **КОД** считает, анализирует, принимает решения
- **LLM** только генерирует текст

## Как это работает

```
┌─────────────────────────────────────────────────────────┐
│                 СООБЩЕНИЕ КЛИЕНТА                       │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│              АНАЛИЗ ИСТОРИИ (КОД)                       │
│                                                         │
│  • send_requests = 2                                    │
│  • call_rejections = 1                                  │
│  • neutral_answers = 3                                  │
│  • irritation_detected = True                           │
│  • questions_after_last_send = 1                        │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│              РЕШЕНИЕ (ЖЁСТКАЯ ЛОГИКА)                   │
│                                                         │
│  if irritated → SEND_MATERIALS, no questions            │
│  if send_requests >= 2 → SEND_MATERIALS, no questions   │
│  if neutral >= 3 → SEND_MATERIALS, no questions         │
│  ...                                                    │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│              ГЕНЕРАЦИЯ ТЕКСТА (LLM)                     │
│                                                         │
│  Задача: "Скажи что пришлёшь варианты. БЕЗ ВОПРОСОВ."   │
│  → LLM генерирует живой текст                           │
└────────────────────────┬────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────┐
│              СТРАХОВКА (КОД)                            │
│                                                         │
│  if not allow_questions and "?" in response:            │
│      response = remove_question(response)               │
└─────────────────────────────────────────────────────────┘
```

## Жёсткие лимиты

| Условие | Действие |
|---------|----------|
| Клиент раздражён | → SEND_MATERIALS, без вопросов |
| 2+ раз "скинь" | → SEND_MATERIALS, без вопросов |
| 1+ вопрос после "скинь" и снова "скинь" | → SEND_MATERIALS, без вопросов |
| 14+ сообщений | → SEND_MATERIALS, без вопросов |
| 2+ отказа от созвона | → SEND_MATERIALS, без вопросов |
| 3+ ответа "без разницы" | → SEND_MATERIALS, без вопросов |

## Паттерны детекции

### Запрос скинуть
```
скинь, отправь, пришли, покажи, скиньте, отправьте, пришлите, 
можно варианты, что есть, хочу посмотреть
```

### Отказ от созвона
```
не хочу звон, не надо звон, без звонка, лучше скинь, 
просто скинь, занят, некогда
```

### Раздражение
```
издеваешься, достал, хватит, много вопросов, я же сказал, 
я же говорил, повторяю, сколько можно
```

### Нейтральный ответ
```
без разницы, всё равно, любой, не важно, как хотите, 
на ваш выбор, не знаю, хз
```

## Структура файлов

```
sofia_hybrid/
├── sofia_hybrid.py        # Основная логика (детекторы, анализ, генерация)
├── bot_server_hybrid.py   # Telegram интеграция
├── switch_system.sh       # Скрипт переключения hybrid/legacy
├── requirements.txt
└── README.md
```

## Установка

### 1. Копирование на сервер

```bash
# С локальной машины
scp -P 2222 -r sofia_hybrid root@72.56.64.91:/opt/

# Или через архив
scp -P 2222 sofia_hybrid.zip root@72.56.64.91:/opt/
ssh -p 2222 root@72.56.64.91 "cd /opt && unzip sofia_hybrid.zip -d sofia-hybrid"
```

### 2. Установка зависимостей

```bash
cd /opt/sofia-hybrid
pip install -r requirements.txt --break-system-packages
```

### 3. Настройка переменных

```bash
# Создаём .env или используем существующий от legacy системы
cat > /opt/sofia-hybrid/.env << 'EOF'
TELEGRAM_BOT_TOKEN=ваш_токен
OPENAI_API_KEY=ваш_ключ
DB_PATH=/opt/sofia-hybrid/sofia_hybrid.db
EOF
```

### 4. Переключение систем

```bash
# Сделать скрипт исполняемым
chmod +x /opt/sofia-hybrid/switch_system.sh

# Переключить на гибридную систему
/opt/sofia-hybrid/switch_system.sh hybrid

# Вернуться на legacy
/opt/sofia-hybrid/switch_system.sh legacy

# Проверить статус
/opt/sofia-hybrid/switch_system.sh status
```

## Ручная настройка systemd

Если скрипт не работает:

```bash
# Создаём сервис
cat > /etc/systemd/system/sofia-hybrid.service << 'EOF'
[Unit]
Description=Sofia Bot (Hybrid)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/sofia-hybrid
Environment=TELEGRAM_BOT_TOKEN=xxx
Environment=OPENAI_API_KEY=xxx
Environment=DB_PATH=/opt/sofia-hybrid/sofia_hybrid.db
ExecStart=/usr/bin/python3 /opt/sofia-hybrid/bot_server_hybrid.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Запускаем
systemctl daemon-reload
systemctl enable sofia-hybrid
systemctl start sofia-hybrid
systemctl status sofia-hybrid
```

## Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Начать новый диалог |
| `/status` | Показать счётчики и состояние |
| `/reset` | Сбросить диалог |
| `/debug` | Последние 5 решений системы |

## Мониторинг

### Логи
```bash
journalctl -u sofia-hybrid -f
```

### Debug в БД
```bash
sqlite3 /opt/sofia-hybrid/sofia_hybrid.db "
SELECT timestamp, action, reason, user_message 
FROM debug_logs 
ORDER BY timestamp DESC 
LIMIT 10;
"
```

### Статистика
```bash
sqlite3 /opt/sofia-hybrid/sofia_hybrid.db "
SELECT action, reason, COUNT(*) 
FROM debug_logs 
GROUP BY action, reason;
"
```

## Откат на legacy систему

### Быстрый откат
```bash
/opt/sofia-hybrid/switch_system.sh legacy
```

### Ручной откат
```bash
systemctl stop sofia-hybrid
systemctl start sofia-bot
```

## Сравнение систем

| Аспект | Legacy (v3.5/v4.1) | Hybrid |
|--------|-------------------|--------|
| Счётчики | LLM не считает | Код считает точно |
| "2+ скинь" → стоп | Может проигнорировать | Гарантированно |
| Раздражение | Может не заметить | Детектор + страховка |
| Вопросы когда нельзя | Может задать | Код вырежет |
| Отладка | Сложно | debug_logs в БД |
| Откат | — | 1 команда |

## Настройка лимитов

В файле `sofia_hybrid.py`:

```python
# Лимиты
MAX_MESSAGES = 14              # Максимум сообщений в диалоге
MAX_QUESTIONS_AFTER_SEND = 1   # Вопросов после "скинь"
MAX_CALL_REJECTIONS = 2        # Отказов от созвона
MAX_NEUTRAL_ANSWERS = 3        # Ответов "без разницы"
```

## Добавление паттернов

В файле `sofia_hybrid.py`:

```python
IRRITATED_PATTERNS = [
    "издеваешься", "достал", ...
    "новый_паттерн",  # добавить сюда
]
```

После изменений:
```bash
systemctl restart sofia-hybrid
```

## Известные ограничения

1. **Детекторы на паттернах** — могут пропустить новые формулировки
2. **Нет ML-классификации** — можно добавить позже
3. **Один язык** — только русский

## TODO

- [ ] ML-классификатор настроения
- [ ] Интеграция с CRM
- [ ] A/B тестирование hybrid vs legacy
- [ ] Дашборд метрик
