# Atlantis — состояние двух путей привлечения клиента

> **Статус:** справочник для масштабирования на новые сайты. Описывает то, что реально стоит на Атлантисе сейчас, без истории и планов.
> **Дата фиксации:** 28.04.2026.
> **Не входит:** история разработки, отчёты пилотов, голосовой стек, готовый план онбординга нового ЖК (см. `docs/NEW_CLIENT_ONBOARDING.md`).

На Атлантисе работают **два независимых пути** входа клиента в диалог с Sofia. Оба ведут в `@SofiaOazis`, но через **разные** Telegram Business Link, с **разным** prefilled-сообщением и **разной** цепочкой в Bitrix.

---

## Путь A — Тильда-форма «Получить презентацию»

**Что видит клиент.** Лендинги Атлантиса на Тильде с тремя формами: «Презентация в WhatsApp Атлантис», «Планировки Атлантис», «Обратный звонок Атлантис». Клиент оставляет имя и телефон, нажимает submit, попадает на success-страницу с редиректом в Telegram.

**Цепочка.**

1. Тильда webhook → Bitrix создаёт лид с `SOURCE_ID=397` (Тильда/Атлантис), TITLE = название формы, `ASSIGNED_BY_ID` распределяется автоматически.
2. Success-page → редирект на `https://t.me/m/QinKZEsTNmRi`.
3. Клиент попадает в `@SofiaOazis`. Telegram автоматически отправляет prefilled-сообщение: **«Здравствуйте, отправьте презентацию АК «Атлантис»»** (хранится в настройках Telegram Business у `@SofiaOazis`, в коде Sofia не задаётся).
4. `sofia_radist_gateway.py`: `detect_source("Атлантис")` → `source_object="atlantis"`, `is_first_atl=True` → `find_recent_atlantis_lead()` (фильтр `SOURCE_ID=397`, окно 60 сек). Лид найден → bind: `save_radist_lead_id(user_id, lead_id)`, `ASSIGNED_BY_ID=428` (Sofia AI), `original_assigned_by_id` сохраняется в `lead_assigned`, `UF_CRM_TELEGRAM=https://t.me/<username>`.
5. `pipeline.run_pipeline()` форсирует `stage=GREETING`, отправляет greeting со ссылкой на `presentation_url`. Дальше стандартная квалификация → `meeting_agreed`/`dialog_finished` → `finalize_lead()` (stage-guard по `STATUS_ID`) → `set_lead_assigned(24932)` → `start_distribution_bp()` (БП 152).

**Bitrix-итог пути A.** `SOURCE_ID=397`, во время диалога `ASSIGNED=428`, при finalize `ASSIGNED=24932` → БП 152, `original_assigned` сохранён.

---

## Путь B — HTML-виджет «Чат с менеджером»

**Что видит клиент.** На странице сайта в Тильде размещён HTML-блок (T123 или аналог). Десктоп: фиксированный круг 72×72 справа по центру, pulse-анимация, текст «ЧАТ». Мобильный: фиксированная плашка снизу с аватаркой и текстом «София • Эксперт АК Атлантис». Клик → новая вкладка с Telegram.

**Источник.** `widgets/atlantis_chat_widget.html` — 15912 байт, md5 `49b4d1c1d568d9d823dc1dccc4d7b6e4`, коммит `3de1fbf9` от 15.04.2026. Самодостаточный HTML — два `<a href>` + inline `<style>` + base64-аватарка. **Никакого JS, никакого бэкенда, никакой телеметрии.** CSS-классы префиксованы `atl-chat-`, `z-index: 99999`.

**Цепочка.**

1. Клик по виджету → `https://t.me/m/Fiw3ldhkN2My` → `@SofiaOazis`.
2. Telegram отправляет prefilled-сообщение: **«Здравствуйте! Помогите подобрать квартиру в АК "Атлантис".»** Утверждено 15.04.2026, хранится в настройках Telegram Business у `@SofiaOazis`, в коде Sofia не задаётся.
3. `sofia_radist_gateway.py`: `detect_source("Атлантис")` → `source_object="atlantis"`, `is_first_atl=True` → `find_recent_atlantis_lead()`. **Виджет-клиент не создаёт лид с `SOURCE_ID=397` на стороне Тильды**, поэтому в норме функция возвращает `None` → диалог идёт **без bind**, `lead_id` отсутствует. Риск коллизии: если в окно 60 сек случайно попал чужой ATL-лид от Тильда-формы, виджет-клиент привяжется к чужому лиду (прецедент #264710, audit 10.04).
4. После `meeting_agreed`/`dialog_finished` → `create_or_update_lead(lead_id=None, ...)`:
   - если есть телефон → `find_lead_by_phone()` (дедуп) → найден → `update_lead`; не найден → `create_lead`;
   - если телефона нет → `create_lead` сразу.
5. `create_lead()` создаёт новый лид с `SOURCE_ID = os.getenv("BITRIX_SOURCE_ID", "504")` — **не 397**, `ASSIGNED_BY_ID=428`, `TITLE="AI-бот: <user_name>"`, `UF_CRM_TELEGRAM=https://t.me/<username>` (если есть).

**Bitrix-итог пути B.** `SOURCE_ID=504` (default env, **не 397**), `TITLE="AI-бот: <name>"`, дедупликация только по телефону. PDF клиенту не отправляется (это путь B, без презентации).

---

## Где сейчас стоит

⚠️ Виджет (путь B) **не пишет в `web_sessions`** — это чистый `<a href>` без бэкенда. Через таблицу веб-сессий его невозможно отследить. Старый JS-виджет `sofia-widget.html` (с CORS, `/api/session`, localStorage) демонтирован 04.04, документ `docs/WIDGET_INSTALL.md` описывает именно его и устарел.

**Путь A.** Тильда переключена на Business Link `t.me/m/QinKZEsTNmRi` на трёх формах invest-apartmens.online (audit 10.04, SESSION_LOG 15.04). Старая ссылка `t.me/humanAINeural_bot?start=ATL` нигде не используется.

**Путь B.** `widgets/atlantis_chat_widget.html` встроен как HTML-блок в Tilda T123. Точные домены, на которых сейчас стоит виджет, в коде/таблицах не отражены — у виджета нет телеметрии. На момент создания (15.04) предполагалось размещение на лендинге Атлантиса. **Требует уточнения у Сергея.**

Косвенный сигнал по трафику Атлантиса в `web_sessions` (PROD, остаточный/старый трафик старого web-виджета):

| Домен | Сессии всего | За 30 дней |
|-------|--------------|------------|
| `invest-apartmens.online/atlantis` | ~180 (с UTM-вариантами) | 24 |
| `atlantis-invest.ru/` | 7 | 5 |
| `sochiremstroy.tilda.ws/` | 2 | 0 |

Цифры относятся к старому JS-виджету и не отражают трафик нового Telegram-виджета.

---

## Зависимости для подключения нового сайта

Что должно существовать, чтобы новый сайт начал работать по схеме Атлантиса:

1. **Telegram Business Link** в `@SofiaOazis` (или другом аккаунте) с prefilled-сообщением, в котором есть ключевое слово объекта в чистом виде — иначе `detect_source()` не сработает.
2. **Запись в `config/source_objects.py`** со всеми полями: `key`, `name`, `short_name`, `city`, `keywords` (минимум 2-3 формы написания), `context_file`, `presentation_url`, `greeting`, `prompt_addon` (опционально, см. ограничение ниже).
3. **Карточка объекта** `objects/<key>_context.md` (структура — по образцу `objects/atlantis_context.md`).
4. **Презентация** на доступном по HTTPS URL (поле `presentation_url`).
5. **SOURCE_ID в Bitrix** — два варианта: использовать существующий `397` (если поток через Тильда-форму) или завести новый. `find_recent_atlantis_lead()` в `core/bitrix.py:230` сейчас **захардкожен на `BITRIX_ATLANTIS_SOURCE_ID=397`** — для другого ЖК с собственным SOURCE_ID функция работать не будет без правки кода.
6. **`radist_chats` / `radist_messages` / `telegram_leads`** заполняются автоматически при условии, что сообщение приходит через тот же `@SofiaOazis` и подключено через тот же `connection_id` в Radist (Telegram=80200, Max=80024 — `config/radist_config.py`).
7. **Виджет (если нужен)** — копируется с `widgets/atlantis_chat_widget.html`, меняются: оба `href` на новый `t.me/m/<NEW_LINK>`, `aria-label` и текст «АК Атлантис», префикс CSS-классов `atl-chat-` (если на странице может стоять несколько виджетов разных ЖК).

---

## Известные ограничения и тонкости

### 🔴 Atlantis-addon в PROD не работает

**Любые специфичные правила Atlantis из `prompt_addon` в production не работают.** Sofia в PROD-канале (Radist) не получает Atlantis-specific инструкций — работает только общий промпт + RAG. **Это касается обоих путей A и B**, как только клиент попадает к Sofia.

Технически: в PROD `config/source_objects.py` ключа `prompt_addon` нет, в PROD `core/pipeline.py` нет ветки `if obj_config.get("prompt_addon")`. Открытая задача — `ATLANTIS_ADDON_INFRA_PORTBACK` (BACKLOG.md, P0).

### Telegram Business Link `t.me/m/XXX` против `t.me/USER?text=`

Используется **только** Business Link `t.me/m/XXX`. Классическая форма `t.me/<username>?text=<urlencoded>` ломает кириллицу на мобильных клиентах Telegram (зафиксировано в SESSION_LOG 15.04). Prefilled-текст хранится у владельца аккаунта в Telegram Business, не в коде Sofia и не на сайте.

### Виджет — самодостаточный HTML без телеметрии

Кликабельность виджета, конверсию и площадки размещения **невозможно** замерить на стороне Sofia. Единственный косвенный сигнал — рост числа разговоров в `@SofiaOazis` без сопоставимого роста лидов с `SOURCE_ID=397`.

### Коллизия 60-сек окна `find_recent_atlantis_lead()`

Если виджет-клиент пишет первое сообщение в Telegram в те же 60 секунд, что и другой клиент, заполнивший Тильда-форму, — виджет-клиент привяжется к **чужому** лиду Тильды (прецедент #264710, audit 10.04). Окно узкое, но риск ненулевой при росте трафика.

### Виджет-клиент не имеет SOURCE_ID Атлантиса в Bitrix

Лид виджет-клиента создаётся с `SOURCE_ID = BITRIX_SOURCE_ID` (env, default `504`), не `397`. Любая аналитика и BP-фильтры Bitrix, завязанные на `SOURCE_ID=397` для отчётности по Атлантису, **не увидят** виджет-поток.

### Дедупликация только по телефону

`create_or_update_lead()` дедуплицирует через `find_lead_by_phone()`. Если Sofia не извлекла телефон из диалога виджет-клиента — каждый повторный заход того же клиента создаст новый лид. По Telegram-username дедупликации нет (только запись в `UF_CRM_TELEGRAM` существующего лида).

---

## Открытые вопросы (для Сергея, при добавлении нового сайта)

1. **Тот же `@SofiaOazis` для нового ЖК или отдельный аккаунт?** При едином аккаунте все Business Link сходятся на одно лицо в Bitrix-чате. При раздельном — своя инфраструктура Radist на каждый ЖК.
2. **Тот же `SOURCE_ID=397` для нового ЖК или новый?** Влияет на `find_recent_atlantis_lead()` (сейчас захардкожен на 397), на отчётность Bitrix, на маршрутизацию БП.
3. **Тот же PDF-флоу или другой?** Атлантис: `presentation_url` отправляется в первом сообщении. Для нового ЖК может быть видеоэкскурсия, лендинг, callback вместо PDF.
4. **Виджет-клиенты пути B сейчас попадают в Bitrix с `SOURCE_ID=504` (default) — это устраивает, или для нового ЖК нужно завести отдельный SOURCE_ID per-object?**
5. **Где реально стоит `atlantis_chat_widget.html` сейчас?** Без подтверждения площадок виджет нельзя считать «эталоном» для копирования.

---

## Не входит в этот документ

- История разработки виджета и форм — `SESSION_LOG.md` (08.04, 15.04), `docs/AUDIT_ATLANTIS_2026-04-10.md`
- Инструкция онбординга нового ЖК — `docs/NEW_CLIENT_ONBOARDING.md`
- Lead-lifecycle детали — `docs/LEAD_LIFECYCLE.md`
- Голосовой стек — `docs/VOICE_ARCHITECTURE.md`
- Старый JS-виджет и `docs/WIDGET_INSTALL.md` — демонтированная 04.04 инфраструктура
