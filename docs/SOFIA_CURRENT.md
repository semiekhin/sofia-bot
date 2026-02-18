# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 18.02.2026

## ✅ Что сделано

### Сессия 17-18.02.2026
- Полное изучение архитектуры: bot_server.py, web_api.py, sofia_radist_gateway.py, extractor.py, state_manager.py, message_processor.py, rag_module.py, sofia_prompt_v2.py
- Аудит кода — сверка SOFIA_PROJECT_MAP с реальным кодом, выявлены расхождения
- Обновлён SOFIA_PROJECT_MAP.md (Project Knowledge Claude.ai)
- Фикс: "@username" → "ник в Telegram" в web_api.py (синяя ссылка в виджете)
- Актуализация всей документации (CONTEXT, CURRENT, ARCHITECTURE, KNOWLEDGE, TASKS, WIDGET_INSTALL)
- Анализ реальных диалогов: Анна (лид потерян — нет [END]), ночной лид (два дубля в Битрикс)
- Проверка работоспособности всех 3 сервисов
- Подготовлен проектный документ АН Эва (AN_EVA_PROJECT.md) — RIZALTA WebChat на архитектуре Софии

### Сессия 16.02.2026
- web_sessions таблица — SQLite persistence для session_id → user_id
- Стабильные user_id — автоинкремент вместо hash(), seed сдвинут за 9971140
- /api/session/resume — новый эндпоинт, возвращает историю (50 сообщений)
- Виджет v2 — localStorage persistence
- Промпт: сбор контакта — "материалы или созвон?"
- [END] при получении контакта
- extract_telegram_from_history() — @username попадает в лид Bitrix

### Сессия 15.02.2026
- Актуальные цены Атлантиса: от 16.8 млн
- finance_data.json: ключевая ставка ЦБ 15.5%
- Финансовая экспертиза в промпте

### Сессия 13.02.2026
- BUG-005 fix: greeting сохраняется в историю
- Битрикс CRM: автоотправка лида при [END]
- Веб-стратегия: 3 вопроса макс + обязательный сбор контакта

## 🔄 Текущее состояние
- ✅ Web API (sofia-web-api) — работает, порт 8080, обновлённый промпт
- ✅ Telegram бот (@humanAINeural_bot) — работает (с 11.02, старый промпт!)
- ✅ Radist gateway — работает (с 13.02)
- ✅ Битрикс интеграция — webhook рабочий (только web_api.py!)
- ✅ Виджет v2 установлен на всех 3 сайтах
- ✅ Реклама Директ → invest-apartmens.online/atlantis — трафик идёт
- ⚠️ ASSIGNED_BY_ID = 426 (тест), нужно 24932 (прод)
- ⚠️ sofia-gpt не перезапущен — работает на старом промпте
- ⚠️ Лиды из Telegram бота и Max НЕ уходят в Битрикс

## 🔜 Следующие шаги
1. **P0:** Битрикс ASSIGNED_BY_ID: 426 → 24932
2. **P1:** Bitrix в bot_server.py и radist_gateway — лиды теряются
3. **P1:** radist_gateway history limit 8→100
4. **P2:** sofia_prompt_v2 ставка ЦБ ~16% → 15.5%
5. **P2:** BUG-004: EN-layout → Extractor
6. **P2:** Единый message_processor.py (DRY)
7. **Новый проект:** АН Эва — RIZALTA WebChat на архитектуре Софии

## 📁 Последние изменения
- `web_api.py` — "@username" → "ник в Telegram" (строка 373)
- `docs/*` — актуализация всей документации
- `AN_EVA_PROJECT.md` — проектный документ (в Claude.ai outputs)
- `SOFIA_PROJECT_MAP.md` — полная карта проекта (Project Knowledge)
