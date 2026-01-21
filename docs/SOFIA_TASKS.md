# Задачи Sofia-GPT

📅 **Обновлено:** 21.01.2026

## ✅ Выполнено

### 21.01.2026 — Фаза 1: Латентные метрики (v2.2)
- [x] Extractor: секция ЭМОЦИОНАЛЬНЫЕ СИГНАЛЫ + калибровка
- [x] Extractor: парсинг signals (friction, call_readiness, engagement, urgency)
- [x] State Manager: новые поля в БД
- [x] Planner: Action.EASE_PRESSURE (friction > 0.7)
- [x] Planner: проверка signals перед PROPOSE_MEETING_1
- [x] Generator: блок СИТУАЦИЯ с метриками
- [x] Тестирование на примерах

### 21.01.2026 — Daemon + sofia_start.sh
- [x] Daemon-режим userbot
- [x] Скрипт sofia_start.sh
- [x] Правила форматирования (без markdown)

### Ранее
- [x] Sofia-GPT v2.0 — две ветки квалификации
- [x] Два предложения созвона
- [x] Финансовый модуль v1.1

## 🔵 Запланировано: Умная София v3.0

### ФАЗА 2: Rolling Summary + Event Log (v2.3) — 3-5 дней
- [ ] generate_summary() каждые 5-6 сообщений
- [ ] Event Log: call_refused, question_asked, mood_change
- [ ] Planner использует event history

### ФАЗА 3: RAG по ситуации + LLM-планер (v3.0) — 5-7 дней
- [ ] RAG: метаданные (objection_type, friction_level, outcome)
- [ ] RAG: поиск успешных траекторий
- [ ] LLM-планер: allowed_actions -> LLM выбирает лучшее

### Инфраструктура
- [ ] systemd сервис для userbot daemon
- [ ] HTTP API для лидов
