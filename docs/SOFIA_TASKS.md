# Задачи Sofia-GPT

📅 **Обновлено:** 22.01.2026

## ✅ Выполнено

### 22.01.2026 — Синхронизация userbot с v2.2
- [x] ease_pressure в ACTION_TO_RAG_STAGE
- [x] Сохранение signals (friction, call_readiness, engagement, urgency)
- [x] Обработка WAIT (return None)
- [x] Finance calculator интеграция
- [x] Проверка доступа к моделям (gpt-5.2, gpt-5.2-pro)

### 21.01.2026 — Фаза 1 "Умная София"
- [x] Extractor: секция ЭМОЦИОНАЛЬНЫЕ СИГНАЛЫ в промпте
- [x] Extractor: парсинг signals (friction, call_readiness, engagement, urgency)
- [x] State Manager: 4 новых поля в ClientState и БД
- [x] Planner: Action.EASE_PRESSURE (при friction > 0.7)
- [x] Planner: проверка signals перед PROPOSE_MEETING_1
- [x] Generator: отображение signals и tone_hints в СИТУАЦИЯ

### 20.01.2026 — "Живая София" v2.1
- [x] Унификация промпта bot_server.py с userbot
- [x] Ситуативный контекст (situation + optional_hints)
- [x] Раздел "ТВОЯ ЛИЧНОСТЬ" в промпте
- [x] Финансовый модуль v1.1

## 🔵 Запланировано: Фаза 3 — LLM-Planner (v3.0)

### Архитектура
- [ ] `get_allowed_actions()` в planner.py — формирует список допустимых действий
- [ ] `llm_planner.py` (новый) — LLM выбирает лучший action из allowed
- [ ] Интеграция в bot_server.py с флагом USE_LLM_PLANNER
- [ ] Fallback на детерминированный planner при ошибке LLM

### Конфигурация моделей
- [ ] Extractor: gpt-5.2 (effort: none)
- [ ] LLM-Planner: gpt-5.2 (effort: xhigh)
- [ ] Generator: gpt-5.2 (effort: medium)
- [ ] Critic (опционально): gpt-5.2 (effort: high)

### Безопасный rollout
- [ ] Тестирование на одном user_id
- [ ] A/B тест: 10% → 50% → 100%
- [ ] Логирование решений LLM-Planner

## 🟡 Опционально

### Critic (проверка перед отправкой)
- [ ] `critic.py` — проверяет ответ Generator
- [ ] Лимит: максимум 2 перегенерации
- [ ] Эскалация на gpt-5.2-pro для сложных кейсов

### Rolling Summary + Event Log (отложено)
- [ ] generate_summary() каждые 5-6 сообщений
- [ ] Event Log: call_refused, question_asked, mood_change
- Решено: пока не нужно, GPT-5.2 хорошо работает с полной историей

## 🔴 Известные проблемы

### Extractor: комбинированные сообщения
**Проблема:** "15. какая доходность?" → budget: null
**Статус:** Низкий приоритет (редкий кейс)
