# Задачи Sofia-GPT

📅 Обновлено: 07.03.2026

## ✅ Выполнено
- [x] BUG-005: greeting сохраняется в историю (13.02)
- [x] Битрикс CRM webhook при [END] в web_api (13.02)
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
- [x] Реструктуризация документации 85→29 КБ (18.02)
- [x] Новая стратегия продаж: цены только через контакт (25.02)
- [x] Смена OpenAI API ключа (25.02)
- [x] /api/docs/file — эндпоинт Claude-оркестратора (25.02)
- [x] Source routing: detect_source, deep links (26.02)
- [x] Analyzer: skip_analyzer при source_object (27.02)
- [x] Greeting: 2 сообщения с паузой 5с (27.02)
- [x] "видео-созвон" → "созвон" (27.02)
- [x] "Дверь открыта" после отказа от созвона (27.02)
- [x] atlantis_context.md: инструкции для диалога (27.02)
- [x] Промежуточная страница /go/atlantis.html для iOS (27.02)

## 🔥 Приоритет (следующая сессия)
1. Битрикс веб-виджет: переписка после каждого ответа (add → update)
2. Битрикс в bot_server.py и radist_gateway.py при [END]
3. Observer: раскомментировать .env + добавить в bot_server.py
4. Проверить диалог с Михаилом @das19875 (chat_id=39125360)

## 📛 Бэклог
- Унификация generate_response() — архдолг (3 копии)
- Голосовые звонки (Vapi.ai / Voximplant)
- WhatsApp Business API (WABA)
- Оптимизация скорости (17-24с → цель <12с)
- BUG-004: EN-layout → Extractor
- sofia_prompt_v2 ставка ЦБ ~16% → 15.5%
- Скоринг лидов (predictive analytics)

## 📊 Замер скорости (25.02)
- Extractor: 6.4с, Analyzer: 5.4с, RAG: 2.8с, Generator: 9.2с
- Итого: 17-24с (цель <12с)
