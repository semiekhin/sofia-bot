# Задачи Sofia-GPT

📅 Обновлено: 18.01.2026

## ✅ Выполнено

### v2.0 Core (17.01.2026)
- [x] Миграция БД — 8 новых колонок в client_state
- [x] state_manager.py — все v2.0 поля
- [x] planner.py — две ветки INVESTMENT/PERSONAL, два созвона
- [x] extractor.py — новые слоты strategy/usage/family
- [x] sofia_prompt.py — директивы PROPOSE_MEETING_*
- [x] RAG — диалог oksana_scripts_v2 (13 примеров)
- [x] Фикс slot_attempts (маппинг payment → payment_type)

### Сессия 18.01.2026 (ночь)
- [x] Уведомления менеджеру при dialog_finished=True
- [x] RAG по action Planner'а (не по Stage Detector)
- [x] "Живой" промпт — эмодзи, разнообразие, человечность
- [x] RAG_EXAMPLES_COUNT увеличен до 10

### Сессия 18.01.2026 (день) — Userbot v2.0
- [x] Восстановлен из бэкапа
- [x] ACTION_TO_SLOT маппинг (фикс slot_attempts)
- [x] ACTION_TO_RAG_STAGE маппинг (RAG по action)
- [x] RAG_EXAMPLES_COUNT = 10
- [x] gpt-5.2 Responses API (MODEL_MODE из .env)
- [x] Сохранение v2.0 полей (branch, счётчики, dialog_finished)
- [x] Логирование в /opt/sofia-gpt/userbot.log
- [x] Systemd сервис создан
- [x] Связанное извлечение goal + strategy в extractor.py

## 🔄 В процессе

### Тестирование Userbot v2.0
- [ ] Полный цикл квалификации INVESTMENT
- [ ] Полный цикл квалификации PERSONAL
- [ ] Связанное извлечение goal + strategy
- [ ] Два созвона, счётчик отказов
- [ ] Параллельные диалоги
- **Статус:** Тестируется вручную

## 📋 TODO

### Приоритет 1: Дотестировать Userbot v2.0
**Время:** 1-2 дня

1. Полный цикл INVESTMENT: goal → strategy → budget → MEETING_1 → payment → location → lpr → MEETING_2
2. Полный цикл PERSONAL: goal → usage → location → budget → MEETING_1 → family → payment → lpr → MEETING_2
3. Проверить счётчик отказов (2 отказа → FINISH_WITH_MATERIALS)
4. Проверить связанное извлечение ("буду сдавать" → goal + strategy)

### Приоритет 2: Daemon режим + HTTP API
**Время:** 2-3 дня

1. Переделать userbot в daemon режим:
   - Убрать интерактивный input()
   - Только обработка входящих + API

2. Добавить HTTP API (Flask/FastAPI):
```python
POST /api/new-lead
{
  "target": "@username" или "+79123456789",
  "name": "Иван",
  "source": "avito"
}
```

3. Интеграция с n8n для автоматических лидов

4. Systemd автозапуск

### Приоритет 3: Финансовый консультант (БОЛЬШОЙ АПГРЕЙД)
**Время:** 1-2 недели

**Неделя 1: Данные и калькулятор**
- [ ] `finance_fetcher.py` — парсинг ключевой ставки ЦБ
- [ ] Парсинг депозитов (banki.ru)
- [ ] `finance_calculator.py` — расчёты доходности
- [ ] `finance_data.json` — структура данных
- [ ] Cron для автообновления

**Неделя 2: Интеграция в Sofia**
- [ ] Extractor — триггеры finance_question, deposit_better
- [ ] Planner — Actions: CONSULT_FINANCE, COMPARE_DEPOSIT, CALCULATE_YIELD
- [ ] Промпт — финансовые аргументы
- [ ] RAG — 30-50 финансовых диалогов
- [ ] Режим "консультант" после квалификации

**Архитектура:**
```
Data Fetcher (API ЦБ, банки) → finance_data.json
                                      ↓
Calculator (депозит vs недвижимость) → action_context
                                      ↓
Generator → финансовые аргументы с расчётами
```

## 🐛 Известные проблемы

| Проблема | Статус | Решение |
|----------|--------|---------|
| ~~slot_attempts не инкрементировался~~ | ✅ Исправлено | Маппинг ACTION_TO_SLOT |
| ~~RAG по неправильному stage~~ | ✅ Исправлено | ACTION_TO_RAG_STAGE |
| ~~Generator игнорировал PROPOSE_MEETING~~ | ✅ Исправлено | Усилены директивы |
| ~~Userbot откачен до v1.0~~ | ✅ Исправлено | Восстановлен + улучшен |
| ~~"сдавать в аренду" не извлекает strategy~~ | ✅ Исправлено | Связанное извлечение |
| Userbot только интерактивный | ⏳ Ожидает | Daemon режим + API |

## 📊 Метрики

- **RAG примеров:** 1939
- **RAG на запрос:** 10
- **Quality distribution:** excellent 76%, good 18%, poor 6%
- **Userbot версия:** 2.0
