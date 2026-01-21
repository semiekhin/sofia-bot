# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 22.01.2026 (ночь)
🏷️ **Версия:** v2.2 — "Умная София" (Латентные метрики)

## ✅ Что сделано (22.01.2026)

### Синхронизация userbot с v2.2
- [x] Добавлен ease_pressure в ACTION_TO_RAG_STAGE
- [x] Добавлено сохранение signals (friction, call_readiness, engagement, urgency)
- [x] Добавлена обработка WAIT (return None + проверка в handle_message)
- [x] Добавлен finance_calculator (расчёт доходности при вопросе о прибыльности)
- [x] Daemon перезапущен с новыми изменениями

### Обсуждение архитектуры v3.0
- [x] Проверен доступ к моделям (gpt-5.2, gpt-5.2-pro доступны)
- [x] Спроектирована архитектура LLM-Planner + Critic
- [x] Рассчитана стоимость (~$0.50-0.80 за диалог)
- [x] Решено делать безопасно — обёртка вокруг существующего Planner с fallback

## 🔄 Текущее состояние

### ✅ Работает
- Основной бот @humanAINeural_bot — active (systemd)
- Userbot sofia-userbot — active (systemd), синхронизирован с v2.2
- Латентные метрики (friction, call_readiness, engagement, urgency)
- EASE_PRESSURE при высоком сопротивлении
- Finance calculator — расчёт доходности

### ❌ Не реализовано
- Фаза 3: LLM-Planner (обёртка вокруг детерминированного Planner)
- Critic (проверка ответа перед отправкой)

## 🔜 Следующие шаги (Фаза 3 — v3.0)
1. Рефакторинг planner.py → `get_allowed_actions()`
2. Создание `llm_planner.py` — LLM выбирает лучший action из allowed
3. Интеграция с флагом `USE_LLM_PLANNER` (безопасный rollout)
4. Тестирование на реальных диалогах
5. (Опционально) Добавление Critic

## 📁 Последние изменения
- `sofia_userbot_pyrogram.py` — синхронизация с v2.2 (signals, WAIT, finance)

## 🔧 Доступные модели OpenAI
- gpt-5.2 — основная модель
- gpt-5.2-pro — для сложных случаев (дорогая: $21/$168 за 1M токенов)
- Параметр reasoning.effort: none/low/medium/high/xhigh
