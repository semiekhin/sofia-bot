# Задачи Sofia-GPT

## 🔴 Срочные

### 1. Реализовать спецификацию Sofia-GPT v2.0 (ПРИОРИТЕТ!)
- **Описание:** Полная переработка логики квалификации
- **Файлы:** planner.py, state_manager.py, extractor.py, sofia_prompt.py
- **Детали:** См. спецификацию в конце сессии 17.01.2026 (ночь)
- **Оценка:** 2-3 часа

### Что включает v2.0:
1. Две ветки диалога (INVESTMENT / PERSONAL)
2. Разный порядок вопросов для каждой ветки
3. Два предложения созвона (PROPOSE_MEETING_1 и PROPOSE_MEETING_2)
4. Счётчик отказов (materials_request_count >= 2 → завершаем)
5. Новые поля: branch, strategy, usage, family, call_proposal_count, materials_request_count, dialog_finished, finish_type
6. Формулировки из RAG (скрипты Оксаны)

---

## 🟡 Следующие

### 2. Загрузить формулировки Оксаны в RAG
- **Описание:** Добавить скрипты продаж в rag_training_data.json
- **Теги:** stage: "propose_meeting", substage: "first_proposal" / "second_proposal" / "objection_no_call"
- **Оценка:** 30 мин

### 3. Userbot v2.0
- **Описание:** Восстановить userbot с импортом из bot_server.py
- **Зависит от:** Реализация v2.0
- **Файл:** sofia_userbot_pyrogram.py
- **Оценка:** 1 час

### 4. Настроить уведомления менеджеру
- **Описание:** При dialog_finished=True отправлять уведомление
- **Куда:** Telegram / webhook (уточнить)
- **Оценка:** 30 мин

---

## ✅ Выполнено

### 17 января 2026 (ночь)
- ✅ Исправлен баг slot_attempts (маппинг payment → payment_type)
- ✅ Добавлена логика no_call в Extractor
- ✅ Добавлен флаг call_refused в StateManager
- ✅ Логика пропуска HANDLE_OBJECTION при повторном no_call
- ✅ Разработана спецификация Sofia-GPT v2.0

### 17 января 2026 (вечер)
- ✅ Userbot v2.0 — импортирует логику из bot_server.py
- ✅ Обнаружен баг slot_attempts
- ❌ Откачены изменения no_call (из-за бага SQL)

### 17 января 2026 (утро)
- ✅ Создан userbot на Pyrogram
- ✅ RAG обновлён до v2.1

### 15 января 2026
- ✅ Унификация HELP_* логики для всех слотов
- ✅ Добавлен HELP_LPR

---

## Метрики

| Метрика | Текущее | Цель |
|---------|---------|------|
| slot_attempts работает | ✅ Да | ✅ Да |
| no_call распознаётся | ✅ Да | ✅ Да |
| Две ветки квалификации | ❌ Нет | ✅ Да |
| Два предложения созвона | ❌ Нет | ✅ Да |
| Счётчик отказов | ❌ Нет | ✅ Да |
