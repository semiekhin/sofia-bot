# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 20.01.2026, ~10:00 MSK
🏷️ **Версия:** v2.1 — "Живая София"

## ✅ Что сделано в этой сессии

### 1. Унификация промпта Generator (bot_server.py)

**Проблема:** bot_server.py и userbot использовали разную логику формирования промпта. Sofia была "зажатой", userbot — живее.

**Причина:** bot_server не передавал `action_context` в `get_system_prompt()`, добавлял свой урезанный формат.

**Решение:** Унифицировали вызов:
```python
# Было (bot_server.py)
base_prompt = get_system_prompt(user_name)  # БЕЗ action_context

# Стало (как в userbot)
system_prompt = get_system_prompt(user_name, action_context)  # С action_context
```

Убрано: stage_context, самодельный action_directive, дублирование "ОДИН вопрос".

### 2. Ситуативный контекст (planner.py)

Добавлен блок `situation` в action_context:
```python
context["situation"] = {
    "client_mood": "positive/negative/neutral",
    "dialog_stage": "early/middle/late",
    "rapport_built": True/False,
    "is_off_topic": True/False,
    "is_frustrated": True/False,
}

context["optional_hints"] = [
    "💡 Клиент в хорошем настроении — можешь пошутить",
    "💡 Клиент напряжён — сначала прояви понимание",
    ...
]
```

### 3. Личность Софии (sofia_prompt.py)

Добавлен раздел "ТВОЯ ЛИЧНОСТЬ":
- Чувство юмора
- Эмпатия
- Гибкость
- Теплота
- Формула: [Эмоциональная реакция] + [Возврат к делу]

### 4. Расширены паттерны Extractor (extractor.py)

Для связанного извлечения goal + strategy:
- "потом сдавать", "и сдавать", "чтобы сдавать", "хотим сдавать"
- "сдавать туристам", "сдавать посуточно", "под сдачу"
- "потом продать", "перепродать", "на рост цены"

Правило: "стройку и потом сдавать" → strategy: "rental" (не growth!)

## 🔄 Текущее состояние

### ✅ Работает
- Основной бот @humanAINeural_bot — active (running)
- Userbot в интерактивном режиме
- Две ветки квалификации (INVESTMENT/PERSONAL)
- Два созвона + счётчик отказов
- slot_attempts защита от повторов
- Связанное извлечение goal + strategy
- **NEW:** Ситуативный контекст для живости
- **NEW:** Раздел "личность" в промпте
- **NEW:** Унифицированный промпт bot ↔ userbot

### ❌ Не реализовано
- Финансовый модуль (откачен в v2.0, требует аккуратной реинтеграции)
- Daemon режим userbot + HTTP API

## 📁 Изменённые файлы (эта сессия)

| Файл | Изменение |
|------|-----------|
| `bot_server.py` | Унификация get_system_prompt(user_name, action_context) |
| `planner.py` | Добавлен situation + optional_hints |
| `sofia_prompt.py` | Раздел "ТВОЯ ЛИЧНОСТЬ" + вывод situation/hints |
| `extractor.py` | Расширены паттерны для strategy (rental/growth) |

## 🚀 Как запустить
```bash
# Бот (автозапуск)
systemctl status sofia-gpt

# Userbot (интерактивный режим)
cd /opt/sofia-gpt && ./venv/bin/python sofia_userbot_pyrogram.py
# Команды: /start @username, /send @username Текст, /quit
```

## 🧪 Как проверить живость

Напиши боту:
1. Позитивное: "Привет! Отличная погода 😊" — должна поддержать тон
2. Off-topic: "А вы давно работаете?" — ответит и вернётся к делу
3. Негативное: "Дорого у вас..." — проявит понимание

## 📋 Архитектура (напоминание)
```
Telegram → Extractor (gpt-5.2) → State Manager → Planner (код) → RAG → Generator (gpt-5.2) → Telegram
```

- **Planner = КОД** — 100% предсказуемость, выбирает ЧТО делать
- **Generator = LLM** — креативность, выбирает КАК сказать
- **situation + hints** — контекст для Generator, чтобы адаптировать стиль
