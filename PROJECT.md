# PROJECT.md — Sofia Bot (Hybrid System)

> Единая точка входа. Этот файл содержит ВСЁ для продолжения работы.
> Последнее обновление: 2026-01-04

---

## CLAUDE: СТАРТ СЕССИИ

### 1. Прочитай HANDOFF (внизу документа)

### 2. Код на сервере
Сервер: ssh -p 2222 root@72.56.64.91
Папка: /opt/sofia-hybrid

Ключевые файлы:
- sofia_hybrid.py — логика: детекторы, decide_action, generate_response
- detectors.py — паттерны из 5,698 сообщений (NEW!)
- sofia_prompt.py — промпт v4.1
- bot_server_hybrid.py — Telegram бот

### 3. Скажи
"Изучил PROJECT.md. [Состояние из HANDOFF]. Что делаем?"

---

## QUICK INFO

| Параметр | Значение |
|----------|----------|
| Проект | Sofia Bot — AI-продажник недвижимости |
| Компания | Oazis Estate |
| Архитектура | Гибридная: код (логика) + LLM (текст) |
| Стек | Python 3.12, python-telegram-bot, OpenAI GPT-5.2 |
| Версия | 2.2 (hybrid + detectors) |
| GitHub | https://github.com/semiekhin/sofia-bot (ветка: hybrid) |
| Сервер | ssh -p 2222 root@72.56.64.91 |
| Бот | @humanAINeural_bot |

---

## АРХИТЕКТУРА

Сообщение клиента -> КОД: analyze_history() -> КОД: decide_action() -> LLM: generate_response() -> Ответ клиенту

### Детекторы (detectors.py)
Извлечены из анализа 5,698 реальных сообщений клиентов:
- IRRITATED_PATTERNS: 40
- SEND_PATTERNS: 38
- CALL_REJECT_PATTERNS: 38
- CALL_AGREE_PATTERNS: 33
- NEUTRAL_PATTERNS: 19
- SHORT_CONFIRM_PATTERNS: 23
- POSITIVE_INTEREST_PATTERNS: 23
- GOODBYE_PATTERNS: 13

### Жёсткие лимиты в decide_action()
- Раздражение -> SEND_MATERIALS, без вопросов
- 2+ раз "скинь" -> SEND_MATERIALS
- 14+ сообщений -> SEND_MATERIALS
- 2+ отказа от созвона -> SEND_MATERIALS
- 4+ сообщений клиента -> PROPOSE_CALL (NEW!)

---

## УПРАВЛЕНИЕ

systemctl status sofia-hybrid
systemctl restart sofia-hybrid
journalctl -u sofia-hybrid -f
python3 -m py_compile /opt/sofia-hybrid/sofia_hybrid.py

---

## МЕТРИКИ (цели)

| Метрика | Текущее | Цель |
|---------|---------|------|
| GOOD rate | 57% | 80% |
| Квалификация | 3.1/10 | 7+ |
| Закрытие | 6.1/10 | 7+ |

---

## HANDOFF

Сессия: 2026-01-03 / 2026-01-04

### Что сделали
1. Анализ 70 диалогов (5,698 сообщений клиентов)
2. Новые детекторы — detectors.py с 8 массивами паттернов из реальных данных
3. PROPOSE_CALL — явное предложение созвона после 4 сообщений клиента
4. Запрет повторов — добавлено в task_prompt: НЕ повторяй вопросы
5. Всё закоммичено в GitHub (ветка hybrid)

### Известные проблемы
- Парсер диалогов (batch_process.py) не работает с форматом [06 октября 2025 г. 15:39]
- Анализ делали через Claude.ai вручную

### Следующие шаги
- Протестировать бота на повторы вопросов
- Проверить что созвон предлагается после 4 сообщений
- Собрать feedback от экспертов

### Файлы анализа (на Mac)
/Users/sergeysemiekhin/Downloads/detector_arrays.py
/Users/sergeysemiekhin/Downloads/final_detectors.json
/Users/sergeysemiekhin/Downloads/ANALYSIS_REPORT.md
/Users/sergeysemiekhin/Downloads/training_analysis.json

---

Последнее обновление: 2026-01-04
