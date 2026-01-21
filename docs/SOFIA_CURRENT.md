# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 21.01.2026 (вечер)
🏷️ **Версия:** v2.2 — "Умная София" (Латентные метрики)

## ✅ Что сделано (21.01.2026 — Фаза 1)

### Латентные метрики (signals)
- [x] Extractor: секция ЭМОЦИОНАЛЬНЫЕ СИГНАЛЫ в промпте
- [x] Extractor: парсинг signals (friction, call_readiness, engagement, urgency)
- [x] State Manager: 4 новых поля в ClientState и БД
- [x] Planner: Action.EASE_PRESSURE (при friction > 0.7)
- [x] Planner: проверка signals перед PROPOSE_MEETING_1
- [x] Generator: отображение signals и tone_hints в СИТУАЦИЯ
- [x] Bot Server: сохранение signals в state

### Результаты тестирования
- friction 0.6, call_readiness 0.2 → НЕ предлагает MEETING_1 ✅
- friction 0.9 → EASE_PRESSURE активируется ✅
- call_readiness 0.9 → правильно распознаёт готовность ✅

## 🔄 Текущее состояние

### ✅ Работает
- Основной бот @humanAINeural_bot — active (systemd)
- Латентные метрики (friction, call_readiness, engagement, urgency)
- EASE_PRESSURE при высоком сопротивлении
- Умная проверка перед предложением созвона

### ❌ Не реализовано
- Фаза 2: Rolling Summary + Event Log
- Фаза 3: RAG по ситуации + LLM-планер

## 🔜 Следующие шаги (Фаза 2 — v2.3)
1. Rolling Summary — generate_summary() каждые 5-6 сообщений
2. Event Log — таблица событий (call_refused, question_asked, mood_change)
3. Planner использует event history

## 📁 Последние изменения
- extractor.py — секция signals в промпте, парсинг
- state_manager.py — поля friction, call_readiness, engagement, urgency
- planner.py — Action.EASE_PRESSURE, проверки signals
- sofia_prompt.py — отображение signals и tone_hints
- bot_server.py — сохранение signals, маппинг EASE_PRESSURE
