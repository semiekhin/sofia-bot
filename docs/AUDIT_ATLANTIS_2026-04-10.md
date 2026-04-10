# Аудит Атлантиса — 10.04.2026

## TL;DR

1. **Все 3 сервиса работают** (web-api, bot, radist), ошибок за 7 дней нет
2. **196 web-сессий**, из них **180 с Яндекс.Директа** (invest-apartmens.online) — реальный платный трафик, 2-10 сессий/день
3. **КРИТИЧЕСКИЙ БАГ:** PROD `source_objects.py` НЕ содержит `url_patterns` вообще (только `keywords`). Для виджета source_object определяется через `detect_source(text)` по первому сообщению, а не по URL. Поэтому для invest-apartmens.online source_object НЕ определяется автоматически — только если клиент в тексте упомянет "атлантис"
4. **786 лидов с SOURCE_ID=397** в Bitrix за всё время, только **2 зависли** на ASSIGNED=428 (остальные финализированы или обработаны). Основной поток лидов идёт через Тильда→Radist Telegram, ~10 лидов/день
5. **Radist — главный канал** ATL-трафика: 216 TG-сообщений за 30 дней, лиды создаются и финализируются через `find_recent_atlantis_lead()` + БП 152
6. **Prod/Dev расхождения:** bot_server.py — в PROD есть Observer (66 строк), в DEV нет; source_objects.py — в DEV есть `prompt_addon`, в PROD нет
7. **6 дней без виджет-трафика** (05-10.04) — реклама возможно остановлена

---

## 1. Web-виджет

### Работоспособность

| Параметр | Значение |
|----------|----------|
| Сервис | `sofia-web-api.service` — **active (running)** |
| Uptime | с 08.04 18:02 MSK (~2 дня) |
| PID | 2349897, Memory 76.0M |
| Health | `curl localhost:8080/api/health` → `{"status":"ok","version":"2.0.0"}` |
| Ошибки за 7 дней | **0** (grep error/exception/traceback — пусто) |
| Журнал с момента рестарта | Только бот-сканеры (`GET / HTTP/1.0` 404) и health check. **Ноль реальных API-запросов** за 2 дня |

### Где встроен и как

**Nginx:** `api.atlantis-invest.ru` → порт 8080 (HTTPS, Let's Encrypt, HTTP→HTTPS redirect).

```
server_name api.atlantis-invest.ru;
location / { proxy_pass http://127.0.0.1:8080; }
ssl_certificate /etc/letsencrypt/live/api.atlantis-invest.ru/fullchain.pem;
```

Дополнительные location: `/go/` (статика redirect-страниц), `/objects/` (PDF-презентации), `/llm-websocket/` → 8081, `/voice-v2/` → 8082, `/voice-samples/`.

**CORS разрешённые домены:**
- `atlantis-invest.ru` (+ www, http/https)
- `sochiremstroy.tilda.ws`
- `invest-apartmens.online`
- `localhost:3000`, `127.0.0.1:5500`

**Виджет-фронтенд НЕ хостится на сервере** — на сервере нет widget.html/chat_widget.js/css. Код виджета встроен (inline) на внешних сайтах. Сервер предоставляет только API (`/api/chat`, `/api/session`, `/api/session/resume`).

**Redirect-страница:** `/opt/sofia-gpt/static/go/atlantis.html` — не виджет, а redirect в Telegram (@SofiaOazis с текстом "Отправьте презентацию АК Атлантис").

**Где виджет установлен (из web_sessions + docs/WIDGET_INSTALL.md):**

| Домен | Сессий | API URL | Откуда трафик |
|-------|--------|---------|---------------|
| invest-apartmens.online/atlantis | **180** | `https://api.atlantis-invest.ru/api` | Яндекс.Директ (CPC, utm_campaign=703240778) |
| atlantis-invest.ru | 6 | `https://api.atlantis-invest.ru/api` | Прямой |
| sochiremstroy.tilda.ws | 2 | `https://api.atlantis-invest.ru/api` | Прямой |
| (без page_url) | 8 | — | — |

**Трафик по дням (последние 30 дней):** 1-10 сессий/день стабильно. Последняя активность: **04.04.2026**.

> ⚠️ **С 05.04 по 10.04 (6 дней) — ноль новых сессий.** Возможно реклама в Яндекс.Директ остановлена.

### Проблема: source_object для виджета

PROD `config/source_objects.py` **не содержит `url_patterns`**. Определение source_object идёт через `detect_source(text)` — по ключевым словам в первом сообщении пользователя. Для виджета это работает так:

1. Клиент открывает виджет → срабатывает `triggerGreeting()` с пустым `message=""`
2. Пустое сообщение → `detect_source("")` → **source_object=None** → generic greeting
3. Если сайт имеет кнопки типа "Обсудить с Софьей" → первое сообщение "Обсудить Атлантис" → detect_source найдёт "атлантис"

**Результат:** На invest-apartmens.online виджет открывается с generic greeting. НО сайт имеет кнопки с `onclick="openChat('...')"`, которые отправляют pre-filled сообщения — нужно проверить, передаётся ли в этих сообщениях ключевое слово "Атлантис".

**Реальные данные из client_state:**
- 53 пользователя invest-apartmens.online **без** source_object
- 8 пользователей с source_object=atlantis (ключевое слово сработало)
- 55 реальных диалогов (>2 сообщений)
- 8 согласились на встречу (meeting_agreed=1)
- 18 диалогов завершено (dialog_finished=1)

### UI / UX

| Параметр | Статус |
|----------|--------|
| Mobile-friendly | ✅ viewport meta + responsive CSS |
| Resume session | ✅ localStorage + серверный `/api/session/resume` |
| Брендирование | Виджет-код на внешних сайтах (не на сервере) — стиль определяется сайтом |
| Форма контактов | ❌ **Нет** — ни до диалога, ни после |
| Observer | ✅ `OBSERVER_CHAT_ID` в prod .env, уведомления в Telegram группу |

### Интеграция с CRM

**Код:** `web_api.py` — при `dialog_finished=True` вызывается `finalize_lead()` → ASSIGNED=24932 → БП 152.

Отдельно: лид создаётся/обновляется на каждое сообщение если page_url содержит "atlantis":
```python
if req.page_url and "atlantis" in req.page_url.lower():
    await create_or_update_lead(...)
```

| Параметр | Значение |
|----------|----------|
| Условие создания лида | `"atlantis" in page_url.lower()` |
| SOURCE_ID | `BITRIX_SOURCE_ID` из env (по умолчанию `504`), не `BITRIX_ATLANTIS_SOURCE_ID=397` |
| ASSIGNED_BY_ID | `428` (Sofia AI) при создании |
| finalize_lead | Вызывается при `dialog_finished` — ставит ASSIGNED=24932 + БП 152 |
| Таймаут | **Только Timeout-A** (15 мин без ответа). Нет hard-таймаута по бездействию |
| Контакты | Телефон/email **извлекаются из диалога** (не из формы) |

**Факт из web_sessions:** Большинство invest-apartmens.online сессий имеют **пустой bitrix_lead_id**. У нескольких (9971322, 9971318, 9971317, 9971316) — заполнен (263728, 263558, 263546, 263542). Разница — в тех с лидами был реальный диалог, в пустых — только greeting (1 сообщение).

### Последние сессии (таблица)

| # | user_id | Домен | bitrix_lead_id | Дата | Сообщений |
|---|---------|-------|----------------|------|-----------|
| 1 | 9971333 | invest-apartmens.online | — | 04.04 11:30 | 1 |
| 2 | 9971332 | invest-apartmens.online | — | 04.04 07:32 | 1 |
| 3 | 9971331 | invest-apartmens.online | — | 04.04 17:55 | 1 |
| 4 | 9971330 | invest-apartmens.online | — | 04.04 10:05 | 1 |
| 5 | 9971322 | invest-apartmens.online | 263728 | 01.04 08:12 | 3 |
| 6 | 9971318 | invest-apartmens.online | 263558 | 31.03 05:00 | 25 |
| 7 | 9971317 | invest-apartmens.online | 263546 | 30.03 21:26 | 15 |
| 8 | 9971316 | invest-apartmens.online | 263542 | 30.03 21:24 | 13 |
| 9 | 9971314 | invest-apartmens.online | — | 30.03 06:02 | 17 |

Трафик с UTM: `utm_source=yandex&utm_medium=cpc&utm_campaign=703240778`
Ключевые слова: "купить недвижимость с управлением", "инвестировать в недвижимость", "купить квартиру"

### Проблемы виджета

| # | Проблема | Приоритет |
|---|----------|-----------|
| W1 | source_object не определяется по URL — только по тексту сообщения | P1 |
| W2 | 53 из 61 widget-пользователей invest-apartmens без source_object | P1 |
| W3 | Нет формы сбора контактов | P1 |
| W4 | 6 дней без трафика (05-10.04) | Вопрос |

---

## 2. Telegram-бот + Тильда

### Тильда сейчас

**Лендинг:** Точный URL Тильда-лендинга **не найден** в коде. В docs: `URL успеха: https://t.me/humanAINeural_bot?start=ATL`. Redirect настроен на стороне Тильды.

**Формы Тильды → Bitrix:** Формы отправляют webhook напрямую в Bitrix (не через Sofia). Лиды приходят с именем, телефоном, SOURCE_ID=397. Заголовки: "Планировки Атлантис", "Презентация в WhatsApp Атлантис", "Обратный звонок Атлантис".

**Активность Тильды:** Лиды из Тильды создаются **ежедневно** (10+ лидов/день на 10.04). Это основной источник ATL-лидов.

### Бот

| Параметр | Значение |
|----------|----------|
| Сервис | `sofia-gpt.service` — **active (running)** |
| Uptime | с 08.04 18:02 MSK (~2 дня) |
| Memory | 124.9M |

**Лог (последние 3 дня) — ключевые события:**

| Время | Событие |
|-------|---------|
| 07.04 01:33 | Татьяна → /start ATL, Timeout-A (900с), финализация no_response |
| 07.04 02:05 | Roman → /start ATL, диалог, meeting_agreed, финализация |
| 08.04 06:41 | Сергей → /start ATL, привязан к лиду #264672 |
| 08.04 11:11 | SK → /start ATL, привязан к лиду #264710 |
| 08.04 11:39 | Сергей → /start ATL, привязан к **тому же** лиду #264710 (коллизия!) |
| 09.04 17:40 | Алина → /start **без ATL**, generic greeting, 8 сообщений, НЕ в CRM |

**Код /start ATL handler:**
1. Очищает историю, сбрасывает state
2. `detect_source(args[0])` → keyword matching по `["атлантис", "atlantis", "#ATL"]`
3. `find_recent_atlantis_lead()` — 60-секундное окно, SOURCE_ID=397
4. Привязка к `telegram_leads`, ASSIGNED=428, greeting с презентацией PDF
5. Timeout-A (15 мин) → финализация если 0 ответов

**WAIT-логика:** Реализована как `should_skip_response` — подавляет ответ на короткие подтверждения после meeting-маркеров.

**telegram_leads:**

| user_id | bitrix_lead_id | Кто |
|---------|----------------|-----|
| 5958053088 | 264710 | SK |
| 5233154136 | 264384 | Станислава |
| 1473599673 | 264424 | Лилия |
| 691485966 | 264520 | Roman |
| 676529516 | 264516 | Татьяна |
| 512319063 | 264710 | Сергей (коллизия с SK!) |

**Проблема коллизии:** Сергей (512319063) и SK (5958053088) привязаны к одному лиду #264710. SK начал в 11:11, Сергей в 11:39 — вероятно, Сергей повторно отправил Тильда-форму, и `find_recent_atlantis_lead()` нашёл тот же лид.

**Проблема Алина:** /start без ATL-параметра → source_object пуст → generic greeting → 8 сообщений квалификации → НИ ОДНОГО обновления в CRM. Клиент потерян.

### Bitrix ATL-flow (цифры)

| Метрика | Значение |
|---------|----------|
| Всего лидов с SOURCE_ID=397 | **786** |
| Сейчас на ASSIGNED=428 (София AI) | **2** (лиды #264518 и #264372) |
| BITRIX_BP_TEMPLATE_ID | `152` ✅ |
| BITRIX_BP_ASSIGNED_ID | `24932` ✅ |
| Webhook жив | ✅ API отвечает |
| Лидов сегодня (10.04) | **~10** (265060-265164) |

**2 зависших лида:**
- `#264518` (07.04) — "Презентация в WhatsApp Атлантис", Роман, STATUS=17
- `#264372` (06.04) — "Планировки Атлантис", "пывп" (тест?), STATUS=2

### Последние 10 ATL-лидов (Bitrix)

| ID | Дата | ASSIGNED | Статус | Название | Имя |
|----|------|----------|--------|----------|-----|
| 265164 | 10.04 15:59 | 99582 | JUNK | Презентация WhatsApp | Игорь Крицкий |
| 265134 | 10.04 13:15 | 99582 | 18 | Презентация WhatsApp | Татиана |
| 265126 | 10.04 11:41 | 99582 | 18 | Обратный звонок | василий |
| 265110 | 10.04 10:44 | 175846 | 6 | Планировки | С |
| 265108 | 10.04 10:42 | 510 | JUNK | Планировки | Нина |
| 265096 | 10.04 09:45 | 510 | 18 | Планировки | Наталья |
| 265082 | 10.04 08:09 | 84940 | 24 | Презентация WhatsApp | Павел |
| 265070 | 10.04 05:53 | 88688 | 6 | Планировки | Лариса |
| 265062 | 10.04 01:04 | 173310 | JUNK | Планировки | OLEG |
| 265060 | 10.04 00:38 | 105652 | 6 | Планировки | Маша |

**Паттерн:** Лиды из Тильды → с именем/телефоном, распределяются менеджерам (ASSIGNED != 428). Большинство проходят через БП 152 и получают реального менеджера. Система работает.

### Зависшие лиды на ASSIGNED=428 — расследование

#### Лид #264518 — Роман, "Презентация в WhatsApp Атлантис"

| Параметр | Значение |
|----------|----------|
| ID | 264518 |
| DATE_CREATE | 2026-04-07 02:00:32 MSK |
| Висит | **87 часов** (3.6 дня на момент аудита) |
| TITLE | Клиент #Презентация в WhatsApp Атлантис |
| STATUS_ID | 17 (кастомный статус) |
| ASSIGNED_BY_ID | 428 (Sofia AI) |
| NAME | Роман |
| PHONE | +7 (914) 791-22-85 |
| SOURCE_ID | 397 |

**Расследование:**
- В `telegram_leads` — **нет** записи с bitrix_lead_id=264518
- В `radist_chats` — нет записи с этим телефоном
- В `web_sessions` — нет
- Роман (user_id 691485966) привязан к **другому** лиду — #264520 (через `telegram_leads`)
- Лог бота: Роман начал /start ATL в 02:05, `find_recent_atlantis_lead()` нашёл лид **#264520** (не #264518). Диалог прошёл успешно, meeting_agreed, финализация сработала для #264520

**Вывод: АНОМАЛИЯ.** Лид #264518 — это Тильда-форма "Презентация в WhatsApp", созданная за 5 минут до /start ATL Романа. `find_recent_atlantis_lead()` по 60-секундному окну не смог сопоставить этот лид с Романом (прошло >60с). Лид попал на ASSIGNED=428, но клиент ушёл в WhatsApp, а не в бота Софии. **Никто не обработал** — ни София (нет связи), ни менеджер (ASSIGNED=428).

**Действие:** Ручная переназначить с 428 на реального менеджера или на 24932 (БП-распределитель).

#### Лид #264372 — "пывп", "Планировки Атлантис"

| Параметр | Значение |
|----------|----------|
| ID | 264372 |
| DATE_CREATE | 2026-04-06 02:50:27 MSK |
| Висит | **110 часов** (4.6 дня на момент аудита) |
| TITLE | Клиент #Планировки Атлантис |
| STATUS_ID | 2 (NEW) |
| ASSIGNED_BY_ID | 428 (Sofia AI) |
| NAME | пывп |
| PHONE | +7 (999) 999-99-99 |
| SOURCE_ID | 397 |

**Расследование:**
- В `telegram_leads` — **нет** записи с bitrix_lead_id=264372
- В `radist_chats` — нет
- В `web_sessions` — нет
- Телефон +7(999)999-99-99 — **мусор/тест**
- Имя "пывп" — **тест** (клавиатурный мусор)
- В логах бота — **нет** упоминаний 264372

**Вывод: АНОМАЛИЯ (тестовый лид).** Кто-то заполнил Тильда-форму тестовыми данными. Лид создан в Bitrix с ASSIGNED=428, клиент не перешёл в бота. `find_recent_atlantis_lead()` не был вызван (нет /start ATL). Лид завис.

**Действие:** Удалить или перевести в статус JUNK.

#### Общий паттерн зависших лидов

Оба лида — из Тильда-формы, клиент **не перешёл** в Telegram-бота. Sofia получает ASSIGNED только для лидов из Тильды (SOURCE_ID=397), но не имеет канала связи с клиентом, если тот не пришёл в TG/Radist. Это системная проблема: Тильда ставит ASSIGNED=428, но у Софии нет outbound-канала для связи.

**Рекомендация:** Нужен safety-net: если лид на ASSIGNED=428 > N часов и нет связи с клиентом — автоматически переназначить на менеджера (через робот в Bitrix или cron-задачу).

---

## 3. Radist

### Статус

| Параметр | Значение |
|----------|----------|
| Сервис | `sofia-radist.service` — **active (running)** |
| Uptime | с 09.04 06:55 MSK |
| Последняя активность | **10.04 13:00** — Игорь Крицкий через TG Radist |

### Трафик за 30 дней

| Канал | Сообщений |
|-------|-----------|
| Telegram (через Radist) | **216** |
| Max (Авито) | 0 (dormant с февраля) |
| **Итого** | **216** |

Всего в radist_messages: 417 записей. **Telegram через Radist — основной живой канал ATL-трафика.**

Последние Radist-клиенты: Игорь Крицкий АРХИТЕКТОР, Наталья Десяева, OLEG Oleg, Алина, ♤♡◇♧, Юля СММ, Анна Радченко — реальный трафик с именами и телефонами.

### ATL-привязки через Radist

Radist **СОЗДАЁТ лиды в Bitrix** (подтверждено логами). Пример из логов 10.04 15:59:
```
Webhook received → object "АК Атлантис"
find_recent_atlantis_lead → лид #265164
ASSIGNED_BY_ID=428 → greeting с презентацией
900s timeout → финализация → ASSIGNED=24932, BP 152 started
```

Это работающий production flow: Тильда форма → Bitrix лид → Radist Telegram → Sofia → финализация → БП 152.

### Dedup verification

Коммит `7f4c96a2` — деdup реализован архитектурно: `save_message()` и `notify_observer()` вынесены в `save_user_and_notify()` closure, вызываемую один раз через `send_callback`. Prod и dev идентичны.

---

## 4. Контент и данные

### objects/atlantis_context.md

| Параметр | Значение |
|----------|----------|
| Размер | 3639 байт |
| Последнее изменение | 27.02.2026 |
| Содержание | **Cosmos Crimea Atlantis Therms & Resort** |

**Это курорт в Крыму (Новофёдоровка)**, не Сочи! Объект:
- Всесезонный wellness-курорт с термальной скважиной 48°C
- Управление: Cosmos Hotel Group
- 1170 лотов, до 8 этажей
- Цены: студии от **16.8 млн**, 1-спальни от 20.7 млн, 2-спальни от 22.8 млн, премиум до 146.4 млн
- ФЗ-214, эскроу Сбербанк, рассрочка + ипотека
- Инвестмодель: доходность 5.2-17.6%, ADR 15-27к/ночь
- Презентация: `https://api.atlantis-invest.ru/objects/atlantis_presentation.pdf`

> ⚠️ **Цены от февраля 2026 — требуется проверка актуальности.**

### RAG

ChromaDB общая база. **Нет** отдельных atlantis-тегированных примеров. Однако в `rag_training_data.json` есть 15+ Atlantis-упоминаний: objection handling ("Атлантис не предлагать", "Космос отельер жадный 50%"), ценовые примеры ("17.2 млн с РМТ", "минимальный лот 14530000"), примеры дисквалификации.

### Промпты

`config/source_objects.py` (PROD) — конфигурация Атлантиса:
```python
"atlantis": {
    "key": "atlantis",
    "name": "Cosmos Crimea Atlantis Therms & Resort",
    "short_name": "АК Атлантис",
    "city": "Крым, Новофёдоровка",
    "keywords": ["атлантис", "atlantis", "#ATL"],
    "context_file": "objects/atlantis_context.md",
    "presentation_url": "https://api.atlantis-invest.ru/objects/atlantis_presentation.pdf",
    "greeting": "Рада, что заинтересовались Атлантисом! ...",
    # НЕТ url_patterns, НЕТ prompt_addon в PROD!
}
```

**Проблема:** `prompt_addon` ("НЕ запрашивай контактные данные") **есть только в DEV**, в PROD отсутствует.

---

## 5. Известные проблемы

### Из BACKLOG (проверка статуса)

| Проблема | Статус | Комментарий |
|----------|--------|-------------|
| Лиды не доходящие до бота (Тильда→TG) | **Работает** | Основной flow через Radist TG, ~10 лидов/день. Прямой redirect в бот тоже работает (6 привязок) |
| Web widget таймаут | **Частично** | finalize_lead вызывается при dialog_finished. Нет hard-таймаута по бездействию |
| Hardcoded SOURCE_ID=397 | **Актуально** | `find_recent_atlantis_lead()` — хардкод, не из env |
| Radist → Bitrix | **РАБОТАЕТ** | Интеграция есть и активна (подтверждено логами 10.04) |
| 20-мин safety net робот | **Неизвестно** | Не виден через API/код |

### Новые проблемы (выявлены аудитом)

| # | Проблема | Приоритет |
|---|----------|-----------|
| **N1** | PROD source_objects.py без `prompt_addon` — расхождение с DEV | P1 |
| **N2** | PROD bot_server.py имеет Observer (~66 строк), DEV — нет. Код дрейфует | P1 |
| **N3** | 53/61 widget-пользователей без source_object (generic greeting) | P1 |
| **N4** | Коллизия лидов (SK + Сергей → один лид #264710) — окно 60с слишком широкое | P2 |
| **N5** | /start без ATL → клиент (Алина) полностью потерян для CRM | P1 |
| **N6** | Max-канал Radist dormant (0 сообщений за 30 дней) | Инфо |
| **N7** | 6 дней без widget-трафика (05-10.04) | Вопрос |
| **N8** | Цены в atlantis_context.md от февраля 2026 | P2 |
| **N9** | `/api/docs/file` endpoint в PROD — позволяет читать .py/.md файлы сервера | P2 (security) |

---

## 6. Git состояние

### Последние коммиты по Атлантис-файлам (DEV)

```
a0aea746 docs: CLAUDE.md — v3 locked, docs index, Groq key description
52d47bb2 docs: session 10.04 close — backlog, session log, CLAUDE.md updated
3892c648 fix(radist): dedup incoming messages by radist_message_id
b5e21f33 fix(bot): Tilda redirect now points to prod bot
a3f21c55 feat(web): widget + atlantis context + source_objects
9c47d882 feat(bitrix): ATL lead flow with find_recent_atlantis_lead
7f38a1cc feat(radist): gateway v2 with process_with_queue
7f4c96a2 fix(radist): eliminate cumulative message duplicates
12e4bf18 feat: Bitrix CRM integration for Radist channel
14e56c3a feat: Атлантис prompt_addon, meeting_agreed финализация, таймауты
```

### Diff PROD vs DEV

| Файл | Различия |
|------|----------|
| **web_api.py** | **Идентичны** |
| **bot_server.py** | **РАСХОЖДЕНИЕ:** PROD +66 строк Observer (get_or_create_bot_topic, notify_bot_observer, observer_topics_bot таблица). DEV этого кода нет |
| **core/bitrix.py** | **Идентичны** |
| **sofia_radist_gateway.py** | **Идентичны** |
| **config/source_objects.py** | **РАСХОЖДЕНИЕ:** DEV имеет `prompt_addon` поле, PROD — нет |

### Расхождения — анализ и риски

#### bot_server.py: PROD новее (Observer)

**PROD** содержит коммит `49659ffb` (08.04.2026, "feat(bitrix): integration in Telegram bot channel"), которого **нет в DEV**. Этот коммит добавил:

**Что в PROD есть, а в DEV нет (87 строк):**
```diff
# Строка 27: import logging + basicConfig (6 строк)
# Строка 72: OBSERVER_CHAT_ID default "0" (в DEV: "-5206139579")
# Строки 339-345: CREATE TABLE observer_topics_bot
# Строки 896-961: get_or_create_bot_topic() + notify_bot_observer() (66 строк)
# Строки 979-981: вызов Observer для входящего сообщения
# Строки 1035-1037: вызов Observer для ответа Софии
```

**Что в DEV есть, а в PROD нет:**
DEV bot_server.py последний коммит `73b14516` (04.04) — более ранний по содержимому Bitrix-логики, но другая ветка развития. DEV не имеет Observer, но имеет свою версию Bitrix-интеграции (коммиты `7ae37c0a`, `c1987ff5`, `73b14516`).

**Вывод: РАЗОШЛИСЬ.** PROD и DEV развивались параллельно. PROD получил Observer через прямой коммит на сервере (коммит 49659ffb от Sergey, 08.04). DEV получил другие Bitrix-фиксы (manager_active, BP 152). Файлы не мержились.

| Критерий | PROD | DEV |
|----------|------|-----|
| Последний коммит bot_server.py | 49659ffb (08.04) | 73b14516 (04.04) |
| Observer | ✅ Работает | ❌ Нет |
| Bitrix BP 152 flow | ✅ (из 49659ffb) | ✅ (из c1987ff5) |
| manager_active fix | ? | ✅ (из 73b14516) |
| logging.basicConfig | ✅ | ❌ |

**Риск деплоя DEV → PROD:** Потеря Observer (66 строк) + потеря logging config. Telegram-бот перестанет транслировать диалоги в Observer-группу. Также `OBSERVER_CHAT_ID` default сменится на `-5206139579` (dev группа).

**Риск деплоя PROD → DEV:** Потеря manager_active fix (73b14516). Возможно потеря мелких Bitrix-фиксов.

**Решение:** Требуется ручной merge. Взять PROD как базу, добавить DEV-фиксы (manager_active). Или наоборот — добавить Observer-код в DEV.

#### config/source_objects.py: DEV новее (prompt_addon)

**Diff (4 строки):**
```diff
# DEV добавляет:
+  "prompt_addon": "Контакт клиента уже получен через форму на сайте.
+   НЕ запрашивай телефон, email или другие контактные данные.
+   После квалификации сразу предлагай удобное время для созвона с экспертом.",
# + форматирование black (кавычки '' → "", переносы строк)
```

**Git log:** Оба имеют одинаковые 2 коммита (`db30accb`, `197cb36b`). `prompt_addon` добавлен в DEV **вне git** (не закоммичен) — вероятно через Claude Code / ручное редактирование.

**Вывод: DEV новее.** prompt_addon нужно перенести в PROD (и закоммитить).

**Риск деплоя DEV → PROD:** Минимальный. Добавится `prompt_addon` (София перестанет спрашивать контакты у ATL-клиентов через бота) + black-форматирование. Функциональность не ломается.

**Риск деплоя PROD → DEV:** Потеря `prompt_addon`. София начнёт спрашивать контакты у ATL-клиентов, которые уже оставили телефон через Тильда-форму — раздражающий UX.

**Примечание:** Сам `prompt_addon` спорный для web-виджета — виджет-клиенты контакты НЕ оставляли (нет формы). Нужно канало-зависимое поведение.

---

## Рекомендации

### P0 — Нет

Критических блокеров нет. Основной ATL-flow (Тильда → Bitrix → Radist TG → София → финализация → БП 152) **работает исправно**, ~10 лидов/день.

### P1 — Важные

1. **Синхронизировать prod/dev** — перенести Observer из PROD bot_server.py в DEV (или наоборот, убрать из prod). Перенести `prompt_addon` из DEV source_objects.py в PROD
2. **Исправить source_object detection для виджета** — добавить URL-based matching (сейчас только keyword в тексте). 53 из 61 widget-клиентов не получают контекст Атлантиса
3. **/start без ATL** — клиенты типа Алины (приходят по ссылке без параметра) полностью теряются. Нужен fallback: если user пришёл в бота из Radist-привязки, подтягивать source_object
4. **Форма сбора контактов в виджете** — widget-лиды создаются без имени/телефона
5. **2 зависших лида** на ASSIGNED=428 (#264518, #264372) — ручная очистка или safety-net

### P2 — Улучшения

6. **Проверить актуальность atlantis_context.md** — цены от февраля 2026
7. **Hardcoded SOURCE_ID=397** → вынести в env
8. **`/api/docs/file` в PROD** — endpoint позволяет читать исходный код, потенциальная утечка
9. **Max-канал dormant** — выяснить, нужен ли ещё
10. **Коллизия лидов** (60с окно) — теоретическая проблема, пока 1 случай

### Вопросы для Сергея

1. Реклама в Яндекс.Директ на invest-apartmens.online — остановлена с 05.04?
2. 20-мин safety-net робот в Bitrix — настроен?
3. Цены в atlantis_context.md актуальны?
4. Observer в PROD bot_server.py — это deliberate? Нужно ли перенести в DEV?
