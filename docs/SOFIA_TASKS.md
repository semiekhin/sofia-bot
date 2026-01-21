# Задачи Sofia-GPT

📅 **Обновлено:** 22.01.2026

## ✅ Выполнено

### 22.01.2026 (ночь) — LLM-Planner v3.0
- [x] `get_allowed_actions()` в planner.py
- [x] Новый модуль `llm_planner.py`
- [x] Интеграция в bot_server.py с флагом USE_LLM_PLANNER
- [x] Синхронизация userbot с v3.0
- [x] Включен на проде
- [x] Документация обновлена

### 22.01.2026 (ночь) — Синхронизация userbot с v2.2
- [x] Добавлен ease_pressure в ACTION_TO_RAG_STAGE
- [x] Добавлено сохранение signals (friction, call_readiness, engagement, urgency)
- [x] Добавлена обработка WAIT
- [x] Добавлен finance_calculator

### 21.01.2026 — Daemon + sofia_start.sh
- [x] Daemon-режим userbot (`--daemon` флаг)
- [x] Скрипт sofia_start.sh для быстрого старта диалога
- [x] Правила форматирования (без markdown в Telegram)

### 20.01.2026 — "Живая София" v2.1
- [x] Унификация промпта bot_server.py с userbot
- [x] Ситуативный контекст (situation + optional_hints)
- [x] Раздел "ТВОЯ ЛИЧНОСТЬ" в промпте
- [x] Расширены паттерны extractor для strategy
- [x] Финансовый модуль v1.1

### 17-18.01.2026
- [x] Sofia-GPT v2.0 — две ветки квалификации
- [x] Userbot v2.0 — восстановлен и улучшен
- [x] Фикс slot_attempts (payment → payment_type)

## 🟡 В работе

Нет активных задач — v3.0 развёрнут.

## 🔵 Запланировано

### Мониторинг v3.0
- [ ] Анализ логов LLM-Planner на реальных диалогах
- [ ] Сравнение конверсии: v2.2 vs v3.0
- [ ] Тюнинг промпта LLM-Planner если нужно

### Опционально: Critic
- [ ] Проверка ответа перед отправкой
- [ ] Защита от галлюцинаций

### Инфраструктура
- [ ] HTTP API для лидов

## 🔴 Известные проблемы

### Extractor: комбинированные сообщения
**Проблема:** "15. какая доходность?" → budget: null
**Статус:** Низкий приоритет (редкий кейс)
