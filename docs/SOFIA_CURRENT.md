# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 17.01.2026 (ночь, поздняя) — реализация спецификации v2.0

## ✅ Что сделано в этой сессии

### Полная реализация Sofia-GPT v2.0

#### 1. Миграция БД — 8 новых колонок
```sql
ALTER TABLE client_state ADD COLUMN branch TEXT;
ALTER TABLE client_state ADD COLUMN strategy TEXT;
ALTER TABLE client_state ADD COLUMN usage TEXT;
ALTER TABLE client_state ADD COLUMN family TEXT;
ALTER TABLE client_state ADD COLUMN call_proposal_count INTEGER DEFAULT 0;
ALTER TABLE client_state ADD COLUMN materials_request_count INTEGER DEFAULT 0;
ALTER TABLE client_state ADD COLUMN dialog_finished BOOLEAN DEFAULT 0;
ALTER TABLE client_state ADD COLUMN finish_type TEXT;
```

#### 2. state_manager.py — новые поля
- Добавлены поля: branch, strategy, usage, family
- Добавлены счётчики: call_proposal_count, materials_request_count
- Добавлены флаги завершения: dialog_finished, finish_type
- Обновлены: _init_db(), get_state(), _save_state()
- Расширен slot_attempts для новых слотов (strategy, usage, family)

#### 3. planner.py — полная переработка логики v2.0
- Добавлены новые Actions:
  - ASK_STRATEGY, ASK_USAGE, ASK_FAMILY
  - PROPOSE_MEETING_1, PROPOSE_MEETING_2
  - FINISH_WITH_MATERIALS
- Реализованы две ветки квалификации:
  - _qualify_investment(): goal → strategy → budget → MEETING_1 → payment → location → lpr → MEETING_2
  - _qualify_personal(): goal → usage → location → budget → MEETING_1 → family → payment → lpr → MEETING_2
- Счётчик отказов: materials_request_count >= 2 → FINISH_WITH_MATERIALS
- Обновлены тесты под v2.0 (11 тестов)

#### 4. extractor.py — новые поля
- Добавлено извлечение: strategy, usage, family
- Обновлён target_slot с новыми слотами
- Добавлены правила извлечения для каждого поля

#### 5. sofia_prompt.py — описания новых Actions
- Добавлены описания: ASK_STRATEGY, ASK_USAGE, ASK_FAMILY
- Добавлены описания: PROPOSE_MEETING_1, PROPOSE_MEETING_2, FINISH_WITH_MATERIALS
- Усилены директивы: "ОБЯЗАНА предложить созвон" для PROPOSE_MEETING_*

#### 6. bot_server.py — интеграция v2.0
- Добавлено сохранение v2.0 полей после Planner:
  - branch, call_proposal_count, materials_request_count
  - dialog_finished, finish_type при завершении
- RAG_EXAMPLES_COUNT увеличен с 3 до 5

#### 7. RAG — формулировки Оксаны
- Добавлен диалог 'oksana_scripts_v2' с 13 примерами:
  - 3 примера для PROPOSE_MEETING_1 (первое предложение)
  - 7 примеров для PROPOSE_MEETING_2 (второе предложение, работа с возражениями)
  - 3 примера для FINISH_WITH_MATERIALS (завершение после отказов)
- RAG переиндексирован: 1939 примеров (было 1926)

## 🔄 Текущее состояние

### Работает ✅
- Две ветки квалификации (INVESTMENT / PERSONAL)
- Два предложения созвона (PROPOSE_MEETING_1 / PROPOSE_MEETING_2)
- Счётчик отказов (materials_request_count)
- Завершение диалога (dialog_finished, finish_type)
- RAG с формулировками Оксаны (1939 примеров)
- Бот запущен и работает (@humanAINeural_bot)

### Требует тестирования ⚠️
- Полный флоу INVESTMENT ветки
- Полный флоу PERSONAL ветки
- Сценарий с 2 отказами → FINISH_WITH_MATERIALS
- Проверка что Generator всегда слушает PROPOSE_MEETING_* директивы

## 🔜 Следующие шаги
1. Протестировать все сценарии v2.0
2. Мониторить логи на предмет игнорирования директив Generator'ом
3. При необходимости усилить промпт

## 📁 Последние изменения
- `state_manager.py` — новые поля v2.0, обновлены все методы работы с БД
- `planner.py` — полностью переписан get_next_action(), добавлены _qualify_investment(), _qualify_personal()
- `extractor.py` — добавлены strategy, usage, family в промпт и формат
- `sofia_prompt.py` — описания новых Actions, усиленные директивы
- `bot_server.py` — сохранение v2.0 полей, RAG_EXAMPLES_COUNT=5
- `rag_training_data.json` — добавлены 13 примеров Оксаны
- БД `sofia_gpt.db` — 8 новых колонок
