# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 16.02.2026

## ✅ Что сделано

### Сессия 16.02.2026
- web_sessions таблица — SQLite persistence для session_id → user_id
- Стабильные user_id — автоинкремент вместо hash(), seed сдвинут за 9971140
- `/api/session/resume` — новый эндпоинт, возвращает историю (50 сообщений)
- Виджет v2 — localStorage: сохраняет session_id, при открытии вызывает resume
- Промпт: сбор контакта — "материалы или созвон?" вместо "WhatsApp или Telegram?"
- [END] при получении контакта — номер или @username → немедленно [END]
- extract_telegram_from_history() — @username попадает в лид Bitrix
- SOFIA_PROJECT_MAP.md — полная карта проекта для Project Knowledge

### Сессия 15.02.2026
- Актуальные цены Атлантиса: от 16.8 млн (было ошибочно 5.2 млн!)
- finance_data.json: ключевая ставка ЦБ 15.5% (решение 13.02.2026)
- Финансовая экспертиза в промпте: сравнение недвижимости с депозитом (139% vs 40%)

### Сессия 13.02.2026
- BUG-005 fix: greeting сохраняется в историю сообщений
- Битрикс CRM: автоотправка лида при [END]
- Веб-стратегия: 3 вопроса макс + обязательный сбор контакта перед [END]

## 🔄 Текущее состояние
- ✅ Web API (sofia-web-api) — работает, порт 8080
- ✅ Telegram бот (@humanAINeural_bot) — работает
- ✅ Radist gateway (Max messenger) — работает
- ✅ Битрикс интеграция — webhook рабочий, лиды приходят
- ✅ Сервер готов к localStorage (web_sessions + resume)
- ✅ Виджет v2 протестирован на Тильде
- ✅ Виджет v2 установлен на atlantis-invest.ru, sochiremstroy.tilda.ws, invest-apartmens.online
- ⚠️ ASSIGNED_BY_ID = 426 (тест), нужно 24932 (прод)

## 🔜 Следующие шаги
1. Виджет v2 (localStorage) → заказчику для установки (P0)
2. Таймаут — авто-лид в Битрикс если клиент ушёл (P1)
3. Битрикс ASSIGNED_BY_ID: 426 → 24932 (P0, ждём программиста)
4. ~~WABA~~ — ❌ Отменён
5. BUG-004: EN-layout → Extractor (P2)
6. Единый message_processor.py (P2)

## 📁 Последние изменения
- `web_api.py` — web_sessions, resume endpoint, промпт контактов, extract_telegram
- `sofia-widget-v2.html` — localStorage persistence

### Сессия 17.02.2026
- Фикс: "@username" → "ник в Telegram" в промпте (синяя ссылка в виджете)
- Аудит кода: сверка PROJECT_MAP с реальным кодом
- Выявлены расхождения: Bitrix только в web_api, radist limit=8, ставка ЦБ ~16% в промпте
- Новые задачи из аудита: #8-11 (см. SOFIA_TASKS.md)
- Подготовлен проектный документ АН Эва (RIZALTA WebChat на архитектуре Софии)
