# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 17.01.2026 (ночь)

## ✅ Что сделано в этой сессии

### 1. Исправлен критический баг slot_attempts
- **Проблема:** Бот спрашивал payment_type 8+ раз подряд
- **Причина:** Несоответствие имён: action `ask_payment` → slot `"payment"`, а в БД `"payment_type"`
- **Решение:** Добавлен маппинг `ACTION_TO_SLOT = {"payment": "payment_type"}` в bot_server.py
- **Коммит:** `4cac35fd`

### 2. Добавлена логика no_call (отказ от созвона)
- В Extractor добавлено `objection: "no_call"`
- В StateManager добавлено поле `call_refused`
- В Planner: если `call_refused=True` и повторный `no_call` → пропускаем HANDLE_OBJECTION

### 3. Разработана спецификация Sofia-GPT v2.0
- Две ветки диалога: INVESTMENT и PERSONAL
- Разный порядок вопросов для каждой ветки
- Два предложения созвона (после базовой и полной квалификации)
- Счётчик отказов — при 2 отказах завершаем
- Формулировки из RAG (скрипты Оксаны)

## 🔄 Текущее состояние

### Работает ✅
- Основной бот (@humanAINeural_bot)
- slot_attempts для payment_type
- Распознавание no_call в Extractor
- Флаг call_refused в БД

### Требует доработки ⚠️
- Полная переработка Planner под спецификацию v2.0
- Добавление новых полей в state_manager
- Загрузка формулировок Оксаны в RAG
- Логика двух предложений созвона

## 🔜 Следующие шаги
1. **ПРИОРИТЕТ:** Реализовать спецификацию Sofia-GPT v2.0
2. Добавить новые поля в state_manager (branch, strategy, usage, family, call_proposal_count, materials_request_count, dialog_finished, finish_type)
3. Переписать Planner с двумя ветками квалификации
4. Загрузить формулировки в RAG
5. Тестирование

## 📁 Последние изменения
- `bot_server.py` — добавлен ACTION_TO_SLOT маппинг для slot_attempts
- `extractor.py` — добавлен no_call в objection, установка call_refused
- `state_manager.py` — добавлено поле call_refused
- `planner.py` — логика пропуска HANDLE_OBJECTION при повторном no_call
