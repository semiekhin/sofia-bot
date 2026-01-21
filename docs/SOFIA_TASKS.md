# Задачи Sofia-GPT

📅 **Обновлено:** 21.01.2026

## ✅ Выполнено

### 21.01.2026 — Daemon + sofia_start.sh
- [x] Daemon-режим userbot (`--daemon` флаг)
- [x] Скрипт sofia_start.sh для быстрого старта диалога
- [x] Правила форматирования (без markdown в Telegram)

### 20.01.2026 — "Живая София" v2.1
- [x] Унификация промпта bot_server.py с userbot
- [x] Ситуативный контекст (situation + optional_hints)
- [x] Раздел "ТВОЯ ЛИЧНОСТЬ" в промпте
- [x] Расширены паттерны extractor для strategy ("сдавать" → rental)
- [x] Финансовый модуль v1.1 — минимальная интеграция
- [x] Трансляция диалогов userbot в группу наблюдателей

### 18.01.2026
- [x] Userbot v2.0 — восстановлен и улучшен
- [x] Связанное извлечение goal + strategy
- [x] ACTION_TO_RAG_STAGE маппинг

### 17.01.2026
- [x] Sofia-GPT v2.0 — две ветки квалификации
- [x] Два предложения созвона
- [x] Счётчик отказов
- [x] Фикс slot_attempts (payment → payment_type)

## 🟡 В работе

### systemd сервис для userbot
- [x] Daemon-режим в коде (main_daemon)
- [ ] Создать /etc/systemd/system/sofia-userbot.service
- [ ] Автозапуск при перезагрузке

## 🔵 Запланировано: Умная София v3.0

### ФАЗА 1: Латентные метрики (v2.2) — 2-3 дня
- [ ] Extractor: секция ЭМОЦИОНАЛЬНЫЕ СИГНАЛЫ + калибровка
- [ ] Extractor: парсинг signals (friction, call_readiness, engagement, urgency)
- [ ] State Manager: новые поля в БД
- [ ] Planner: условия по метрикам
- [ ] Generator: блок СИТУАЦИЯ в промпте
- [ ] Тестирование на реальных диалогах

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

## 🔴 Известные проблемы

### Extractor: комбинированные сообщения
**Проблема:** "15. какая доходность?" → budget: null
**Статус:** Низкий приоритет (редкий кейс)
