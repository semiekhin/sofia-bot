# Текущий статус Sofia-GPT

📅 **Последняя сессия:** 26.02.2026

## ✅ Что сделано

### Сессия 26.02.2026 — Source routing + презентация с сайтов
- Source routing: распознавание объекта по ключевым словам (config/source_objects.py)
- Карточка объекта АК Атлантис (objects/atlantis_context.md) — цены, инфраструктура, доходность
- PDF презентация на сервере: https://api.atlantis-invest.ru/objects/atlantis_presentation.pdf
- Nginx location /objects/ для статических файлов
- Поле source_object в client_state (БД + dataclass + CRUD)
- Бот @humanAINeural_bot: /start ATL → автоприветствие + презентация ✅ РАБОТАЕТ
- Radist @SofiaOazis: detect_source() в process_message_wrapper → контекст в промпт ✅ РАБОТАЕТ
- Инъекция контекста объекта в generate_response (оба канала)
- Убран мёртвый импорт sofia_prompt v1 из radist_gateway
- Проверено: оба канала (бот + Radist) используют sofia_prompt_v2

### Предыдущие сессии
- 25.02: Стратегия цены через контакт, смена API ключа, /api/docs/file, замер скорости
- 17-18.02: Аудит, фикс @username, реструктуризация документации

## 🔄 Текущее состояние
- ✅ Web API (sofia-web-api) — работает, порт 8080, Bitrix подключён
- ✅ Telegram бот (@humanAINeural_bot) — работает, /start ATL → source routing
- ✅ Radist gateway (@SofiaOazis) — работает, source routing по ключевым словам
- ✅ Source routing — распознаёт объекты и инжектит контекст в промпт
- ✅ PDF презентация доступна по URL
- ✅ Оба канала на промпте v2
- ⚠️ Analyzer ставит stage=OBJECTION вместо GREETING для первого сообщения с сайта
- ⚠️ ASSIGNED_BY_ID = 426 (тест), нужно 24932 (прод)
- ⚠️ Лиды из Telegram бота и Radist НЕ уходят в Битрикс
- ⚠️ Подписка Radist продлена (Telegram), Max забанен

## 🔜 Следующие шаги
1. **P1:** Analyzer — при source_object первое сообщение = GREETING, не OBJECTION (влияет на RAG)
2. **P1:** Bitrix в bot_server.py — лиды теряются
3. **P2:** sofia_prompt_v2 ставка ЦБ ~16% → 15.5%
4. **P2:** Оптимизация скорости (17-24с → цель <12с)
5. **P2:** BUG-004: EN-layout → Extractor
6. **P3:** Единый message_processor.py (DRY — process_incoming_message не используется)

## 📁 Последние изменения
- `config/source_objects.py` — НОВЫЙ: конфиг объектов с detect_source()
- `objects/atlantis_context.md` — НОВЫЙ: карточка Атлантиса для промпта
- `objects/atlantis_presentation.pdf` — НОВЫЙ: PDF презентация
- `state_manager.py` — поле source_object в dataclass + БД CRUD
- `bot_server.py` — /start ATL → source routing + greeting с презентацией + инъекция контекста
- `sofia_radist_gateway.py` — detect_source в process_message_wrapper + инъекция контекста + убран мёртвый импорт v1
- `/etc/nginx/sites-available/sofia-api` — location /objects/ для статики
