# Задачи Sofia-GPT

## 🔴 Срочные

### 1. Исправить slot_attempts (КРИТИЧНО!)
- **Приоритет:** Критический
- **Проблема:** Бот спрашивает один вопрос 8+ раз подряд
- **Причина:** slot_attempts не инкрементируется или не сохраняется
- **Файлы:** planner.py, bot_server.py, state_manager.py
- **Диагностика:**
```bash
# Добавить логи
grep -n "slot_attempts" /opt/sofia-gpt/bot_server.py
grep -n "slot_attempts" /opt/sofia-gpt/planner.py

# Проверить в БД
sqlite3 /opt/sofia-gpt/sofia_gpt.db "SELECT user_id, slot_attempts FROM client_state ORDER BY updated_at DESC LIMIT 5;"
```
- **Оценка:** 1-2 часа диагностика + фикс

### 2. Добавить обработку "не хочу созвон"
- **Приоритет:** Высокий (после фикса slot_attempts)
- **Проблема:** "не хочу созвон, давайте по ватсап" не распознаётся
- **Решение:** 
  - Добавить `objection: "no_call"` в Extractor
  - Добавить `call_refused` флаг в StateManager
  - Planner: если `call_refused` → `SEND_MATERIALS` вместо `PROPOSE_MEETING`
- **Файлы:** extractor.py, state_manager.py, planner.py
- **Оценка:** 30 мин (код был написан, нужно аккуратно добавить после фикса slot_attempts)

---

## 🟡 Следующие

### 3. Userbot: умная команда /start
- **Описание:** Команда `/start @username` которая:
  1. Сбрасывает state клиента
  2. Через Planner определяет первое действие
  3. Генерирует первое сообщение
- **Зависит от:** Фикс slot_attempts
- **Файл:** sofia_userbot_pyrogram.py
- **Оценка:** 30 мин

### 4. Systemd сервис для userbot
- **Описание:** Чтобы userbot работал 24/7
- **Файл:** /etc/systemd/system/sofia-userbot.service
- **Оценка:** 15 мин

### 5. Webhook API для автостарта диалогов
- **Описание:** POST /api/new-lead → Sofia пишет первой
- **Интеграция:** CRM, Avito, сайт
- **Оценка:** 1-2 часа

---

## 🟢 Бэклог

### RAG: использовать search_by_substage
- **Проблема:** Функция `search_by_substage()` существует, но не вызывается
- **Решение:** При `HANDLE_OBJECTION` искать примеры по типу возражения
- **Файл:** rag_module.py, bot_server.py
- **Оценка:** 1 час

### Supervisor Agent
- **Описание:** Проверка ответа перед отправкой
- **Оценка:** 3-4 часа

---

## ✅ Выполнено

### 17 января 2026 (вечер)
- ✅ Userbot v2.0 — импортирует логику из bot_server.py
- ✅ Userbot работает в базовом режиме (/send)
- ✅ Обнаружен баг slot_attempts
- ❌ Откачены изменения no_call (из-за бага)

### 17 января 2026 (утро)
- ✅ Создан userbot на Pyrogram (sofia_userbot_pyrogram.py)
- ✅ RAG обновлён до v2.1 (1926 примеров)
- ✅ Добавлены скрипты Оксаны Швецовой

### 15 января 2026
- ✅ Унификация HELP_* логики для всех слотов
- ✅ Добавлен HELP_LPR

### 14 января 2026
- ✅ Extractor v2.0 + answer_mode
- ✅ sofia_prompt v4.7

---

## Метрики

| Метрика | Текущее | Цель |
|---------|---------|------|
| GOOD rate | 93.75% | ≥90% ✅ |
| Повторы вопросов | 8+ раз ❌ | ≤2 |
| slot_attempts работает | ❌ Нет | ✅ Да |
