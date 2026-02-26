# Задачи Sofia-GPT

📅 Обновлено: 26.02.2026

## ✅ Выполнено
- [x] BUG-005: greeting сохраняется в историю (13.02)
- [x] Битрикс CRM webhook при [END] (13.02)
- [x] Веб-стратегия: 3 вопроса + контакт + вовлечение (13.02)
- [x] Актуальные цены Атлантиса в промпте (15.02)
- [x] finance_data.json — ЦБ 15.5% (15.02)
- [x] Финансовая экспертиза в промпте (15.02)
- [x] Виджет на invest-apartmens.online/atlantis (15.02)
- [x] Web API + observer для web-канала
- [x] CORS для atlantis-invest.ru, sochiremstroy.tilda.ws, invest-apartmens.online
- [x] Dynamic greeting по page_url
- [x] Виджет v2 (localStorage) установлен на всех 3 сайтах (16.02)
- [x] web_sessions + /api/session/resume (16.02)
- [x] "@username" → "ник в Telegram" в промпте (17.02)
- [x] Реструктуризация документации 85→29 КБ (18.02)
- [x] Новая стратегия продаж: цены только через контакт (25.02)
- [x] Проценты вместо рублей в промпте (25.02)
- [x] Выбор Telegram/звонок при сборе контакта (25.02)
- [x] @username убран из промпта повторно (25.02)
- [x] Смена OpenAI API ключа (25.02)
- [x] sofia-bot.service отключён, дубль устранён (25.02)
- [x] /api/docs/file — эндпоинт Claude-оркестратора (25.02)
- [x] Source routing: распознавание объекта по ключевым словам (26.02)
- [x] Карточка объекта АК Атлантис + PDF презентация на сервере (26.02)
- [x] Бот: /start ATL → автоприветствие + презентация (26.02)
- [x] Radist: detect_source() + инъекция контекста в промпт (26.02)
- [x] Поле source_object в client_state (26.02)
- [x] Nginx /objects/ для статических файлов (26.02)
- [x] Убран мёртвый импорт sofia_prompt v1 из radist_gateway (26.02)
- [x] Проверено: оба канала на промпте v2 (26.02)

## 🔥 Приоритет (следующая сессия)
1. **P1:** Analyzer — при source_object первое сообщение = GREETING, не OBJECTION
2. **P1:** Bitrix в bot_server.py — лиды теряются
3. Битрикс ASSIGNED_BY_ID: 426 → 24932 (ждём программиста)

## 🔴 Выявлено аудитом + сессии
- [ ] **P1:** Bitrix в bot_server.py и radist_gateway — лиды теряются
- [ ] **P1:** Analyzer stage=OBJECTION вместо GREETING при source_object (влияет на RAG)
- [ ] **P2:** sofia_prompt_v2 ставка ЦБ ~16% → 15.5%
- [ ] **P2:** Оптимизация скорости: стриминг Generator, облегчение Analyzer (17-24с → цель <12с)
- [ ] **P2:** BUG-004: EN-layout → Extractor
- [ ] **P3:** Единый message_processor.py (DRY — process_incoming_message мёртвый код)
- [ ] **P3:** Мёртвый код process_incoming_message в radist_gateway (не вызывается)

## 📛 Бэклог
- Голосовые звонки (Vapi.ai / Voximplant)
- Расширение source routing на новые объекты/сайты
- Cold lead актуализация (стратегия реактивации)
- WABA замена Max (360Dialog)

## 📊 Deep links для сайтов
- Бот: https://t.me/humanAINeural_bot?start=ATL (автоотправка)
- Radist: https://t.me/SofiaOazis?text=Добрый+день!+Отправьте,+пожалуйста,+презентацию+АК+%22Атлантис%22
- Презентация: https://api.atlantis-invest.ru/objects/atlantis_presentation.pdf
