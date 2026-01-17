# Задачи Sofia-GPT

## 🟢 Готово к тестированию

### Sofia-GPT v2.0 — РЕАЛИЗОВАНО
- ✅ Две ветки диалога (INVESTMENT / PERSONAL)
- ✅ Разный порядок вопросов для каждой ветки
- ✅ Два предложения созвона (PROPOSE_MEETING_1 и PROPOSE_MEETING_2)
- ✅ Счётчик отказов (materials_request_count >= 2 → завершаем)
- ✅ Новые поля: branch, strategy, usage, family, call_proposal_count, materials_request_count, dialog_finished, finish_type
- ✅ Формулировки Оксаны в RAG (13 примеров)

---

## 🟡 Следующие задачи

### 1. Тестирование v2.0
- **Описание:** Полное тестирование всех сценариев
- **Сценарии:**
  - INVESTMENT: goal → strategy → budget → MEETING_1 → payment → location → lpr → MEETING_2
  - PERSONAL: goal → usage → location → budget → MEETING_1 → family → payment → lpr → MEETING_2
  - Два отказа → FINISH_WITH_MATERIALS
- **Оценка:** 30 мин

### 2. Мониторинг Generator compliance
- **Описание:** Следить что Generator слушает директивы PROPOSE_MEETING_*
- **Как:** Смотреть логи, сравнивать action Planner'а с текстом ответа
- **Оценка:** ongoing

### 3. Настроить уведомления менеджеру
- **Описание:** При dialog_finished=True отправлять уведомление
- **Куда:** Telegram / webhook (уточнить)
- **Оценка:** 30 мин

### 4. Userbot v2.0
- **Описание:** Восстановить userbot с импортом из bot_server.py
- **Зависит от:** Тестирование v2.0
- **Файл:** sofia_userbot_pyrogram.py
- **Оценка:** 1 час

---

## ✅ Выполнено

### 17 января 2026 (поздняя ночь)
- ✅ Реализована полная спецификация Sofia-GPT v2.0
- ✅ Миграция БД (8 новых колонок)
- ✅ state_manager.py — новые поля v2.0
- ✅ planner.py — две ветки квалификации, новые Actions
- ✅ extractor.py — strategy, usage, family
- ✅ sofia_prompt.py — описания новых Actions, усиленные директивы
- ✅ bot_server.py — сохранение v2.0 полей
- ✅ RAG — 13 формулировок Оксаны
- ✅ RAG_EXAMPLES_COUNT увеличен до 5

### 17 января 2026 (ночь)
- ✅ Исправлен баг slot_attempts (маппинг payment → payment_type)
- ✅ Добавлена логика no_call в Extractor
- ✅ Добавлен флаг call_refused в StateManager
- ✅ Логика пропуска HANDLE_OBJECTION при повторном no_call
- ✅ Разработана спецификация Sofia-GPT v2.0

### 17 января 2026 (вечер)
- ✅ Userbot v2.0 — импортирует логику из bot_server.py
- ✅ Обнаружен баг slot_attempts

### 17 января 2026 (утро)
- ✅ Создан userbot на Pyrogram
- ✅ RAG обновлён до v2.1

### 15 января 2026
- ✅ Унификация HELP_* логики для всех слотов
- ✅ Добавлен HELP_LPR

---

## Метрики

| Метрика | Статус |
|---------|--------|
| slot_attempts работает | ✅ |
| no_call распознаётся | ✅ |
| Две ветки квалификации | ✅ |
| Два предложения созвона | ✅ |
| Счётчик отказов | ✅ |
| RAG с формулировками Оксаны | ✅ |
| RAG примеров | 1939 |
