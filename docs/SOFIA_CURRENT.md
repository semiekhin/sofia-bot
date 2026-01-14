# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 14 января 2026, 11:50

## ✅ Что сделано (14.01.2026)

### Промпты
- **EXTRACTOR_SYSTEM_PROMPT v2.0** — задеплоен в extractor.py
  - Новые поля: answered_last_bot_question, answer_mode, target_slot, conversation_complete
  - Работает корректно (проверено в логах)
  
- **sofia_prompt.py v4.7** — задеплоен
  - Добавлен блок "РАБОТА С ACTION_CONTEXT"
  - Таблица реакций по answer_mode
  - Блок "ДЕЙСТВИЯ HELP_*"
  - Правило №15 (не упоминать служебные слова)
  - Функция get_system_prompt принимает action_context

### Код
- **planner.py** — обновлён get_action_context()
  - Добавлена передача: answered_last_bot_question, answer_mode, target_slot, conversation_complete

## 🔄 Текущее состояние

### Работает ✅
- Extractor возвращает новые поля (answer_mode, target_slot)
- Generator реагирует на answer_mode="unknown" — варьирует вопросы
- action_context передаётся из Planner в Generator

### Не работает ❌
- **Planner застревает на слоте** — после 2+ "не знаю" продолжает ask_location (5 раз подряд)
- Нет slot_attempts (счётчик попыток)
- Нет HELP_* actions в Planner

## 🔜 Следующие шаги

### Приоритет 1: Лимит попыток в Planner
1. state_manager.py — добавить slot_attempts
2. planner.py — добавить HELP_* actions
3. planner.py — логика: ASK (1 раз) → HELP (1 раз) → пропуск слота

### Приоритет 2: Улучшить концовку
- Не переспрашивать "куда отправить" если клиент уже сказал
- Сократить подборку до 2-3 вариантов

## 📁 Изменённые файлы (14.01.2026)
- `extractor.py` — EXTRACTOR_SYSTEM_PROMPT v2.0
- `sofia_prompt.py` — v4.7 (action_context, answer_mode, HELP_*)
- `planner.py` — get_action_context() с новыми полями

## 📊 Метрики
- GOOD rate: ~93.75% (сохранился)
- Повторы: Generator варьирует, но Planner шлёт одинаковый action
