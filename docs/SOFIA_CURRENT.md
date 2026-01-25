# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 25.01.2026
🏷️ **Версия:** v3.1 — "LLM-Planner + RAG"

## ✅ Что сделано (25.01.2026)

### Исправлен LLM-Planner
- [x] **Баг:** LLM-Planner был включён (`USE_LLM_PLANNER=true`), но падал с ошибкой
- [x] **Причина:** `state_manager.get_messages()` — метод не существовал
- [x] **Симптом:** в логах `⚠️ LLM Planner error: 'StateManager' object has no attribute 'get_messages', fallback to deterministic`
- [x] **Решение:**
  - `bot_server.py`: заменено на `get_conversation_history(chat_id, limit=8)`
  - `sofia_userbot_pyrogram.py`: заменено на `history[-8:]`
- [x] **Результат:** LLM-Planner теперь реально работает, в логах видно `🤖 LLM Planner: action | micro_goal | tone`

## 🔄 Текущее состояние

### ✅ Работает
- Основной бот @humanAINeural_bot — active + LLM-Planner + RAG
- Userbot @SofiaOazis (+79181038493) — active + LLM-Planner
- LLM-Planner выбирает лучший action из allowed_actions (когда >1 вариант)
- RAG примеры подтягиваются для сложных кейсов
- Напоминания: 1ч днём / 9:00 после 18:00

### Как работает LLM-Planner
1. Детерминированный Planner формирует `allowed_actions[]`
2. Если 1 action → используется сразу (экономия токенов)
3. Если >1 action → LLM (gpt-5.2) выбирает лучший + добавляет:
   - `micro_goal` — дополнительная цель для Generator
   - `tone` — тон ответа (warm, professional, empathetic, playful)

### Пример из логов
```
🔀 Allowed actions: ['answer_question', 'ask_budget']
🤖 LLM Planner: answer_question | micro_goal: уточнить район/формат под бюджет 15-17 млн | tone: warm
```

## 📁 Последние изменения (25.01.2026)
- `bot_server.py` — фикс get_messages → get_conversation_history
- `sofia_userbot_pyrogram.py` — фикс get_messages → history[-8:]

## 🚀 Команды
```bash
# Перезапуск
systemctl restart sofia-gpt
systemctl restart sofia-userbot

# Логи LLM-Planner
tail -f /opt/sofia-gpt/sofia_bot.log | grep -E "LLM Planner|Allowed actions"

# Проверка что LLM-Planner работает (должен быть без error)
grep "LLM Planner:" /opt/sofia-gpt/sofia_bot.log | tail -5

# Статусы
systemctl status sofia-gpt
systemctl status sofia-userbot

# Быстрый старт диалога
/opt/sofia-gpt/sofia_start.sh @username
/opt/sofia-gpt/sofia_start.sh @username avito
```

## 🔜 Следующие шаги
1. Мониторинг LLM-Planner на реальных диалогах
2. Анализ качества выбора actions
3. Интеграция с Max (новый источник лидов)
