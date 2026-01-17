# База знаний Sofia-GPT

## Ключевые решения

### 13 января 2026: Диагностика повторов
**Проблема:** Бот повторяет вопрос о локации 4+ раза
**Причина:** Planner не считает попытки, Extractor не понимает "не знаю"
**Решение:** Нужен счётчик ask_counts в state + лимит 2 попытки
**Статус:** Не реализовано

### 12 января 2026: WAIT-логика только через Planner
**Проблема:** WAIT срабатывал на "35" (бюджет) потому что "записала" в тексте бота
**Решение:** Закомментированы строки 130-131 в planner.py
**Почему:** Planner проверяет реальный флаг state.meeting_agreed, а не угадывает по тексту

### 10 января 2026: Агентная архитектура
**Решение:** Extractor → State Manager → Planner → Generator
**Результат:** GOOD rate вырос с 64.8% до 93.75%
**Почему:** LLM не умеют считать и следовать жёстким правилам — это делает код

## Известные проблемы и решения

### Проблема: Повтор вопросов (4+ раза)
**Симптомы:** Бот спрашивает "Что по локации?" 4 раза подряд
**Причина:** Нет лимита повторов в Planner
**Решение:** Добавить ask_counts в state_manager.py + проверку в planner.py
**Файлы:** state_manager.py, planner.py

### Проблема: Extractor не понимает "не знаю"
**Симптомы:** location остаётся null после "не знаю"/"где выгоднее"
**Причина:** В промпте Extractor нет правила для неопределённых ответов
**Решение:** Добавить location: "any" для "не знаю" (как payment_type)
**Файл:** extractor.py, строки 70-130

### Проблема: "Вы на связи?" спам
**Симптомы:** Бот повторяет это после каждого сообщения
**Причина:** Не диагностирована
**Файл:** Искать в bot_server.py или sofia_prompt.py

### Проблема: assistant сохраняется с user_id=0
**Симптомы:** SELECT WHERE role='assistant' AND user_id=X возвращает 0
**Причина:** Баг в save_message()
**Файл:** bot_server.py

## Паттерны и практики

### Детерминированная логика > промпт
LLM плохо считают и следуют правилам. Выносить в код:
- Счётчики (количество вопросов, попыток)
- Порядок действий (квалификация → созвон)
- Лимиты (макс 2 вопроса на тему)

### Confidence levels
- `confirmed` — клиент явно сказал "хочу в Сочи"
- `mentioned` — клиент упомянул "слышал про Сочи"
- `null` — не говорил об этом

### Тестирование через feedback_v2
```sql
SELECT rating, COUNT(*) FROM feedback_v2 
WHERE timestamp >= '2026-01-13' 
GROUP BY rating;
```

## Полезные команды
```bash
# Диалог конкретного клиента
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT role, content, timestamp FROM messages WHERE user_id = ID ORDER BY timestamp;"

# Состояние клиента
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT * FROM client_state WHERE user_id = ID;"

# Последние оценки с комментариями
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT rating, comment, timestamp FROM feedback_v2 WHERE comment != '' ORDER BY timestamp DESC LIMIT 10;"

# Статистика по дням
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT DATE(timestamp), rating, COUNT(*) FROM feedback_v2 GROUP BY DATE(timestamp), rating;"

# Поиск в коде
grep -rn "на связи" /opt/sofia-gpt/*.py
```

## Чего НЕ делать

- **Не проверять WAIT по тексту** — только через state.meeting_agreed
- **Не добавлять общие слова в MEETING_MARKERS** — "записала" вызывает ложные срабатывания
- **Не использовать gpt-5.2 с temperature** — не поддерживается
- **Не хранить методы класса в dict** — перезапишутся через setattr
- **Не полагаться на LLM для счёта** — выносить в код

### 15.01.2026: Унификация логики HELP_* для всех слотов

**Проблема:** Payment обрабатывался иначе чем location — "не знаю" превращалось в "any, confirmed", из-за чего HELP_PAYMENT не срабатывал и бот переспрашивал тот же вопрос.

**Решение:** 
1. Унифицировали Extractor: "не знаю"/"надо подумать" → null для ВСЕХ слотов
2. Добавили HELP_LPR (не было)
3. Переписали все HELP_* — теперь объясняют ЗАЧЕМ нужна информация, а не просто переформулируют вопрос

**Почему:** 
- Клиент не идиот — повторение вопроса другими словами раздражает
- Объяснение ценности вопроса мотивирует ответить
- Если после объяснения всё равно "не знаю" — пропускаем слот, не настаиваем

### 17.01.2026 (вечер): Обнаружен баг slot_attempts

**Проблема:** Бот спрашивает один и тот же вопрос (payment_type) 8+ раз подряд, игнорируя лимит попыток.

**Симптомы:**
- Planner выдаёт `ask_payment` бесконечно
- `slot_attempts` в state показывает нули: `{'ask': 0, 'help': 0}`
- Клиент раздражается: "я ж сказал уже", "издеваетесь?"

**Где искать причину:**
1. `planner.py:230-260` — проверка `state.slot_attempts`
2. `bot_server.py:504-509` — вызов `increment_slot_attempt()`
3. `state_manager.py` — сохранение `slot_attempts` в БД (JSON поле)

**Гипотезы:**
- `increment_slot_attempt()` вызывается, но state не сохраняется в БД
- `slot_attempts` загружается из БД как пустой dict
- Логика в Planner проверяет `slot_attempts` до инкремента

**Как диагностировать:**
```bash
# Добавить логи в bot_server.py после инкремента:
print(f"DEBUG slot_attempts after increment: {client_state.slot_attempts}")

# Проверить что в БД:
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT slot_attempts FROM client_state WHERE user_id = ID;"
```

### 17.01.2026: Userbot v2.0 — правильная архитектура

**Решение:** Userbot должен ИМПОРТИРОВАТЬ логику из bot_server.py, а не копировать код.

**Почему:**
- Один источник правды — изменения в боте автоматически работают в userbot
- Общая БД — история диалогов единая
- Меньше багов — не нужно синхронизировать два кодовых потока

**Реализация:**
```python
from bot_server import (
    generate_response_with_rag,
    state_manager,
    extract_sync,
    ...
)
```

**Ограничение:** Userbot в базовой версии использует `/send` для отправки произвольного текста. Умный `/start` (через Planner) был откачен из-за бага slot_attempts.
