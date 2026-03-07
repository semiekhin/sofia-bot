# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 07.03.2026

## ✅ Что сделано

### Сессия 27.02-07.03.2026
- Source routing: Analyzer force GREETING при source_object + первые сообщения (skip_analyzer)
- Подсказка Analyzer про source routing для дальнейших сообщений (>2 msg)
- Greeting в боте разделён на 2 сообщения: приветствие+PDF (5с пауза) → квалификационный вопрос
- Greeting текст обновлён: "Спрашивайте что угодно — а я задам пару вопросов, чтобы подобрать лучший вариант)"
- "видео-созвон" → "созвон" в sofia_prompt_v2.py
- "Дверь открыта": после отказа от созвона → "если определитесь со временем — напишите мне"
- atlantis_context.md: инструкции для диалога (держись Атлантиса, расширяй горизонт по ситуации)
- Промежуточная страница /go/atlantis.html для корректного deep link на iOS
- Nginx: location /go/ для статики
- Observer отключён на время тестирования (OBSERVER_CHAT_ID закомментирован в .env)
- Outreach Михаилу (@das19875): warm → ответил "давайте завтра" → follow-up через 2 дня

## 🔄 Текущее состояние
- ✅ Web API (sofia-web-api) — работает, Bitrix подключён
- ✅ Telegram бот (@humanAINeural_bot) — работает, source routing, 2 сообщения greeting
- ✅ Radist gateway (@SofiaOazis, +79181038493, connection 80200) — работает, source routing
- ✅ /go/atlantis.html — промежуточная страница для iOS deep links
- ✅ sofia_outreach.sh — рабочий для Telegram через Radist
- ⚠️ Observer ОТКЛЮЧЁН (раскомментировать OBSERVER_CHAT_ID в .env + добавить observer в bot_server.py)
- ⚠️ ASSIGNED_BY_ID = 426 (тест), нужно 24932 (прод)
- ⚠️ Bitrix НЕ подключён в bot_server.py и radist_gateway.py
- ⚠️ Нужно: отправка переписки из веб-виджета в Битрикс после каждого ответа Софии
- 📞 Активный диалог: Михаил @das19875 (chat_id=39125360) — ждём ответ на follow-up

## 🔜 Следующие шаги
1. **P1:** Битрикс веб-виджет: переписка после каждого ответа (crm.lead.add → crm.lead.update)
2. **P1:** Битрикс в bot_server.py и radist_gateway.py при [END]
3. **P1:** Observer: раскомментировать .env + добавить в bot_server.py
4. **P2:** sofia_prompt_v2 ставка ЦБ ~16% → 15.5%
5. **P2:** Оптимизация скорости (17-24с → цель <12с)
6. **P2:** BUG-004: EN-раскладка

## 📁 Последние изменения
- `bot_server.py` — skip_analyzer, send_greeting (2 сообщения), source routing greeting
- `sofia_prompt_v2.py` — "видео-созвон" → "созвон", дверь открыта после отказа
- `objects/atlantis_context.md` — инструкции для диалога
- `config/source_objects.py` — обновлён greeting текст
- `static/go/atlantis.html` — промежуточная страница deep link
- `/etc/nginx/sites-available/sofia-api` — location /go/
- `.env` — OBSERVER_CHAT_ID закомментирован
