# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 22.01.2026 (ночь)
🏷️ **Версия:** v3.0 — "LLM-Planner"

## ✅ Что сделано (22.01.2026 ночь)

### Реализован LLM-Planner (v3.0)
- [x] `get_allowed_actions()` в planner.py — возвращает список допустимых actions
- [x] Новый модуль `llm_planner.py` — LLM выбирает лучший action + micro_goal + tone
- [x] Интеграция в bot_server.py с флагом `USE_LLM_PLANNER`
- [x] Синхронизация userbot с v3.0
- [x] Включен на проде: `USE_LLM_PLANNER=true`

### Как работает LLM-Planner
1. Детерминированный Planner формирует `allowed_actions[]` (1-5 вариантов)
2. Если вариантов > 1 → LLM (gpt-5.2 + reasoning:high) выбирает лучший
3. LLM возвращает: action + micro_goal + tone
4. micro_goal передаётся Generator для "комбо-ответов"
5. Fallback на детерминированный Planner при ошибке

### Примеры работы
| Ситуация | allowed_actions | Выбор LLM |
|----------|-----------------|-----------|
| Вопрос + нужен budget | [answer_question, ask_budget] | answer_question + micro_goal: "спросить бюджет" |
| Возражение + вопрос | [handle_objection, answer_question] | answer_question (ответить на вопрос важнее) |
| Холодный клиент | [propose_meeting_1, ask_payment] | ask_payment (не давить созвоном) |
| Вовлечённый клиент | [propose_meeting_1, ask_family] | propose_meeting_1 (момент для созвона) |

## 🔄 Текущее состояние

### ✅ Работает
- Основной бот @humanAINeural_bot — active (systemd) + LLM-Planner
- Userbot sofia-userbot — active (systemd) + LLM-Planner
- Латентные метрики (friction, call_readiness, engagement, urgency)
- EASE_PRESSURE при высоком сопротивлении
- Finance calculator — расчёт доходности
- Комбо-ответы через micro_goal

### ❌ Не реализовано
- Critic (проверка ответа перед отправкой) — опционально

## 📁 Изменённые файлы
- `planner.py` — добавлен `get_allowed_actions()` (~200 строк)
- `llm_planner.py` — новый модуль (~250 строк)
- `bot_server.py` — интеграция LLM-Planner
- `sofia_userbot_pyrogram.py` — синхронизация с v3.0
- `.env` — добавлен `USE_LLM_PLANNER=true`

## 🔧 Конфигурация

### Флаги в .env
```
USE_LLM_PLANNER=true    # Включить LLM-Planner (по умолчанию false)
MODEL_MODE=gpt-5.2      # Модель для Generator
```

### LLM-Planner использует
- Модель: gpt-5.2
- Reasoning: effort=high
- Max tokens: 300

### Стоимость
- ~$0.01-0.03 за вызов LLM-Planner
- Вызывается только когда allowed_actions > 1
- Общая стоимость диалога: ~$0.50-0.80

## 🚀 Команды
```bash
# Перезапуск
systemctl restart sofia-gpt
systemctl restart sofia-userbot

# Логи
tail -f /opt/sofia-gpt/sofia_bot.log
journalctl -u sofia-userbot -f

# Отключить LLM-Planner (откат на v2.2)
sed -i 's/USE_LLM_PLANNER=true/USE_LLM_PLANNER=false/' /opt/sofia-gpt/.env
systemctl restart sofia-gpt sofia-userbot

# Отправить первое сообщение клиенту
/opt/sofia-gpt/sofia_start.sh @username
```

## 🔜 Следующие шаги
1. Мониторинг на реальных диалогах
2. Анализ логов LLM-Planner
3. (Опционально) Добавление Critic
4. Тюнинг промпта LLM-Planner если нужно
