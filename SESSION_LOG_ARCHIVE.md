# SESSION_LOG_ARCHIVE — Архив сессий

> 📁 **Это архив старых сессий** SESSION_LOG.md, выгруженный 2026-04-29 (последнее обновление 2026-05-26 — ротация 05.05.2026 ATLANTIS-виджет после добавления 26.05.2026 ANSWERING_MODE_v1).
> Активный лог последних 5 сессий: [SESSION_LOG.md](SESSION_LOG.md).
> Записи в архиве сохранены as-is, в исходном порядке (свежее сверху).

## 05.05.2026 — ATLANTIS-виджет: read-only аудит первого касания + ATLANTIS_ADDON_INFRA_PORTBACK + новый prompt_addon

### TL;DR

Длинная сессия закрыла давний P0 `ATLANTIS_ADDON_INFRA_PORTBACK` (висел в backlog с 15.04, отложен 28-29.04 при RIZALTA-деплое). Структурно: (1) read-only аудит «как именно виджет-Sofia ломает логику Атлантиса» — реконструкция первого касания виджет-клиента vs Тильда-клиент vs `/start` без объекта, 8 точек расхождения с file:line; (2) портбэк ветки `if obj_config.get("prompt_addon"): system_prompt += ...` из DEV `core/pipeline.py:267-268` в PROD `core/pipeline.py:206-207`; (3) полная переработка текста `prompt_addon` в `config/source_objects.py` обоих репо — с «контакт уже получен через форму» (фактически ложно для виджет-клиента) на новый текст 3464 байт под виджет+Тильда одновременно. PROD-коммит `f3213406` без push (by-design), DEV-коммит `25d81351` запушен. 5 рестартов (sofia-radist + sofia-web-api + sofia-gpt + sofia-radist-dev + sofia-web-api-dev) — 0 ERROR/Traceback в журналах за 2 минуты после.

### Хронология коммитов

| # | Репо | SHA | Subject |
|--:|------|------|---------|
| 1 | PROD | `f3213406` | feat(atlantis): rewrite prompt_addon for widget-driven qualification flow (без push by-design) |
| 2 | DEV | `25d81351` | feat(atlantis): rewrite prompt_addon for widget-driven qualification flow (push origin/main) |

### Sprint 1 — ATLANTIS_WIDGET_BEHAVIOR_AUDIT_v1 (read-only)

Аудит реконструировал что происходит с момента когда prefilled `«Здравствуйте! Помогите подобрать квартиру в АК "Атлантис".»` приходит на webhook Радиста до отправки первого ответа Sofia клиенту. Сравнение с двумя контрольными сценариями: Тильда-клиент (тот же канал, prefilled про «отправьте презентацию», `find_recent_atlantis_lead` возвращает реальный лид) и `@humanAINeural_bot /start` без объекта.

**Trifecta-таблица** (8 критических шагов × 3 сценария с file:line):

- `state.source_object`: виджет=`atlantis` (`sofia_radist_gateway.py:906-912`), Тильда=`atlantis`, /start=`None` (`bot_server.py:1271-1282`).
- Bitrix-вызов: виджет→`find_recent_atlantis_lead → None` (нет лида от формы) → `create_lead` с `SOURCE_ID=504` дефолтный, не 397; Тильда→`find_recent_atlantis_lead → {id, assigned}` → `set_lead_assigned(428)` + `update_lead`; /start→пропуск.
- Force-routing на репликах 1-2 (`core/pipeline.py:176-183`): виджет=ДА (`source_object` есть, `user_msg_count≤2`), Тильда=ДА, /start=НЕТ (Analyzer работает).
- `state.materials_request_count`: виджет=0 (текст «помогите подобрать» — не запрос материалов), Тильда=1 (extractor `wants_materials=true` на «отправьте презентацию» → `message_processor.py:81-84` → state_summary показывает «⚠️ БЫЛ 1 ОТКАЗ ОТ СОЗВОНА» уже на 1-й реплике).
- system_prompt: виджет/Тильда получают object_context (`core/pipeline.py:259-266`) + presentation_url + (DEV) prompt_addon с «контакт уже получен» — для виджета это **фактически ложно** (контакта в Bitrix нет).

**Прогноз первых 4 реплик виджет-Sofia** (по сборке промпта без живого LLM-вызова): высокая вероятность что Sofia вываливает презентацию на 1-й реплике (object_context + presentation_url инжектятся принудительно), упоминает Крым/цены, ведёт квалификацию по чек-листу. Низкая вероятность запроса контакта (prompt_addon явно запрещает). Уровень уверенности — средняя для содержания, высокая для механики (force-routing GREETING + RAG-query константа `"приветствие клиент с сайта интерес к объекту"`).

**8 точек расхождения с базовой логикой /start** (key findings):
1. Force-routing на репликах 1-2 — RAG жёстко GREETING с константной query, не адаптируется к смыслу prefilled.
2. Object_context инжектируется (полная карточка `atlantis_context.md` с ценами 16.8/20.7/22.8 млн).
3. Инструкция «При запросе презентации — отправь эту ссылку клиенту» — слово «подобрать» в prefilled может быть LLM-интерпретировано как запрос материалов.
4. **prompt_addon «контакт уже получен» — для виджет-клиента ложно** (find_recent_atlantis_lead → None, телефон не приходил).
5. Отсутствие Bitrix-привязки на старте (лид создаётся только при finalize, риск коллизии 60-сек окна с чужим ATL-лидом).
6. user_name fallback на `phone` (часто пуст у Telegram Business) → state_summary без имени.
7. В radist-пути нет статического greeting (всегда LLM-generated).
8. `user_name` нигде не передаётся в системный промпт — Sofia может не обратиться по имени.

Сергей подтвердил аудит живым smoke 04.05 (виджет вываливает цены, прыгает к презентации, не запрашивает контакт нормально).

### Sprint 2 — ATLANTIS_ADDON_INFRA_PORTBACK + новый prompt_addon

**STOP #1 (investigate_first):** md5 четырёх файлов (PROD/DEV pipeline.py + source_objects.py), 4 snapshots в `/tmp/*before_atl_addon_20260505_230514`, точка вставки в PROD pipeline.py — между `:205` (`)` после presentation_url) и `:207` (комментарий was_offline), отступ 12 пробелов; точка вставки в PROD source_objects.py — между `:20` (`"greeting": ...`) и `:21` (закрывающая `},`), отступ 8 пробелов. Voice-pipeline `stream_voice_response` `:350-358` намеренно НЕ тронут (вне scope).

**STOP #2 (drafting):** Сергей дал финальный текст addon целиком (1 сообщение) — 6 блоков:
1. КОНТЕКСТ ВХОДА — два пути (Тильда/виджет), не предполагать «контакт получен», Атлантис как стартовая точка а не клетка.
2. ПЕРВАЯ РЕПЛИКА — без цен/УТП/локации, образец дословный.
3. ВЕДЕНИЕ ДИАЛОГА — обычный чек-лист (цель→бюджет→оплата→стадия→локация→ЛПР→созвон), факты карточки реактивно.
4. ПРЕЗЕНТАЦИЯ — 4 случая отправки PDF (созвон-бонус / отказ от созвона / тупик / прямая просьба).
5. ЗАПРОС КОНТАКТА — телефон в финале, ник только для письменной коммуникации.
6. SAFETY-RAIL (политика/СВО/юр/мошенничество) — сохранён дословно из старого addon.

Принципиальное архитектурное решение: addon применяется к **обоим путям** одинаково (виджет + Тильда). Ранее DEV-addon делал ложное предположение «контакт уже получен» — для Тильды это работало случайно (лид с телефоном уже создан webhook-формой), для виджета было фактически неверным. Новый текст не предполагает контакт ни для одного пути — Тильда-клиент в худшем случае ещё раз подтвердит телефон, что не ломает воронку.

**STOP #3 (DEV-деплой):** sofia-radist-dev + sofia-web-api-dev перезапущены, health-чеки 5002/8081 ok, журнал 0 ERROR.

**PROD-деплой:** sofia-radist → sofia-web-api → sofia-gpt последовательно, `is-active` после каждого, журналы за 2 минуты — 0 ERROR/Traceback/Exception, health-чеки 5001/8080 ok, sofia-gpt получил Telegram getMe/deleteWebhook без ошибок. Pre-commit black прошёл на DEV.

### Финальные md5 после сессии

| Файл | до сессии | после сессии |
|---|---|---|
| `/opt/sofia-gpt/core/pipeline.py` | `872769a8d4...` | `8511e83f9e...` |
| `/opt/sofia-gpt-dev/core/pipeline.py` | `e5c7af2e95...` | `e5c7af2e95...` (НЕ тронут) |
| `/opt/sofia-gpt/config/source_objects.py` | `c6cd1b13e1...` | `4e8308fd15...` |
| `/opt/sofia-gpt-dev/config/source_objects.py` | `3529d24e13...` | `89ae82f2eb...` |

DEV/PROD-тексты `prompt_addon` побайтно идентичны (3464 байт, проверено через runtime-импорт обоих модулей).

### Уроки

1. **Read-only аудит-сценариев перед изменением промпта.** Перед прикосновением к коду Сергей запросил 3-сценарный диф с прогнозом первых 4 реплик. Аудит за 30 минут вывел 8 конкретных точек расхождения с file:line. Без этого шага мы бы не поняли что **prompt_addon применяется к обоим путям** (виджет+Тильда) и что текст должен быть нейтрален относительно «контакт получен/не получен» — иначе для виджета он системно врёт.
2. **Дословный портбэк DEV-образца, не «упрощение».** Acceptance criterion #1 формально требовал «одна строка с условием», но DEV-образец — это **две строки** (`if obj_config.get("prompt_addon"):` + `system_prompt += f"..."`). Не схлопывал в один-лайнер — Сергей подтвердил «двухстрочный паттерн = правильный портбэк». Принцип: при копировании готового образца из работающей среды — копировать побайтно, схлопывания/упрощения = новый источник риска.
3. **Идентичность DEV/PROD-текста addon — runtime-проверка через импорт обоих модулей.** Перед коммитом сравнили `len()` + строковое равенство prompt_addon из обоих SOURCE_OBJECTS через двойной `importlib.import_module`. Это сильнее чем `md5sum` файла (файлы могут различаться по black-форматированию, but значение dict-ключа должно совпадать побайтно).
4. **Наблюдение: voice-pipeline `stream_voice_response` имеет второй блок инжекции object_context+presentation_url** (`core/pipeline.py:350-358` в PROD, аналогично в DEV). Туда `prompt_addon` не пробрасывается — voice использует отдельный compact `_get_object_context()`. Если Atlantis когда-нибудь вернётся в голос (сейчас по CLAUDE.md «Голоса для Atlantis НЕ существует») — нужно отдельное решение должен ли voice-промпт получать addon. P3 backlog, не блокер.

### Открыто в следующую сессию

- **Сергей делает live smoke** виджет-flow через `t.me/m/Fiw3ldhkN2My`. Ожидаемое: первая реплика без цен/Крыма, обычная квалификация без вываливания фактов, PDF не приходит на 1-й–2-й реплике, в финале запрашивает телефон. Если совпало — `ATLANTIS_ADDON_INFRA_PORTBACK` закрыт окончательно. Если расхождение — итерация по тексту addon (L0 rollback или новый коммит с правкой только текста, инфра-часть остаётся).
- **Тильда-flow regression check** — через `t.me/m/QinKZEsTNmRi` пройти диалог, убедиться что Sofia здоровается мягко, идёт по чек-листу, в конце предлагает созвон. Особое внимание: не сломалось ли поведение «уже подтверждённого контакта» (теперь Sofia может ещё раз спросить телефон в финале — это by design, не баг).
- **`config/source_objects.py` PROD без black-форматирования** — известный косметический drift, отложен. Не блокер.

### Snapshots

- `/tmp/pipeline.py.prod.before_atl_addon_20260505_230514` (17483 байт)
- `/tmp/pipeline.py.dev.before_atl_addon_20260505_230514` (57904 байт)
- `/tmp/source_objects.py.prod.before_atl_addon_20260505_230514` (3218 байт)
- `/tmp/source_objects.py.dev.before_atl_addon_20260505_230514` (5493 байт)

---

## 28-29.04.2026 — RIZALTA в текстовом канале: регистрация, двухуровневая защита от Bitrix, деплой в PROD, investment-only позиционирование

### TL;DR

Двухдневная сессия добавила RIZALTA как второй текстовый объект в Sofia параллельно Atlantis — отдельный путь привлечения через виджет на сайте rizalta → Telegram Business Link → @SofiaOazis. Принципиальное отличие от Atlantis: **Bitrix-интеграция для RIZALTA полностью отключена by design** (менеджеры заносят лиды вручную). Реализована **двухуровневая защита**: уровень 1 (`_is_radist_bitrix_session` возвращает False для rizalta-сессий — short-circuit caller-блоков) + уровень 2 defense-in-depth внутри `create_or_update_lead` (если уровень 1 сломан — payload подменяется на «Тестовый лид» / `89181011091` с громким `🚨 [BITRIX_RIZALTA_LEAK]` алармом). Observer-нотификации помечены тегом `· rizalta` в названии темы. Деплой в PROD по split-схеме (core-файлы applied чисто, `config/source_objects.py` ручная вставка из-за известного drift). После боевого smoke-теста через @SofiaOazis выявлена ошибка позиционирования («для себя или для инвестиции») — исправлена: RIZALTA теперь явно позиционируется как **исключительно инвестиционный продукт** без опции личного проживания собственника, устаревший пункт «2 недели весной/осенью со скидкой» удалён.

5 коммитов в DEV (28-29.04), 3 коммита в PROD (29.04, без push by design).

### Хронология коммитов

| # | Репо | SHA | Subject |
|--:|------|------|---------|
| 1 | DEV | `027a353e` | docs(atlantis): consolidate widget state — Tilda form + chat widget |
| 2 | DEV | `cf104e7a` | docs(rizalta): extract object factsheet from voice prompt v4.3 |
| 3 | DEV | `e25bc8f7` | docs(rizalta): rebuild factsheet from full project sources |
| 4 | DEV | `9947721d` | feat(rizalta): register object with Bitrix bypass and Observer tag |
| 5 | DEV | `4d79a8ae` | docs(rizalta): clarify investment-only positioning, remove stale owner-stay clause |
| 6 | PROD | `3be32d68` | feat(rizalta): deploy from dev 9947721d (split — core files only, atlantis-addon infra portback deferred) |
| 7 | PROD | `9f2d35bf` | feat(rizalta): toggle observer via env (default off for private testing) |
| 8 | PROD | `a5820989` | docs(rizalta): clarify investment-only positioning (sync from dev 4d79a8ae) |

### Sprint 1 — ATLANTIS_WIDGETS_DOC_v1 (`027a353e`)

Создан `docs/ATLANTIS_WIDGETS_STATE.md` (15.0 KB) — справочник по двум независимым путям привлечения клиентов на Атлантисе: форма «Получить презентацию» (Тильда → `t.me/m/QinKZEsTNmRi` → SOURCE_ID=397 в Bitrix) и HTML-виджет «Чат с менеджером» (`widgets/atlantis_chat_widget.html` → `t.me/m/Fiw3ldhkN2My` → дефолтный `SOURCE_ID=504`, не 397). Цель документа — baseline перед масштабированием на новые сайты, описывает фактическую цепочку без истории. Парная правка в gitpull-блоке CLAUDE.md (scp-строка для нового файла). Зафиксированы открытые вопросы (где реально стоит виджет, prefilled-текст для Business Link, риск 60-сек коллизии find_recent_atlantis_lead).

### Sprint 2-3 — RIZALTA_CONTEXT_EXTRACT + REBUILD (`cf104e7a` + `e25bc8f7`)

Двухитерационная подготовка фактологии для нового объекта. Первая версия извлекла факты только из `VOICE_SYSTEM_PROMPT_RIZALTA` (`core/pipeline.py:646-780`, голосовой питч RIZALTA v4.3) — короткая карточка ~7.8 KB. По уточнению Сергея вторая итерация расширила за счёт **`rag_training_data.json`** — найдено **4 диалога с object_purchased=RIZALTA** (Дмитрий_Оазис, Виталий_Рязань, Андрей_Псков ×2 — две стадии одной сделки), 109 совпадений по ключевым словам. Извлечена детальная фактология: схема гарантированного дохода с примерами расчётов (50% валового, не меньше договорной суммы), окупаемость 7 лет в консервативе, дорожная карта сделки (10 шагов от Госключа до эскроу), категории комнат, налоговая оптимизация ИП+аренда (УСН 5-6% vs 13% НДФЛ), реферальная программа 400к, команда сопровождения с архитектором Пергаевым и руководством Zont. Финальная карточка 102 строки / 13.4 KB — структурно зеркалит `objects/atlantis_context.md`.

### Sprint 4 — RIZALTA_REGISTER_v1 (`9947721d`, DEV)

Регистрация объекта `"rizalta"` в `config/source_objects.py` с **узкими keywords** `["ризалта", "rizalta", "rizalta resort"]` (после обсуждения с Сергеем: keyword `"белокуриха"` исключён чтобы не false-match'нуть «А что есть в Белокурихе?» от случайного клиента). Без `prompt_addon` — этот механизм DEV-only, в PROD не работает (ATLANTIS_ADDON_INFRA_PORTBACK).

**Двухуровневая защита от Bitrix.** Уровень 1 в `sofia_radist_gateway.py`: расширение существующего `_is_radist_bitrix_session()` — для `source_object="rizalta"` возвращает `False`, чем шортит все 5 Bitrix-функций (`create_or_update_lead`, `update_lead`, `finalize_lead`, `set_lead_assigned`, `start_distribution_bp`) в обоих caller-блоках Radist (`radist_finalize_timeout` + `radist_callback`). Skip пишется в лог как `🚫 [BITRIX_SKIP] source=rizalta function=<name>`. Уровень 2 (defense-in-depth) внутри `create_or_update_lead` в `core/bitrix.py`: если caller всё-таки пропустил rizalta-сессию (баг рефакторинга, новый канал-потребитель) — payload **подменяется** на `TITLE="Тестовый лид"`, `NAME="Тестовый лид"`, `PHONE="89181011091"`, дедупликация через `find_lead_by_phone` намеренно пропускается (чтобы не приклеиться к чужому существующему лиду с тем же тестовым номером). Громкий `🚨 [BITRIX_RIZALTA_LEAK]` ERROR-уровня — мониторинг сразу заметит. Добавлен `title_override` параметр в `create_lead`. Логика «двойной замок с подменой» (а не двойной early-return) — Сергей сформулировал: «при поломке уровня 1 факт протечки должен быть виден в Bitrix как Тестовый лид → пойдут разбираться → найдут поломку».

**Observer-tag.** В `notify_observer` + `get_or_create_topic` добавлен опциональный параметр `source_object`; при создании темы имя формируется как `f"{display_name} · {source_object}"` (формат точка-разделитель — выглядит как контактная пометка, не как технический баг). Helper `_get_source_object(user_id)` добавлен рядом с `_is_radist_bitrix_session` чтобы 5 call-site'ов notify_observer не дублировали `getattr(state_manager.get_state(...))`. Существующие atlantis-темы не переименовываются (одна тема создаётся при первом сообщении).

### Sprint 5 — RIZALTA_TEST_DEV_v1 (автотесты)

4 автотеста на DEV перед деплоем — все PASS:
1. `detect_source` 6 кейсов: prefilled RIZALTA→`rizalta`, prefilled Atlantis→`atlantis` (регрессия), `Atlantis` lowercase→`atlantis`, «Ризалта» именительный→`rizalta`, **«Белокуриха» одиночный→`None`** (узкие keywords защищают от false-match), нейтральная фраза→`None`.
2. `_is_radist_bitrix_session` уровень 1: 4 кейса (rizalta→False, atlantis→True, None→False, no state→False).
3. Уровень 2 fallback с моком `aiohttp.ClientSession`: проверено что `find_lead_by_phone` НЕ вызывается, на `crm.lead.add` уходит payload с `TITLE='Тестовый лид'`/`NAME='Тестовый лид'`/`PHONE='89181011091'`, в логе появляется `🚨 [BITRIX_RIZALTA_LEAK]`.
4. Observer `get_or_create_topic`: 3 кейса — rizalta→`'Иван Петров · rizalta'`, no source_object→`'Андрей Смирнов'` (регрессия Atlantis-формата), atlantis→`'Мария Лебедева · atlantis'` (универсальность).

Открытие в разведке: **DEV bot_server.py из `/opt/sofia-gpt-dev/` не запущен** как systemd-сервис. PROD bot_server (`/opt/sofia-gpt/...`) обслуживает @humanAINeural_bot, ещё два `run_polling.py` — из `/opt/bot-dev/` (другой проект Сергея). Из задеплоенного DEV-кода активны только `sofia-radist-dev` + `sofia-web-api-dev`. Ручной тест в DEV возможен только через временный запуск `bot_server.py` руками — это не блокер, но стоит сделать `sofia-bot-dev.service` для регулярного DEV-тестирования (P3 backlog).

### Sprint 6 — RIZALTA_DEPLOY_PROD_v1 (`3be32d68`)

Split-deploy в PROD по схеме: `core/bitrix.py` + `sofia_radist_gateway.py` через `git -C /opt/sofia-gpt-dev show 9947721d -- <file> | git -C /opt/sofia-gpt apply --index -` (DEV ≡ PROD до коммита, патчи применились чисто). `objects/rizalta_context.md` — простой `cp DEV → PROD` (нового файла в PROD не было). `config/source_objects.py` — ручная вставка только rizalta-блока через `Edit` (drift известен: PROD без `prompt_addon`, без black). После применения — md5 PROD bitrix.py и radist_gateway.py = DEV; `source_objects.py` намеренно различается (atlantis-блок не тронут, rizalta-блок добавлен). Снапшоты в `/tmp/*.prod.before_rizalta_deploy_20260429_095745`.

**Рестарт всех трёх сервисов** (sofia-radist + sofia-web-api + sofia-gpt) — оркестратор настоял на полном покрытии: «защита это страховка от ошибок. Если она работает только в одном месте — это хрупко. Если завтра кто-то добавит новую логику где RIZALTA-сессия попадёт в другой канал — нет защиты». Я изначально предлагал минимально (только sofia-radist), но согласился — defense-in-depth требует чтобы level-2 был прогрет во всех 3 импортирующих модуль `core/bitrix.py` сервисах. Последовательно с `is-active` чек после каждого. ERROR-grep за 2 минуты после рестарта — 0 строк.

PROD detect_source-тесты прошли: rizalta распознан, atlantis регрессия не нарушена, level-1+level-2 в коде через `inspect.getsource`.

### Sprint 7 — RIZALTA_OBSERVER_TOGGLE_v1 (`9f2d35bf`)

После деплоя Сергей решил провести **приватные тесты** через @SofiaOazis по RIZALTA-сценарию без шума в Observer-группе. Точечный env-флаг `RIZALTA_OBSERVER_ENABLED` (default `"false"`) — guard внутри `notify_observer` сразу после существующей `if not OBSERVER_CHAT_ID...: return`: при `source_object == "rizalta" and not RIZALTA_OBSERVER_ENABLED` пишет одну строку `🚫 [OBSERVER_SKIP] source=rizalta reason=disabled_by_env phone=<phone>` и выходит. Не-RIZALTA Observer без изменений. Включение обратно — `sed -i 's/^RIZALTA_OBSERVER_ENABLED=false/RIZALTA_OBSERVER_ENABLED=true/' /opt/sofia-gpt/.env && sudo systemctl restart sofia-radist`. Default false — гарантирует «выключен сразу после деплоя до явной команды Сергея». `.env` gitignored — RIZALTA_OBSERVER_ENABLED=false выставлено на сервере вне коммита.

### Sprint 8 — SERGEY_STATE_RESET_v1 + RADIST_HISTORY_SOURCE_RECON_v1 (без коммитов)

После первого RIZALTA-теста Sofia подтянула старое состояние (бюджет из старого Atlantis-диалога, тема «готовых номеров нет»). Чистка состояния по user_id `-40076372` (Sergey, chat_id `38076372`, tg_username `sergey_7in`): `DELETE FROM client_state` + `DELETE FROM messages` + `DELETE FROM radist_leads` (последняя имела привязку к историческому Atlantis-лиду 265944 от 15.04 — потенциальная мина для будущих не-rizalta тестов в этом же чате).

После второй чистки Sofia всё равно начала с темы «готовые номера». Read-only разведка: `get_history(channel, chat_id, limit=100)` в `sofia_radist_gateway.py:287` читает из таблицы **`radist_messages`** (не `messages`!) — 37 строк по `chat_id=38076372` остались нетронутыми, последние 5 явно про вчерашнюю тему. Гипотеза подтверждена данными: LLM подтянул историю предыдущего разговора и продолжил контекст. **Чистка должна включать `DELETE FROM radist_messages WHERE channel='telegram' AND chat_id=38076372`** — `radist_chats` оставляем (привязка `chat_id ↔ tg_username`, иначе `user_name` сломается).

Урок: bot_server.py / web_api.py пишут в общую `messages` (по user_id), Radist в свою `radist_messages` (по chat_id) — любая «универсальная» one-liner-чистка по user_id молча пропускает Radist-историю.

### Sprint 9 — RIZALTA_CONTEXT_INVESTMENT_ONLY_v1 (`4d79a8ae` DEV + `a5820989` PROD)

В реальном диалоге через @SofiaOazis Sofia предложила «для себя или для инвестиции» — это структурно **некорректно** для RIZALTA: объект инвестиционный, по договору с УК собственник в номере не проживает. Карточка `objects/rizalta_context.md` поправлена в обеих средах (DEV ≡ PROD по md5 после правок: `56a3303c06e1...`). 4 правки:

1. **Концепция:** «инвестиция, не жильё» → «исключительно инвестиционный продукт — не для личного проживания и не для отдыха собственника»
2. **Новый раздел «Личное проживание собственника не предусмотрено»** — однозначное «нет» на вопрос «могу ли я сам приезжать»
3. **Раздел «Спецусловия для собственников» удалён**: пункт «2 недели весной/осенью со скидкой 30%» противоречил правилу выше и устарел. **Два других факта перенесены**: «приёмка не нужна» → в `Условия оплаты`, «перепродажа сохраняет агентский договор» → в `Юридическое` (по уточнению Сергея — не выкидывать факты вместе с разделом).
4. **Инструкции для диалога:** новый пункт **первым** в списке — «не предлагай RIZALTA для себя или для инвестиции, это всегда инвестиционный продукт»

PROD-rizalta-карточка читается через `load_object_context()` при сборке system_prompt — рестарт `sofia-radist` обновил кеш модуля, новый текст идёт в LLM сразу со следующего сообщения.

### Уроки

1. **Defense-in-depth с громким аларм-логом > silent early-return.** Уровень 2 в `create_or_update_lead` пишет `🚨 ERROR` и **подменяет** payload (а не молча пропускает) — Сергей: «при поломке уровня 1 факт протечки должен быть виден в Bitrix как Тестовый лид → пойдут разбираться → найдут поломку». Silent skip в каждом из 5 call-site'ов был бы формально правильным, но неотличим от штатной работы.
2. **Полное покрытие level-2 во всех 3 каналах > минимально-достаточно.** Изначально я предложил рестарт только `sofia-radist` (по букве «only canonical RIZALTA channel»). Сергей настоял на всех трёх — `core/bitrix.py` импортируется в bot_server и web_api тоже, без рестарта level-2 в их памяти не загрузится, и первый случайный коммит расширяющий RIZALTA на эти каналы тихо обойдёт защиту.
3. **Drift между средами → ручная вставка через Edit для критических конфигов, остальное deferred.** Cherry-pick между PROD/DEV не работает (разные репо), `git format-patch | git am` падает на drift'нутом контексте. Для `config/source_objects.py` — Edit-инструмент с явной точкой вставки, прецедент по `prompt_addon` остаётся в backlog отдельно. Запрет «не правь по пути» спас от затягивания скоупа.
4. **Чистка state Radist-канала требует `radist_messages`.** `client_state` + `messages` + `radist_leads` — недостаточно. История диалога (то что попадает в LLM-контекст через `get_history`) живёт в `radist_messages` (ключ `chat_id`, не `user_id`). Любая «универсальная» очистка по user_id её пропускает.
5. **Реальный диалог-тест через @SofiaOazis находит баги позиционирования, которых не видит автотест.** Investment-only ошибка проявилась только когда Sofia в боевом потоке предложила выбор «для себя/для инвестиции» — структурный изъян карточки, который автотест (matching keywords) не отловил бы.

### Carry-over на следующую сессию

- **DEV bot_server.py не запущен как systemd** — стоит сделать `sofia-bot-dev.service` для регулярного DEV-тестирования RIZALTA-flow (P3).
- **Уровень 1 guard в bot_server.py отсутствует** — `_is_bitrix_session(user_id)` в bot_server.py возвращает True для rizalta-сессий (источник там не отфильтрован). Если RIZALTA когда-нибудь придёт через @humanAINeural_bot — defense сработает только на уровне 2 (с алармом). Не критично для текущего RIZALTA-канала (виджет → Radist), но при расширении нужен отдельный спринт.
- **Внешние материалы Tilda (виджет rizalta) могут противоречить новому investment-only позиционированию** — стоит сверить с текстами на сайте rizalta до боевого запуска виджета. Не код, не правил.
- **`scp` для нового memory-файла `project_rizalta_text_channel.md`** должен быть добавлен в gitpull-блок CLAUDE.md (если файл создаётся этой сессией).

---

## 21.04.2026 — Пилот холодного обзвона: инфраструктура workstation + hang bug в dial.py

### TL;DR

Сессия собрала инфраструктуру пилота холодного обзвона за несколько часов утренней работы: 3 новых компонента (dial.py per-turn metrics + recording path + listen_live + ExecStop hangup), 5 реальных звонков холодной базы проведено. Hang bug в dial.py на invalid/unanswered номерах найден через диагностику и починен двумя коммитами — первая попытка (`is not None`) провалилась smoke-тест, рабочая версия требует 3 consecutive Up/Ringing polls перед тем как «channel ever seen». Telphin autodial разведан в публичной доке — НЕЯСНО поддерживается ли AMD + passthrough, Сергей написал менеджеру. CLAUDE.md пополнен секцией «Рабочая станция пилота», новый `docs/PILOT_WORKSTATION_RUNBOOK.md`.

7 коммитов в DEV, not pushed.

### Хронология коммитов

| # | SHA | Subject |
|--:|------|---------|
| 1 | `8ac8233f` | feat(dial): per-turn metrics + turn timers + recording path in realtime stream |
| 2 | `f28cd748` | fix(dial): use CALL_UUID from CDR.lastdata for MixMonitor recording path |
| 3 | `f501d719` | feat(voice): live audio listen wrapper for pilot |
| 4 | `37e099a5` | feat(voice): ExecStop hangup AudioSocket orphans on sofia-voice restart |
| 5 | `2304b075` | docs: pilot operator runbook — three-terminal workflow |
| 6 | `38c42abf` | fix(dial): early exit when originate produces no channel (v1, flawed) |
| 7 | `75082b73` | fix(dial): require 3 consecutive Up/Ringing before canceling giveup |

### Sprint 1 — DIAL_PY_METRICS_v1 (`8ac8233f` + `f28cd748`)

Per-turn EOU / LLM / TTS-first-chunk метрики в realtime-стрим `dial.py`, агрегируемые по триггеру `⏱️ Turn timings:`. Timers `[MM:SS]` от call_start для USER/SOFIA/METRICS/AUTO_HANGUP строк. Mixed scheme: `[HH:MM:SS]` wall clock для Ringing/Answered/Ended (удобно cross-ref с CRM). После ANSWERED+billsec≥5: post-call summary выводит `Recording:` путь и `Download (run from your Mac): scp sofia-voice:...` one-liner.

Post-smoke fix (`f28cd748`): первый запуск дал `Recording: not found` т.к. путь строился из `CDR.uniqueid` (`1776758372.14`), а MixMonitor пишет с `${CALL_UUID}` из dialplan (kernel-random RFC-4122 `c83688c7-...`). Retrospective verify на live-файле — путь совпал с реально существующим WAV. Два UUID у Asterisk — выучено.

### Sprint 2 — DIAL_LIVE_LISTEN_v1 (`f501d719`)

`bin/listen_live.sh` — live-прослушка MixMonitor WAV через ssh-pipe + ffplay на Mac. `inotifywait -e create` на каталог `recordings/YYYY-MM-DD/` + `tail -c +0 -F <file.wav>` + exit after 20с idle growth. Mac-side wrapper `while true; do ssh sofia-voice 'listen_live.sh' | ffplay ...; done` автопереключает между звонками.

Smoke провалился первый раз — SSH запрашивал пароль в каждой итерации while-loop. Fix: `ssh-copy-id sofia-voice` на Mac. После — live audio подтверждён, задержка 2-5с приемлема. Финальная команда использует `-f s16le -ar 8000 -ch_layout mono -` (MixMonitor пишет 8kHz mono) + `2>/dev/null` чтобы глушить stderr-статусы листенера.

### Sprint 3 — EXECSTOP_AUDIOSOCKET_CLEANUP_v1 (`37e099a5`)

`bin/hangup_audiosocket.sh` — узкий фильтр: `core show channels concise | awk -F'!' '$6=="AudioSocket" {print $1}' | xargs channel request hangup`. `ExecStop=/opt/sofia-voice/bin/hangup_audiosocket.sh` добавлен в `sofia-voice.service` via `sed`. Unit md5 до `8fdb7808...` → после `0f2a76a6...`. Snapshot `/tmp/sofia-voice.service.before_execstop_20260421_090953`.

Smoke (два phase'а): **Part 1** — restart на активном канале `PJSIP/telphin-endpoint-0000000b`: restart выполнился за **51 мс**, через 3с `core show channels count = 0`, `journalctl -t sofia-voice-hangup` показал `hangup PJSIP/telphin-endpoint-0000000b`, MainPID 24230 → 42525 (auto-restart через `Restart=on-failure`). **Part 2** — normal workflow звонок с graceful hangup клиентом: disposition=ANSWERED billsec=43, ExecStop **не вызван** (Python жив, нет рестарта). Оба passed.

Защита от root-cause 20.04 инцидента задеплоена.

### CLAUDE.md + Pilot operator runbook (`2304b075`)

Новая секция «Рабочая станция пилота (three-terminal workflow)» в CLAUDE.md — T1 Mac listen_live + T2 main-server dial.py + T3 Mac scp download. Плюс строчка про «рестарт безопасен технически, но дисциплина no-restart-mid-call остаётся».

### 5 звонков пилота + hang на 79262228016

Сергей провёл живой обзвон: 11:12:27 +79219662562 ANSWERED 48с, 11:14:41 +79104320164 4с hang-up, 11:15:44 +79181011091 ANSWERED 35с, 11:19:05 +79104320164 3с hang-up, **11:20 +79262228016 — hang 4 мин без summary**. Сергей убил процесс 46783 через `kill`.

### Sprint 4 — HANG_DIAGNOSTIC + DIAL_PY_CHANNEL_GIVEUP_v1 (`38c42abf` → `75082b73`)

**Read-only разведка:**
- CDR за 11:20–11:27 UTC = пусто (Master.csv последняя строка 11:19:23). Non-ANSWERED за весь день = 0.
- Asterisk journal 11:19:30–11:28 = пусто. `/var/log/asterisk/full.log` не пишется с 11:16 (logrotate квирк, отдельно).
- `outbound_2026-04-21.jsonl` не имеет записи для 79262228016 (dial.py убит до writeback).
- `cdr.conf` — все в `[general]` закомментировано (дефолты). Критическое открытие: дефолтная документация говорит **«outgoing calls always logged regardless of unanswered flag»** — `unanswered=yes` для нашего случая **не помогло бы**. Проблема глубже: Asterisk не создал channel вообще.

**Telphin autodial recon (6 источников):** [Голосовой робот](https://www.telphin.ru/products/virtual-atc/voice-robot) 1790₽/мес, до 100 одновременных, predictive-mode. **AMD и passthrough на внешний SIP endpoint в public docs не упомянуты.** REST API имеет `/callback/` (инициация) и webhooks (dial-out/answer/hangup), но спецификации за Confluence auth'ом. Вердикт: closed-loop voice robot на первый взгляд, нужен ответ менеджера.

**Fix v1 (`38c42abf`) — не сработал:** `channel_ever_seen = True` при любом `state is not None` через 30с giveup. Smoke на 88000000000 — dial.py висел > 60с. Root cause: Asterisk кратковременно создаёт PJSIP channel в state `Ring`/`Other` пока SIP INVITE летит на invalid peer, `is not None` срабатывает → escape навсегда disabled → fallback до 600с.

**Fix v2 (`75082b73`) — рабочий:** счётчик `channel_consecutive`, требует 3 consecutive polls в `("Up", "Ringing")` (≈3с sustained) прежде чем `channel_ever_seen = True`. Сбрасывается на None/Other. Smoke на 88000000000 — **exit за 35.4с** ✓. Regression на +79181011091 — ANSWERED 30с billsec ✓, метрики/transcript/recording все ok.

**Побочная проблема:** stdout всё ещё говорит `Status: FAILED (no CDR after 600s)` даже при 35с exit — общий текст для обеих no-CDR веток. Backlog P1 косметика.

### Новые документы

- `docs/PILOT_WORKSTATION_RUNBOOK.md` — три терминала, состояние 21.04, тонкости (orphan / briefly-existing channels / два UUID / SSH ключ / misleading message / V1 assumption).

### Итог

Инфраструктура пилота полная. Сергей может продолжать обзвон 47+ номеров холодной базы — любой invalid/unanswered номер завершится за 35с, live-прослушка работает, запись скачивается одной командой, restart sofia-voice безопасен.

Carry-over на следующую сессию: (1) Telphin autodial — ждём менеджера, (2) Greeting PCM artefacts — бесплатная диагностика через live-синтез greeting, (3) Misleading FAILED text — косметика.

### Post-session closure — START_SESSION_PARITY

После финального session-end коммита Сергей обновил локальный `~/projects_claude/start-session.sh` на Mac: добавлены scp + cat для 4 docs (`PILOT_WORKSTATION_RUNBOOK.md`, `LESSONS_LEARNED.md`, `VOICE_ARCHITECTURE.md`, `VOICE_TECH_STACK_FULL.md`). Локальный скрипт теперь полностью зеркалит Gitpull блок CLAUDE.md (13 файлов). Закрыл P3 backlog item «парная правка к `af11212f`» от 19.04. Коммит `21df9bd2` + finalizing commit.

---

## 20.04.2026 — pacing fix + локализация проглатывания слогов в голосе

### TL;DR

Длинная сессия от 05:46 MSK. **Главное достижение: локализован и починен корневой источник проглатывания слогов в голосовом канале Sofia** — AudioSocket buffer overflow из-за `asyncio.sleep(0.018)` pacing против 20ms playback rate. Fix асимметричный: `_speak_pcm=0.020` / `_speak=0.019` (компенсация ~1ms event loop overhead от параллельных gRPC STT + Silero inference в активном разговоре). Подтверждено математически (correlation greeting-source vs MixMonitor 0.034 → 0.987) и ушами Сергея на silent + активных тестовых звонках. 2 коммита в origin DEV, PROD не тронут (voice-компонентов в `/opt/sofia-gpt/` нет).

Остался один открытый вопрос для следующей сессии — «склейки внутри слов» (шероховатость на стыках слогов, не связана с overflow). Бесплатная диагностика через уже скачанные A/B файлы.

### Хронология коммитов

| # | Репо | SHA | Subject |
|--:|------|------|---------|
| 1 | DEV | `8f3eeaf0` | feat(voice): pacing fix _speak 0.018→0.019, _speak_pcm 0.018→0.020 |
| 2 | DEV | `7f65fadd` | docs(voice): document pacing fix 20.04 |

### VPS апгрейд 1→2 vCPU (Timeweb Premium NVMe)

- Апгрейд с 1 vCPU до **2 vCPU, 4 GB RAM** на Premium NVMe тарифе (~1000₽/мес). `nproc=2`, load 0.00, RAM 3.2 GB free после boot — аппаратно система в норме
- Гипотеза из 19.04 «1 vCPU = главный bottleneck» **не подтвердилась** — проглатывания слогов сохранились после апгрейда на silent test звонке. Аппаратная конкуренция CPU оказалась ложным следом

### CHUNK-инструментация `_speak` (коммит в `/opt/sofia-voice/` на VPS, DEV-only)

- Добавлено per-chunk timing логирование в `_speak` Yandex-branch: uuid + chunk_idx + offset + t_before_us + send_dur_us + sleep_actual_us + sleep_overrun_us, плюс ⚠️ SLEEP_OVERRUN warning при overrun >10ms
- Snapshot: `/tmp/voice_asterisk.py.before_instr_20260420_041752` на VPS (md5 `d677c89c9a9242f3ff923350954abde3`)
- sofia-voice рестартован, тестовый звонок Сергея `8ad55f5b` (171с, 11 TTS реплик, 4373 CHUNK-строк)

### Первый неверный вывод: «Python-уровень чист, виновник downstream»

Анализ CHUNK-timing звонка `8ad55f5b`:
- sleep_overrun median 947us, p99 2147us, max 3510us — **0 overrun >10ms** на 4373 интервала
- send_dur median 75us, max 458us — socket.send никогда не блокируется
- Inter-chunk gap медиана 19 114us, max 21 697us — стабильно
- Позиция в реплике не выделяется (first_10 avg 905us, mid 955us, last_5 1039us)

Вывод (D): «Python-уровень pacing стабилен. Проблема не в asyncio/socket. Копать в RTP/Telfin/Asterisk transcoding». **Оказалось неверно.**

### `docs/VOICE_TECH_STACK_FULL.md` написан Claude Code

Исчерпывающая техническая документация voice pipeline: 49KB, 10 разделов + 2 приложения (навигация по коду + diagnostic команды), ASCII-диаграмма end-to-end, 19 шагов pipeline от SIP INVITE до звука клиента, 25 параметров с `file:line` ссылками, таблица 27 файлов. Коммит в итоговом session-close (bundle с pacing-fix).

### TTS A/B матрица `TTS_AB_MATRIX_v1` — расширена для `8ad55f5b`

- 12 WAV через прямой curl на Yandex TTS API (baseline alena 8k / alena 48k→soxr→8k / jane 8k × 4 фразы). Плюс MixMonitor звонка `8ad55f5b`
- Все 12 curl-файлов звучат чисто, **Yandex TTS подтверждённо исключён** как источник проглатываний
- scp-команда: `scp -P 2222 'root@72.56.64.91:/tmp/pilot_recordings_18_04/call_8ad55f5b_*' ~/projects_claude/Sofia/pilot_recordings_18_04/`

### Silent test `b3cd88c8` — критическое наблюдение

- Сергей молчал 65 секунд. **Услышал проглатывания в greeting** (вступительная фраза)
- Greeting идёт через `_speak_pcm` из статичного файла `greeting_rizalta.pcm` (198318 bytes, 12.4s audio). Одна и та же волна на каждом звонке
- **Значит проглатывания детерминированы** — не связаны с нагрузкой, STT, LLM, параллельными процессами. Чисто воспроизводимый дефект pipeline `_speak_pcm → AudioSocket → Asterisk → MixMonitor`
- `_speak_pcm` не был инструментирован → 0 CHUNK-строк для этого UUID

### Прямое сравнение `greeting_source` vs `greeting_via_mixmon`

Побайтовый dropout-анализ MixMonitor WAV первых 13с vs оригинальный PCM-файл:
- **Correlation 0.034** — паттерн громко-тихо радикально расходится
- **209 loud→silent dropout-окон** 10ms (greeting RMS >1500, mixmon RMS <200)
- 277 attenuation >5× в тех же участках
- Сергей подтвердил ушами: в `greeting_via_mixmon.wav` слышны проглатывания, в `greeting_source.wav` — чистое аудио

**Вывод:** дефект вносится **внутри** Asterisk pipeline — между `_speak_pcm` и MixMonitor. Кандидаты: наш pacing / AudioSocket app overflow / Asterisk core routing

### Гипотеза overflow 18ms pacing vs 20ms playback — подтверждена

- `frame_size=320B` = **20ms audio** (8kHz slin16)
- `asyncio.sleep(0.018)` между чанками → wall_per_chunk ~19.1ms против playback 20ms
- Накопление: 900us overflow × 50 chunks/sec = **45ms excess/sec**. За 12s greeting = **540ms лишних чанков** в AudioSocket buffer
- Asterisk сбрасывает overflow → **209 dropout-окон** = физически потерянные фреймы, не наши digital artefacts

### Симметричный фикс 0.018→0.020 — только половина решения

- Правка в трёх местах: `_speak_pcm:1032`, `_speak:1096` (Yandex), `_speak:1139` (ElevenLabs legacy symmetry)
- Snapshot: `/tmp/voice_asterisk.py.before_pacing_20260420_064354`
- **Silent test v2 `1efe792f` — греeting ЧИСТЫЙ:** correlation 0.987 (было 0.034), **0 dropouts** (было 209), Сергей на слух подтвердил
- **Активный разговор `5a46a58f` — «практически каждое слово нестабильное»:** wall_per_chunk стал 20 985us vs audio 20 000us = **5% underrun**. За 10s реплики накапливается **519ms отставания**, Asterisk buffer опустошается, слышны stutter'ы. 3 dropout-дипа в первой TTS-реплике t=18.7s/19.2s/23.1s

### Асимметричный фикс `_speak=0.019 / _speak_pcm=0.020` — финал

Причина асимметрии: event loop overhead. В активном `_speak` параллельно работают Silero VAD inference + gRPC STT stream receive + inbound frame processing — добавляют ~855us на каждый chunk-цикл. В `_speak_pcm` нагрузки нет, overhead ~610us.

Целевая формула: `sleep + event_loop_overhead + send_dur ≈ 20 000us` (идеальное попадание в audio rate).
- `_speak`: 19 000 (sleep) + 855 (overhead) + 117 (send) = **19 972us** ≈ 20ms ✓
- `_speak_pcm`: 20 000 + 610 + 100 = 20 710us (чуть больше, но без конкурентной нагрузки не слышно)

Snapshot: `/tmp/voice_asterisk.py.before_asym_20260420_070119` на VPS.

Контрольный звонок `dff69ac4` (126.2с, 7 TTS реплик через `_speak`, 3395 чанков):

| Reply | chunks | audio_ms | wall_ms | excess | per-chunk_us |
|-------|--------|----------|---------|--------|--------------|
| 0 | 542 | 10 840 | 10 829 | **−11 ms** | 19 980 |
| 1 | 1162 | 23 240 | 23 238 | **−1.6 ms** | 19 999 |
| 2 | 1012 | 20 240 | 20 225 | −15.4 ms | 19 985 |

Inter-chunk gap median = **20 000us ровно**. 0 gaps >22ms. 0 dropouts в MixMonitor на TTS-репликах.

**Вердикт Сергея:** «Проглатывание небольшое было только одно во вступительной фразе. Больше проглатываний не было, но есть ощущение склейки внутри слов».

### Сводка «Три прогона pacing»

| Pacing | wall_per_chunk | Inter-chunk max | Greeting dropouts | TTS-реплики |
|--------|----------------|-----------------|-------------------|-------------|
| **18ms** (до фикса) | 19 113 us — 4% overflow | 21.7 ms | 209 | 2 проглатывания / 11 реплик |
| **20ms symm.** | 20 985 us — 5% underrun | 22.3 ms | 0 | «каждое слово нестабильно» |
| **19/20 asym** (финал) | 19 980 us — 0.1% | 21.5 ms | 0 | 0 проглатываний |

### Коммит, снятие инструментации, push

- Снята CHUNK-инструментация из `_speak` (~20 строк per-chunk timing logs — временная была)
- Snapshot: `/tmp/voice_asterisk.py.before_cleanup_20260420_071727` на VPS
- `8f3eeaf0` feat(voice): pacing fix + remove CHUNK instrumentation — git diff только 3 строки `0.018 → 0.020/0.019/0.019`, ни residuals от инструментации
- `7f65fadd` docs(voice): document pacing fix 20.04 — VOICE_TECH_STACK_FULL.md (новый файл, 49KB) + VOICE_ARCHITECTURE.md (+2 строки)
- **PROD не тронут** — `/opt/sofia-gpt/` не содержит `voice_asterisk.py`/`yandex_stt_grpc.py`/voice-файлов (подтверждено двумя независимыми grep'ами). Voice stack эксклюзивно на VPS sofia-voice (live) + git origin DEV

### Ключевые архитектурные паттерны (закрепились)

- **Детерминированность дефекта = локализуется через silent test.** Клиент молчит → нет нагрузки, нет STT, нет LLM — если дефект воспроизводится, он в pipeline `_speak_pcm → AudioSocket → Asterisk`. В активном звонке 11 компонентов работают одновременно, фильтр не даёт найти виновника. В silent test — 1 компонент. Переход с «активный звонок с инструментацией» на «silent test с curl-сравнением» сократил диагностику с 2 часов до 20 минут
- **Байтовая корреляция source vs MixMonitor** — объективный инструмент для dropouts в audio pipeline. Результат 0.034 vs 0.987 даёт однозначный ответ без прослушивания Сергеем. Применимо везде где есть «проходит ли сигнал через промежуточный буфер без потерь»
- **Асимметричный фикс под разные режимы одного паттерна** оправдан когда разница event loop overhead measurable (600us vs 850us). Не рефакторинг — две цифры вместо одной
- **«Дешёвая диагностика перед любой правкой кода» снова прошла** — A/B через curl (30 мин) сразу исключил Yandex TTS, сэкономил 2 дня на inline-48kHz refactoring

### Обнаруженные побочные проблемы

- **VPS `/opt/sofia-voice/` не git-tracked.** Правки напрямую на VPS (как делали сегодня snapshot-backup'ами) живут без истории. Workflow-риск: если не синхронизировать в DEV после каждой правки, следующий DEV→VPS scp деплой молча перезапишет. Сегодня синхронизировал финальное состояние в коммите `8f3eeaf0` — корректно. **P2 backlog:** либо правила «воссегда сначала DEV, потом scp», либо git init на VPS с remote в origin
- **yandex_stt_grpc.py и dial.py** идентичны DEV и VPS — drift отсутствует (хороший signal)
- **Silent-test звонок `b3cd88c8` показал одно небольшое проглатывание во вступительной фразе** даже с 20ms в `_speak_pcm`. Причина: greeting total=12856ms на 12.4s audio = 3.5% underrun за 12 секунд. Оставлено как acceptable (на слух редко и не мешает); если критично — можно `_speak_pcm=0.019` но риск вернуть overflow

### Открыто в следующую сессию

**🟡 «Склейки внутри слов»** (carry-over из 20.04):

Pacing-фикс убрал проглатывания/дропы, но осталась шероховатость на стыках слогов в TTS-репликах. Не dropouts (нули не появляются), а artefacts waveform phase.

**Бесплатный первый шаг** — Сергей прослушивает уже скачанные A/B файлы на Mac:
- `~/projects_claude/Sofia/pilot_recordings_18_04/call_8ad55f5b_reply5_baseline.wav` (Alena 8kHz production)
- `call_8ad55f5b_reply5_48k.wav` (Alena 48kHz → soxr → 8kHz)
- `call_8ad55f5b_reply5_jane.wav` (другой голос, тот же текст)
- то же для `reply8_*`

**3 возможных исхода:**

1. **48k чище** → Sprint Contract на inline `48kHz→soxr` в `synthesize_tts_yandex` (+150мс latency, правка ~20 строк)
2. **Все одинаковые** → физика 8kHz канала PSTN/G.711. В этом стеке не улучшить. Accept as-is
3. **jane чище** → `YANDEX_TTS_VOICE=jane` env-переключатель (бесплатно), но ребрендинг голоса Sofia

Дополнительно можно проверить: `speed=1.0` vs текущий `1.1` (time compression артефакты в TTS).

**🟢 Второй заход пилота** (после подтверждения фикса живыми звонками):
- Сергей делает 2-3 живых звонка с фиксом, подтверждает качество
- Зовём тестеров (5-6 × 5-6 звонков) для продолжения пилота
- Собираем 20+ записей с чистым pacing для финальной валидации RIZALTA
- Если всё ок — RIZALTA готов к реальному обзвону

### Deploy details

- **sofia-voice**: systemctl active, последний рестарт 07:18 UTC после cleanup CHUNK-инструментации, PID 9266
- **Snapshots в /tmp** (VPS, оставлены для rollback до ребута):
  - `voice_asterisk.py.before_instr_20260420_041752` (md5 `d677c89c9a9242f3ff923350954abde3`) — pre-instrumentation
  - `voice_asterisk.py.before_pacing_20260420_064354` (md5 `f3104a07d799aaf9e31e5371ec4a75c6`) — pre-20ms fix
  - `voice_asterisk.py.before_asym_20260420_070119` — pre-19/20 asymmetric
  - `voice_asterisk.py.before_cleanup_20260420_071727` (md5 `dd3d2ad9562bf5d579486d25447317a2`) — pre-cleanup CHUNK instr
- **Финальный md5 на VPS:** `ae958c66d79797ab439b14be1d162d0b`
- **Git DEV**: `8f3eeaf0` feat + `7f65fadd` docs, pushed в origin

### Docs Updates

- **docs/VOICE_TECH_STACK_FULL.md** (новый, 49KB) — полный технический стек от SIP до клиента. 10 разделов, 19 шагов pipeline, 25 параметров с `file:line` ссылками, diagnostic команды, навигация по коду
- **docs/VOICE_ARCHITECTURE.md** — блок «Pacing fix (20.04)» после таймингов с объяснением асимметрии

---



### TL;DR

После утреннего pacing-фикса прошла вторая серия спринтов: (A) RIZALTA промпт v4.3 с ценами + порогом входа + фактологическими правками, (B) A/B эксперимент TTS speed 1.1→1.0→1.2 с регенерацией cached greeting трижды, (C) синхронизация hardcoded greeting text в `voice_asterisk.py` с v4.3, (D) разведка SIP codec negotiation через Telphin — вывод: G.722 недоступен на уровне провайдера, Stage 2 отменён. Итог: **speed=1.2 зафиксирован** как оптимальный (на live-речи субъективное улучшение), greeting-артефакты остались — требуют отдельного диагностического спринта.

### Хронология коммитов (DEV)

| # | SHA | Subject |
|--:|------|---------|
| 1 | `0cedd8f0` | feat(voice): RIZALTA v4.3 — pricing + entry threshold + fact corrections |
| 2 | `e8cbd0b6` | fix(voice): sync hardcoded greeting with v4.3 prompt (remove 'окупаемостью') |

### Sprint B — RIZALTA v4.3 (pricing + entry threshold)

- `VOICE_SYSTEM_PROMPT_RIZALTA` в `core/pipeline.py` (lines 646-842), md5 `583a977df…` → `e5c7af2e9…`
- Убрано из canonical pitch + 3 few-shot примеров: «окупаемостью от семи лет»
- Добавлено: «Минимальная цена апартамента — пятнадцать миллионов рублей за двадцать два квадратных метра», «Минимальный вход в сделку — четыре миллиона семьсот тысяч рублей»
- Snapshot: `/tmp/pipeline.py.before_v43_20260420_174825` (VPS)
- Задеплоено через scp DEV→VPS, sofia-voice restart, live-звонок подтвердил

### Sprint C/E — YANDEX_TTS_SPEED A/B (1.1→1.0→1.2)

- **Baseline** `YANDEX_TTS_SPEED=1.1` (код default, в .env не было): `greeting_rizalta.pcm` 198318 B, 12.39s, md5 `8e553237…`
- **Speed=1.0** (Sprint C): добавлена строка `YANDEX_TTS_SPEED=1.0` в `/opt/sofia-voice/.env`, PCM регенерирован нативным импортом `voice_asterisk` (скрипт `/tmp/regen_greeting_speed10.py`, использует `synthesize_tts_yandex` + `add_ssml_breaks` из hot path — zero drift). Результат: 205006 B, 12.81s, md5 `fe60bf5d…`. **Non-linear time-stretching** — ожидалось ~13.6s (+10%), получили +3.4%
- **Greeting sync v4.3** (Sprint D): в `voice_asterisk.py:668` заменил hardcoded literal — убрал «и окупаемостью от семи лет», поставил «в год». После регенерации: 181972 B, 11.37s, md5 `e0e97036…`. Snapshot: `/tmp/voice_asterisk.py.before_greeting_v43_20260420_191636`
- **Speed=1.2** (Sprint E): `YANDEX_TTS_SPEED=1.2` в .env, регенерация: 150206 B, 9.39s, md5 `44d25194…`. Сжатие −17.4% от speed=1.0 (против ожидания −16.7% — близко к линейному в эту сторону)
- **Ear-validation Сергея:** speed=1.2 на live-речи даёт субъективное улучшение (меньше «тягучести»), на cached greeting артефакты остались стабильными на всех трёх значениях speed

### Sprint F — SIP codec recon (Stage 1, Stage 2 отменён)

- Текущая конфигурация `/etc/asterisk/pjsip.conf` VPS: `disallow=all; allow=alaw; allow=ulaw`. Snapshot: `/tmp/pjsip.conf.before_codec_20260420_164536` (md5 `c52386700b…`)
- `pjsip set logger on` → 2 тестовых звонка Сергея → `pjsip set logger off`
- **Telphin INVITE offer (идентичен в обоих звонках):**
  ```
  m=audio <port> RTP/AVP 8 0 101
  a=rtpmap:8 PCMA/8000    ← alaw
  a=rtpmap:0 PCMU/8000    ← ulaw
  a=rtpmap:101 telephone-event/8000
  ```
- **G.722 Telphin не offerит.** Asterisk в 200 OK зеркалит тот же порядок, согласован **alaw** (первый общий).
- `core show translation`: slin16→g722 фактически быстрее (6000μs) чем slin16→alaw/ulaw (14500μs), но это неприменимо — G.722 нет в offerе
- **Вывод:** переключение alaw↔ulaw — косметика, оба 64 kbit/s PCM 8 kHz, одна и та же психоакустика G.711. HD-звук через Telphin невозможен без изменений на стороне провайдера. Это **fundamental limit** PSTN через Telphin — документируется и принимается
- **Stage 2 отменён** (перестановка кодеков в pjsip.conf) — нет данных, что это улучшит качество. Снапшот оставлен в /tmp как страховка, rollback не требуется

### Ключевые архитектурные паттерны (закрепились)

- **Read-only разведка как первый этап двухэтапного спринта** — Sprint F разделили на «разведка» (логи SDP через `pjsip set logger`) и «модификация». После разведки решение было отменить модификацию. Спринт не закрыт как «выполнен» — закрыт как «проверено, оказался no-op». Разведочный этап сэкономил правку pjsip.conf, которая дала бы 0 эффекта
- **Native-import регенерация PCM** (`sys.path.insert + import voice_asterisk`) — использует те же `add_ssml_breaks` + `synthesize_tts_yandex` что и runtime hot path. Zero drift от production, гарантирует что cached greeting соответствует точно тому же пути синтеза что live TTS
- **Субъективная ear-validation после объективных метрик** — speed=1.2 снижает PCM на 17.4% (объективно), но финальное решение за ухом Сергея: live улучшилось, greeting не изменился
- **Провайдер PSTN как hard ceiling качества** — до сегодня считали что возможно договориться о HD через кодек. Оказалось: Telphin offerит только G.711 (alaw/ulaw), G.722/Opus не на столе. Потолок SIP-линии — 8kHz narrowband независимо от нашей TTS. Для HD нужна смена провайдера или переход на Over-The-Top (WebRTC/Daily) для конкретных сценариев

### Обнаруженные побочные проблемы

- **scp `-P 2222` port conflict** — при активном алиасе `sofia-voice` в `~/.ssh/config` (port 22) передача `-P 2222` перекрывает алиас и идёт на несуществующий порт. **Правило:** не использовать `-P 2222` вместе с алиасом `sofia-voice`
- **SSH session timeout при load 28** — во время длинной работы на VPS произошёл session hang (auth проходил, channel_open_confirmation не приходил). Сергей рестартанул Asterisk, load упал 28→5, VPS восстановился. Причина load 28 не диагностирована (P2): либо запущенный Silero inference + ffmpeg rotation + gRPC STT race, либо disk I/O
- **Регенерационный скрипт с hardcoded assert** — `/tmp/regen_greeting_speed10.py` содержал `assert va.YANDEX_TTS_SPEED == 1.0`, для speed=1.2 пришлось патчить через sed. Минор

### Открыто в следующую сессию

**🟡 «Greeting PCM playback artefacts» — почему cached звучит хуже live при идентичном transcoding**:

Speed=1.2 дал улучшение на live TTS, но **не** на cached greeting. При том что транскодинг пути одинаковые (оба `_speak_pcm` → AudioSocket → G.711 alaw → Telphin). Гипотезы:
1. **Static file artefacts при повторных воспроизведениях** — что-то в пути чтения файла/передачи чанков, чего нет в live-stream
2. **Silence/breath между `add_ssml_breaks` гранями** генерируется детерминированно в cached, но адаптивно в live (из-за разных начальных условий SSML parser / TTS engine state)
3. **Артефакты ре-воспроизведения PCM, сохранённого при одном прохождении TTS engine**, которые не слышны в live потому что каждый live-синтез идёт через свежий prepare chain
4. **Физический артефакт waveform phase при 8kHz decimation** из greeting_rizalta.pcm именно — live избегает за счёт непрерывного потока

**Бесплатный первый шаг диагностики:** записать через MixMonitor live-синтез того же greeting-текста без cached PCM (выключить cached-load на 1 звонок), сравнить с MixMonitor'ом звонка где греeting пришёл из cached. Если live чистый — причина в cached-path. Если оба грязные — физика 8kHz/G.711.

Отдельный спринт, P1 в BACKLOG.

### Deploy details

- **sofia-voice**: systemctl active, последний рестарт при Sprint E speed=1.2, PID live
- **Snapshots в /tmp** (VPS, оставлены для rollback до ребута):
  - `pipeline.py.before_v43_20260420_174825`
  - `greeting_rizalta.pcm.before_speed10_20260420_190137`
  - `voice_asterisk.py.before_greeting_v43_20260420_191636`
  - `greeting_rizalta.pcm.before_greeting_v43_20260420_191636`
  - `greeting_rizalta.pcm.before_speed12_20260420_192339`
  - `pjsip.conf.before_codec_20260420_164536`
- **Финальный .env VPS:** `YANDEX_TTS_SPEED=1.2` (зафиксировано как оптимальное)
- **Git DEV**: `0cedd8f0` + `e8cbd0b6` pushed в origin (утро), этот session-close коммит (вечер) — не пушить

### Docs Updates

- Этот session-close коммит — `SESSION_LOG.md` (блок session 2) + `BACKLOG.md` (новый P1). Других docs правок нет.

### Sprint G — Asterisk post-mortem (incident 14:56–15:53 UTC)

**Контекст:** во время вечерней серии deploy'ев (4 подряд `systemctl restart sofia-voice` на 14:55/16:02/16:17/16:24 UTC в рамках Sprint B/C/D/E) VPS вошёл в критическое состояние: Asterisk 193.9% CPU (2 ядра в полку), load 27.46, 4 stuck systemd PID в D-state. SSH timeout'ы с основного сервера в 14:55+ UTC. Ликвидация: `systemctl restart asterisk` в 15:53 UTC → load 28→5, sofia-voice сам не трогался. Разведка проведена read-only после восстановления.

**Root cause — orphan AudioSocket channels:**
- Каждый restart sofia-voice во время активного звонка → Python TCP socket (port 9090) умирает
- Asterisk PJSIP-канал остаётся активным с работающим `AudioSocket()` dialplan app
- `app_audiosocket.c` продолжает форвардить RTP от Telphin в dead TCP → tight retry loop с ECONNRESET
- 4 restart'а × N одновременных звонков = несколько orphan'ов → 193% CPU, 79% sys-time
- **Конкретные orphan'ы на момент ликвидации:** PJSIP channels `0x09` и `0x0a` (номера ниже чем у каналов 13-14 UTC — пережили 2+ deploy'ев)
- **Factoid smoking gun:** `asterisk.service: Consumed 1h 56min 44.771s CPU time` при stop'е (2h активной CPU при общем uptime 13ч)
- **Log silence 13:41 → 15:53 UTC (2h 12min)** — Asterisk физически не успевал флашить логи
- **Post-restart баг сохранился:** новый orphan `00000004` в 16:50:54 UTC (уже после ликвидации) — подтверждает что root cause в архитектуре, не в конкретных каналах

**Secondary — kernel PSI bug 6.8.0-110:**
- systemd user-сессии из SSH-логинов (моих retry'ев) застревали в D-state на close() cgroup pressure trigger
- Stack: `__x64_sys_close → __fput → kernfs_fop_release → cgroup_pressure_release → psi_trigger_destroy → kthread_stop → wait_for_completion`
- 4 подтверждённых stuck PID (19335/19664/19820/19902), hung_task trace каждые 2 минуты
- Не источник CPU storm'а (D-state = не потребляет CPU), но источник «13 зомби» в context'е Сергея
- Лечение: kernel upgrade (отложено, P2 backlog)

**Recon Stage 2A (safety net):**
- Targeted hangup синтаксис: `asterisk -rx "core show channels concise" | awk -F'!' '$6=="AudioSocket" {print $1}' | xargs -I{} asterisk -rx "channel request hangup {}"` — Asterisk 20 не поддерживает `hangup like <pattern>`
- Решение 2 файла в `/opt/sofia-voice/bin/`: `hangup_audiosocket.sh` (ExecStop хук) + `load_watchdog.sh` (cron каждые 2 мин, load>15 AND asterisk_cpu>150%, debounce 10 мин, Telegram alert опционально)
- **Блокер Telegram alert:** `TELEGRAM_BOT_TOKEN` + `ADMIN_CHAT_ID` присутствуют в `/opt/sofia-gpt/.env` (main server), **отсутствуют** в `/opt/sofia-voice/.env` (VPS)

**Deploy решения — отложено на P1:** Сергей выбрал не деплоить safety net прямо сейчас. Причины: (1) root cause понят и контролируется дисциплиной «no restart during calls», (2) ExecStop хук во время звонка обрывает активный разговор — цена для пилота неочевидна, (3) watchdog может ложно сработать если пилот выйдет за пределы экспериментальных оценок load. Вернёмся после первых пилотных звонков с реальными метриками.

**Критическое операционное правило на пилот:** НЕ делать `systemctl restart sofia-voice` во время активных звонков. Если нужен hot-patch — сначала `asterisk -rx "core show channels count"`, убедиться `0 active channels`, только тогда restart. Все planned deploy'и — в окне тишины между тестерами.

**Read-only подтверждение:** 0 write-операций на VPS в post-mortem фазе. Все snapshots 20.04 (pipeline/voice_asterisk/greeting_rizalta.pcm × 3/pjsip.conf) живут в `/tmp` до ребута как страховка L1 rollback.

---

## 19.04.2026 — CLAUDE.md разгрузка + BITRIX stage-guard (инцидент Елены)

### TL;DR

3 DEV-коммита + 1 PROD-деплой. Начали с разгрузки документации, закончили закрытием инцидента 19.04 где Sofia трижды перезаписала ASSIGNED менеджера.

- **CLAUDE_MD_SPLIT_v1** (`af11212f`) — CLAUDE.md 57k → 22k (−60 %). Вынесено: «Уроки из ошибок» (36 прецедентов) → `docs/LESSONS_LEARNED.md` (23.8k), voice-архитектура (AudioSocket/Silero/Yandex/Phase1/auto-hangup/MixMonitor/VOICE_PROMPT_MODE) → `docs/VOICE_ARCHITECTURE.md` (14.6k). Summary-блоки с ссылками + scp-команды в Gitpull.
- **BITRIX_LEAD_RESCUE** (разведка) — лид 266638 Elena, +79124753743 (Radist Telegram @Ofira666, SOURCE_ID=397 Atlantis). Sofia трижды финализировала лид через `set_lead_assigned(24932) + BP 152` несмотря на ручной перехват менеджером (ASSIGNED 19622). **Root cause:** Bitrix webhook ONCRMLEADUPDATE не настроен — за 14 дней доступных логов 0 hit на `/api/bitrix/webhook`, `manager_active` ни разу не установился. Endpoint полностью живой (HTTPS 200, Let's Encrypt, nginx proxy в sofia-api.conf, UFW 443 open, POST идентичен на localhost и снаружи). Мяч на стороне Bitrix — нужна подписка от Stetsenko.
- **BITRIX_STAGE_GUARD_v1** (DEV `441dec63`, PROD `7e08e9a6`) — решение инцидента: pull-проверка STATUS_ID перед критичными операциями вместо polling webhook. Функция `get_lead_status(lead_id) -> str | None` (fail-safe: None при любой ошибке API). Встроена в 3 точки: `finalize_lead` (единая точка для всех каналов), `radist_send_reminder` (2 свежих вызова — перед отправкой и перед финализацией после sleep), `_radist_finalize_timeout`. Skip-ветка: `find_user_id_by_lead` → `set_manager_active(True)` → log `[FINALIZE_SKIP|REMINDER_SKIP|TIMEOUT_SKIP]` → return. `update_lead` не проверяет (безопасная операция, только COMMENTS).

### Хронология коммитов

| # | Репо | SHA | Subject |
|--:|------|------|---------|
| 1 | DEV | `af11212f` | chore(docs): split CLAUDE.md — extract lessons and voice architecture |
| 2 | DEV | `441dec63` | feat(bitrix): stage-based manager protection via get_lead_status |
| 3 | PROD | `7e08e9a6` | feat(bitrix): stage-based manager protection via get_lead_status (format-patch из `441dec63`) |

### Инцидент — таймлайн лида 266638 (MSK, 19.04)

| Время | Событие |
|-------|---------|
| 09:15:38 | Тильда создала лид 266638, ASSIGNED=428 |
| 09:15:50 | Sofia привязала radist user -42262997, save original=428 |
| 09:16–09:24 | 4 сообщения клиента + ответы Sofia (студии до 20 млн) |
| 10:24:06 | Sofia напоминание #1 «Elena, не забыли про меня?» |
| **10:39:07** | **finalize #1** → ASSIGNED=24932, BP 152 (workflow `69e4869b`) |
| 11:49 | Клиент вернулся «Нет не интересно» → Sofia ответ |
| **11:49:09** | **finalize #2** → ASSIGNED=24932, BP 152 (`69e49705`) |
| 11:50–11:52 | Клиент ещё 2 сообщения, Sofia отвечает |
| 12:52:01 | Sofia напоминание #2 |
| **13:07:02** | **finalize #3** → ASSIGNED=24932, BP 152 (`69e4a947`) |
| 13:15:31 | Bitrix MOVED_BY_ID=454 (робот BP) |
| 13:19:31 | Менеджер 19622 взял лид, DATE_MODIFY final |

### Ключевые архитектурные паттерны (закрепились)

- **Два независимых слоя защиты от перезаписи менеджера** — (1) push: Bitrix webhook ONCRMLEADUPDATE → `set_manager_active(True)` в web_api.py webhook handler (не работает сейчас — подписка не настроена); (2) pull: `get_lead_status` перед `finalize_lead`/reminder/timeout (деплоили сегодня). Webhook-слой оставлен in-place для будущей defense in depth когда Stetsenko настроит подписку.
- **Fail-safe по умолчанию в сторону не-трогать** — при любой ошибке API (network/timeout/bad JSON) `get_lead_status` возвращает None, caller трактует None как «не NEW» → skip финализации. Приоритет: тишина лучше перезаписи менеджера.
- **Проверка свежая не кешированная** — вторая проверка в `radist_send_reminder` перед finalize после 15-минутного sleep делается отдельным API-вызовом (не реюз первой). Стадия могла поменяться за время ожидания.
- **Split-deploy дисциплина на CLAUDE.md** — разгружали в 2 docs-файла, оставили summary-блоки с явной ссылкой «Полный текст: docs/FILENAME.md». 36 уроков сохранены дословно с SHA/UUID/датами, не перефразированы.

### Обнаруженные побочные проблемы

- Hard-coded `BITRIX_BASE_URL` fallback в `core/bitrix.py:25-28` с устаревшим токеном — работает только при `load_dotenv`. Для живых сервисов ok, ad-hoc скрипты могут silent-fail-safe. P2.
- Сервисы не используют systemd `EnvironmentFile=`, .env грузится внутри Python. Работает, но менее прозрачно. P2.
- PROD origin/main отстаёт на 10 локальных коммитов (by-design, никогда не пушится). Стоит audit-спринт для сверки состава. P3.
- `restore_assigned` в `core/bitrix.py` — dead code, нигде не вызывается. Со stage-guard концептуально не нужен. P3.
- `_radist_finalize_timeout` skip-ветка делает early return внутри `_is_radist_bitrix_session` блока, зеркально очищая `radist_reminder_tasks/sent` pops (как в финальной секции функции).

### Deploy details

- **DEV commit сmoke**: `get_lead_status(266638)` → `"18"` ✓ (совпадает с разведкой Bitrix STATUS_ID=18).
- **PROD deploy**: format-patch clean apply (md5 базы DEV vs PROD совпадал 1:1), 3 сервиса перезапущены (sofia-gpt + sofia-web-api + sofia-radist), 0 ERROR за 2 минуты после рестарта, /api/health HTTP 200, /api/bitrix/webhook HTTP 200.
- **Snapshots L1 rollback**: `/tmp/core_bitrix.prod.before_stage_guard_20260419_115517` + `/tmp/sofia_radist_gateway.prod.before_stage_guard_20260419_115517`.

### Docs Updates

- `docs/LESSONS_LEARNED.md` — новый файл, 36 уроков 21.03–18.04 с полным дословным сохранением.
- `docs/VOICE_ARCHITECTURE.md` — новый файл, полная voice-архитектура с диаграммой серверов.
- `CLAUDE.md` — разгружен с 57k до 22k, summary-блоки на обе новые docs-страницы, Gitpull обновлён (scp для новых файлов).
- **Не обновлялись**: `ORCHESTRATOR_RULES.md` (не было новых правил), memory-файлы (не было значимых профильных изменений).

---

## 19.04.2026 — продолжение: пилот-аудит + TTS A/B + MixMonitor эксперимент

### TL;DR

Вторая часть сессии целиком под голосовой пилот: инвентаризация собранных записей, разведка двух проблемных звонков, A/B-матрица Yandex TTS на прямых curl-ах, эксперимент с отключённым MixMonitor на живом звонке. Код не правился — только наблюдения. Пилот накопил 9 WAV за 8.5ч активности 18.04, после 18.04 17:32 MSK новых звонков 24+ часа нет.

Ключевой вывод дня: **проблема проглатывания слогов и щелчков в аудио Sofia не в Yandex TTS и не в нашем send_audio, а в ресурсах VPS**. A/B показал что все три варианта синтеза (baseline alena 8kHz / alena 48kHz→8kHz soxr / premium jane 8kHz) на тех же фразах звучат чисто. MixMonitor-эксперимент на живом звонке Сергея подтвердил влияние нагрузки — с выключенным MixMonitor стало субъективно немного лучше, но не до конца. Главный подозреваемый к утру 20.04 — **1 vCPU на VPS sofia-voice**.

### PILOT_INVENTORY_19_04

Инвентаризация `/var/lib/asterisk/recordings/` за 18-19.04:
- **9 WAV** (9.98 MB), все за 18.04, папки 2026-04-19 нет. Последний файл — `b2786722-...wav` от 18.04 14:32 UTC (17:32 MSK). За следующие ~24 часа активности sofia-voice нет (journal пустой после 14:32).
- **CDR**: 35 строк в пилот-контекстах за 18.04 (13 inbound from-telphin + 22 outbound-audiosocket). 4 уникальных номера: `+79181011091` (5 звонков, 3 билли=0), `+79189007826` (4 длинных, 310с), `+79160322905` (3 вечерних тестера 197с), `+79113379876` (1 звонок 94с).
- **Gap CDR↔WAV**: 13 inbound vs 9 WAV — MixMonitor добавили в dialplan ~13:20 UTC, 4 ранних коротких inbound без записи (билли 0-5с, потеря минимальна).
- **AUTO_HANGUP**: 14 detect + 14 exec, 0 cancel — 100% happy-path, 14 уникальных UUID.
- **EOU_WAIT (positive n=167)**: median 1035мс ≈ baseline 1036мс (Phase 1 hint работает), p95 1790мс, max 2153мс. 194 строки `eou_wait_ms=-1` — gRPC close markers (P2 backlog — phantom EOU silencing).
- **Ошибки non-STT**: 2 (оба DEBUG «_send_hangup write error: Connection lost» — клиент клал первым, не real error).
- **HALLUC_TRUNCATED**: 6 (anti-halluc штатно), **[END]**: 4 («Всего доброго! [END]»).
- **Cron-ротация**: работает (03:00/03:30 UTC 19.04), 0 конвертаций (все WAV <72h).

### AUDIO_DROPOUT_8a7c4983

Разведка звонка `8a7c4983` (18.04 13:51 UTC, +79189007826, 124с). Сергей слышит проглатывание «безопасном» на 0:19 и «управляющую» на 0:51. Полное соответствие timing: оба артефакта — на стыках длинных слов (инвестиционно|безопасном, через|управляющую) внутри одного SSML-блока без `<break>`, в середине реплики, не в начале.

Факты: Yandex вернул полный PCM (bytes/duration сходятся до сэмпла), `_speak` отправил целиком, 0 событий BARGE-IN/_cancel_playback/HALLUC_TRUNCATED во всём call window. Длительность WAV 123.76с = call_duration 123.8с.

Гипотеза — **(E) Yandex coarticulation artefact**, не наша сторона. Побочное: `_speak` не логирует per-chunk события (невозможно по логам доказать отсутствие underrun внутри реплики), `asyncio.sleep(0.018)` vs frame 20мс даёт постоянный 10% overrun.

### AUDIO_DROPOUT_94ea75b1

Разведка звонка `94ea75b1` (18.04 14:27 UTC, +79160322905, 69.5с). Сергей слышал больше артефактов чем на 8a7c4983.

Найдено конкретное отличие — **1 false-positive BARGE-IN на reply #2**. Silero VAD с threshold 0.5 набрал 200мс (3200 bytes) через 497мс после старта TTS и дёрнул `_cancel_playback`. Reply #2 «Это апарт-отель в Белокурихе, под сдачу через управляющую компанию. Гарантии… Вход от пятнадцати миллионов рублей. Подходит такой формат?» сыграла только 655мс из 10.79с — успело «Это апарт-отель в…», потом тишина 4.7с до следующего user-turn. **10.1с запланированного аудио потеряно**, реплика не возобновляется. Клиент реальный вопрос задал через 4.7с — значит то что VAD принял за речь, речью не было (кашель/TTS-echo на SIP).

Плотность artefact-кандидатов (стыков 2 длинных слов ≥6 букв): 0.46/сек идентична 8a7c4983 — характер текста тот же. Больше артефактов у 94ea75b1 — от BARGE-IN обрезки, не от coarticulation. Звонок изолированный (gap 2:22 до, 2:14 после), параллельных нет. Нагрузочных алертов 0.

Побочное: Silero `SILERO_VAD_THRESHOLD_BARGE_IN=0.5` + 200мс cumulative window на SIP линии даёт false positives (комментарий в коде прямо: «TTS-echo mix on SIP line»). Возможное решение — threshold 0.6-0.7 на TTS-период или удлинить window 200→400мс.

### TTS_AB_MATRIX_v1

Сгенерировано 12 WAV через прямой curl на Yandex TTS API, без изменений production-кода. 4 проблемных текста из пилотных реплик × 3 варианта синтеза = 12 файлов в `/tmp/pilot_recordings_18_04/ab_*.wav`:
- **baseline**: alena 8kHz LPCM (идентично production параметрам из `synthesize_tts_yandex` + `add_ssml_breaks`)
- **48k_downsample**: alena 48kHz LPCM → ffmpeg `aresample=resampler=soxr` → 8kHz WAV (гипотеза что синтез на полной частоте сохраняет транзиенты безударных слогов)
- **jane**: premium голос 8kHz (jane/ermil/zahar — все три пробника 200 OK; выбран jane по умолчанию)

Sanity: все 12 файлов `pcm_s16le / 8000 Hz / 1 ch / 16 bit`. PCM-before downsample в 6× больше baseline (97k→581k для текста A) — подтверждает что синтез был реально 48kHz. После downsample WAV побайтово совпадает с baseline duration (<0.1с delta). API latency: baseline 410мс / 48k 579мс (+169мс) / jane 527мс.

**Вердикт Сергея после прослушивания**: все три варианта звучат **чисто**, проглатывания нет ни в одном. Значит проблема проглатывания слогов **не в Yandex TTS**, а в чём-то между Yandex ответом и ухом клиента на production звонке.

### MIXMONITOR_DISABLE_TEST

Эксперимент с живым звонком Сергея. Гипотеза: MixMonitor пишет смешанный поток на диск синхронно → на 1 vCPU VPS конкурирует за CPU/I/O с AudioSocket send + Silero VAD → `_speak` получает задержки → слышно как проглатывания и щелчки.

Процедура:
1. Snapshot `/etc/asterisk/extensions.conf` (md5 `b17c7d34febde34aa4c1ddf66f670194`) → `/tmp/extensions.conf.before_mixmonitor_disable_20260419_212739`
2. Закомментированы 2 строки `MixMonitor(...)` в `[from-telphin]:14` и `[outbound-audiosocket]:30`
3. `asterisk -rx 'dialplan reload'` — OK, dialplan показал контексты без MixMonitor-шага
4. Asterisk PID 698, sofia-voice PID 161279 — не менялись (только reload, не restart)
5. Живой звонок Сергея на +79310091644 — разговор 1-2 мин про Белокуриху/Атлантис/инвестиции (провоцировал длинные слова)
6. Восстановление: `cp` из snapshot → диff пустой, md5 совпал, `dialplan reload`, MixMonitor вернулся в dialplan на те же priorities (6 в from-telphin, 4 в outbound-audiosocket)

**Субъективный вердикт Сергея**: «немного лучше, но не решено». MixMonitor — часть проблемы, но не вся. Новый симптом, зафиксированный в этом звонке — **щелчки в аудио Sofia** (jitter / CPU contention / I/O stall).

### Основная гипотеза к утру 20.04

**1 vCPU bottleneck на VPS sofia-voice**. Конкуренция за CPU на 1 ядре между:
- Silero VAD inference (singleton под GIL, `intra_op_num_threads=1`)
- gRPC STT stream `yandex_stt_grpc` (bidirectional streaming, continuous)
- `asyncio.sleep(0.018)` TTS pacing в `_speak` (чувствительна к event loop latency)
- MixMonitor I/O на диск (синхронная запись смешанного потока)
- SQLite writes (`save_message`, `client_state`, WAL checkpoint — подозревались ещё 17.04 на звонке 98332baf)

A/B исключил Yandex TTS как источник проглатываний. Эксперимент MixMonitor показал что I/O нагрузка действительно влияет. Следующий шаг — убрать главное ограничение (1 vCPU), тогда в продакшн-like окружении станет видно какая проблема осталась.

### TODO для следующей сессии 20.04

1. **P0 — Апгрейд VPS sofia-voice с 1 vCPU до 2-4 vCPU** (главный кандидат на решение проглатывания + щелчков).
2. Повторный тестовый звонок после апгрейда с MixMonitor **включённым** — сравнить субъективно и по логам.
3. Если после апгрейда проблема останется — инструментация `_speak` per-chunk timing (добавить счётчик `chunks_sent` и `max_sleep_lag_ms` в строку `TTS done`, одна правка).
4. Возможное вторичное: пересмотреть `SILERO_VAD_THRESHOLD_BARGE_IN` 0.5→0.6-0.7 или удлинить cumulative window 200→400мс (false-positive на reply #2 94ea75b1).

### Что изменилось в файлах

- Код: **ничего** (read-only разведки + curl-генерация + временный MixMonitor toggle через cp).
- `/tmp/pilot_recordings_18_04/ab_*.wav` — 12 файлов A/B для прослушивания Сергеем (эфемерно, не в git).
- `/tmp/extensions.conf.before_mixmonitor_disable_20260419_212739` — snapshot VPS-конфига (оставлен для истории).
- `SESSION_LOG.md`, `BACKLOG.md` — эта запись + backlog-перестановки.

---

## 18.04.2026 — полная сессия: Phase 1 (−742мс EOU) + auto-hangup + recording + prompt v4.x + realtime dial.py stream

### TL;DR

Самая продуктивная сессия на voice. **12 коммитов**, **~10-12 часов работы**, 8 подробных docs-отчётов.

- **Phase 1 (VLAT-07-P1)** — добавлен `max_pause_between_words_hint_ms=700` через env. EOU_WAIT median **1778 → 1036 мс** (−742 мс, −42 %), p95 **2148 → 1446 мс**. Targets оркестратора (median ≤1500, p95 ≤2000) hit с margin.
- **Auto-hangup после farewell** — hybrid keyword + [END] marker, gate `VOICE_PROMPT_MODE=rizalta`. Исправлен pre-existing [END]-handler bug (swap order + anchor endswith).
- **Call recording** — MixMonitor в обоих dialplan-контекстах, cron 72h WAV→Opus, retention 30д. Inbound тест: 792 KB WAV / 49.5 с / обе стороны audible (−18..−21 dB per 5-s window).
- **RIZALTA prompt v3 → v4.2** — 3 итерации: вариативность связок (v4), fix stress-problematic phrases (v4.1), natural phrasing (v4.2).
- **dial.py realtime streaming** — journalctl -f в терминал, USER/SOFIA/AUTO_HANGUP с [HH:MM:SS].
- **EOU instrumentation** — per-turn `EOU_WAIT uuid=... eou_wait_ms=N` в логах.
- **yandex_stt_grpc.py sync в DEV git** — устранён scp-only drift (P2 backlog item).

### Хронология коммитов (12, в порядке)

| # | SHA | Subject |
|--:|------|---------|
| 1 | `296505c2` | chore(voice): sync yandex_stt_grpc.py from VPS (scp-workflow since Phase 2A, 17.04) |
| 2 | `d2f875d1` | feat(voice): add eou_wait_ms instrumentation in yandex_stt_grpc.py (VLAT-07 prep) |
| 3 | `393eb062` | feat(voice): Phase 1 — max_pause_between_words_hint_ms via env (VLAT-07-P1) |
| 4 | `60f62916` | docs(voice): Phase 1 results — hint=700ms A/B vs baseline |
| 5 | `ffcde20e` | feat(voice): RIZALTA v4 — variability in bindings (human-sounding) |
| 6 | `f6f750c1` | docs(voice): RIZALTA v4 live-test results — keep decision |
| 7 | `ab90940b` | feat(voice): RIZALTA v4.1 — replace stress-problematic phrases |
| 8 | `b78fe04c` | feat(voice): auto-hangup after Sofia farewell (RIZALTA only) |
| 9 | `19102904` | fix(voice): [END] handler — run hallucination filter first, anchor to end-of-text |
| 10 | `110a6a3c` | chore(voice): RIZALTA v4.2 — natural phrasing for two variants |
| 11 | `4ce5881b` | feat(dial): realtime transcript streaming to terminal |
| 12 | `19a49fa6` | feat(voice): call recording — MixMonitor + 72h→Opus rotation |

### Метрики ДО и ПОСЛЕ Phase 1

| Metric | Baseline (утро, 22 turns) | Post-Phase-1 (21 turns) | Δ |
|--------|---:|---:|---:|
| median EOU_WAIT | **1778 мс** | **1036 мс** | **−742 (−42 %)** |
| p90 | 2051 | 1177 | −874 |
| p95 | 2148 | 1446 | −702 |
| max | 2153 | 1675 | −478 |
| short category median | 1924 | 1011 | −913 (−47 %) |
| medium category median | 1790 | 1145 | −645 (−36 %) |
| long category median | 1662 | 1076 | −586 (−35 %) |

### Ключевые архитектурные паттерны (закрепились)

- **Env-gated rollback на каждую фичу** — Phase 1 (`YANDEX_MAX_PAUSE_HINT_MS`), auto-hangup (`AUTO_HANGUP_ENABLED`), streaming (`STREAM_TRANSCRIPT`). L0 rollback = `sed` на `.env` + `systemctl restart` (<30 с). L1 = snapshot в `/tmp/*.before_<ts>`. L2 = git reset. **Никогда не заходили за L0 в этой сессии.**
- **Pre-existing [END] ordering bug** — `if "[END]" in answer_text` substring match runs BEFORE hallucination filter → LLM emit `[END]` в hallucinated tail, filter strips tail but `state.dialog_finished` уже contaminated. Fix: swap + anchor `endswith`. Протестирован живьём: false-positive исчез (call f184c7be был последним incident). **Тот же bug лежит в text-path `core/pipeline.py:319-326` для PROD** — P1 backlog.
- **Snapshot-before-scp discipline** — каждый deploy на VPS предваряется `cp /opt/sofia-voice/X /tmp/X.before_<timestamp>`. L1 rollback восстанавливается одной командой cp.
- **Keyword matching scoped to tail** — farewell keyword match в последних 80 chars response, не во всём тексте. Prevents mid-sentence false positives.
- **Prompt-level refusal over-eagerness distinct from infrastructure** — call `f8d41815` показал что Sofia входит в Категорический отказ branch на ambiguous user text («это вот теперь не с вами говорить»). Не bug auto-hangup, а prompt-level sensitivity. Fix option: двойное подтверждение refusal (как в Atlantis prompt: «дважды чётко отказался»).
- **Testers ≠ Sergey phone hardware issue** — tester vs Sergey differential показал что phone/hardware identical; разница в attention level (testers multitask, Сергей focused). STT partials clean, TTS-echo guard works, no HALLUC_TRUNCATED — не инфра bug.

### Созданные docs (8 reference files в `docs/`)

| File | Purpose |
|------|---------|
| `VOICE_LATENCY_AUDIT_2026-04-18.md` | 29 KB — Latency audit, 8 optimisations VLAT-01..08 with gain/effort/risk |
| `VLAT_07_DEEP_DIVE_2026-04-18.md` | 25 KB — Phase 1/2/3 breakdown для max_pause_hint |
| `EOU_BASELINE_2026-04-18.md` | 16 KB — Baseline 22 turns, 4 calls, per-category medians |
| `PHASE1_RESULTS_2026-04-18.md` | 16 KB — A/B Phase 1, −742 ms median, 1 regression |
| `PROMPT_V4_RESULTS_2026-04-18.md` | 9 KB — RIZALTA v4 live-test, keep decision |
| `CALL_LIFECYCLE_RECON_2026-04-18.md` | 18 KB — Task A (ringing 20с) + Task B (auto-hangup) recon |
| `NOISE_CASE_POSTMORTEM_2026-04-18.md` | 16 KB — 3-call triage +79160322905 tester failures |
| `TESTER_VS_SERGEY_DIFF_2026-04-18.md` | 13 KB — гипотеза «phone HW» опровергнута → attention level |

### Найденные но НЕ исправленные проблемы (на P1 backlog)

- **Text-path [END] handler в PROD `core/pipeline.py:319-326`** — тот же баг что мы fix'ed в голосе (`19102904`), но для text channels (Telegram/Radist/web). В PROD репо `/opt/sofia-gpt/`. Влияет на Atlantis inbound когда LLM галлюцинирует `[END]` в tail — false dialog_finished. Критично для text pipeline.
- **Option A RIZALTA prompt hardening** (из NOISE_CASE_POSTMORTEM) — добавить «двойное подтверждение отказа» в Категорический отказ branch. ~2 часа. Запустить если пилот-серия покажет повторные false refusals.
- **Audio dropouts** — Сергей слышит что Sofia иногда «глотает слова» в inbound тесте. Гипотезы: TTS pacing `asyncio.sleep(0.018)` под CPU нагрузкой / prompt-artefacts. Evidence в логах чистый (0 RTP warnings, 0 underrun). Catch в WAV при пилоте.
- **1 vCPU bottleneck** — VPS 1 ядро, Silero singleton под GIL. Safe concurrent calls: 3-4. Пилот планируется sequential → OK. P2: upgrade 2-4 vCPU.
- **Белокуриха misstress** — Yandex Alena ставит ударение на предпоследний слог. P1 backlog: проверить U+0301 acute accent in prompt или Yandex custom pronunciation dictionary.

### Next steps (для завтра)

1. **Пилот-серия** — Сергей ожидает 5-6 тестеров × 5-6 inbound звонков = ~30 calls на +79310091644. Инструкции тестерам: тихая комната, focused, не одновременно (1 vCPU limit). MixMonitor активен — все будут записаны.
2. **Post-pilot analysis** (следующая сессия):
   - Прослушать все WAV (Сергей) + cross-ref с journalctl
   - Rate drop-offs, Sofia-initiated refusals, audio dropouts
   - Решить: Option A prompt hardening YES/NO based on repeat of `f8d41815`-class falses
   - Audio dropout diagnosis если подтвердится в WAV

### Side note: userMemories оркестратора устарели

userMemories в Claude.ai упоминают:
- kimi-k2 как active LLM (давно YandexGPT)
- ElevenLabs Flash v2.5 (давно Yandex Alena)
- Ничего про сегодняшние Phase 1, auto-hangup, recording, streaming, prompt v4.x

**Требуется обновление через `memory_user_edits` в начале следующей сессии.** Claude Code не имеет доступа к этому инструменту, делает сам оркестратор.

### Feature flags / состояние сервиса на конец сессии

```
STT_MODE=grpc
YANDEX_STT_EOU_MODE=high
YANDEX_MAX_PAUSE_HINT_MS=700      ← Phase 1
AUTO_HANGUP_ENABLED=true          ← Auto-hangup
VOICE_PROMPT_MODE=rizalta          ← gate для auto-hangup
VOICE_VAD_PROVIDER=silero
VOICE_PROVIDER=yandex
VOICE_TTS_PROVIDER=yandex
STREAM_TRANSCRIPT=true (dial.py default, не .env)
MixMonitor: active в обоих dialplan контекстах
```

Сервис active, banner: `Pipeline: Yandex STT (GRPC, EOU=high, hint=700ms) -> YANDEX TTS | Mode: rizalta, auto_hangup=on`.

### Post-session addendum — первые пилотные inbound звонки (18.04 вечер)

После session close (df9015a6, 13:24 UTC) Сергей запустил первых тестеров на inbound +79310091644:

| UTC | MSK | UUID | Phone | billsec | WAV size |
|-----|-----|------|-------|--------:|---------:|
| 14:24:20 | 17:24:20 | `e561a7c6-9535-4508-8daa-6443f28bc0d1` | +79160322905 | 73 с | 1.11 MB |
| 14:27:55 | 17:27:55 | `94ea75b1-94b0-49b1-95d5-3aa0c8dbccd7` | +79160322905 | 70 с | 1.06 MB |
| 14:31:18 | 17:31:18 | `b2786722-a448-494e-937d-dc739e78a674` | +79160322905 | 54 с | 848 KB |

Все 3 записаны MixMonitor'ом (deploy сегодня утром, `19a49fa6`). Сергей скачивает WAV для прослушивания — первый real-world acoustic verification. Transcripts для inbound не создаются dial.py (он только outbound), но SQLite `sofia_voice.db messages` содержит все turns — на следующей сессии нужен `transcript_dump.py <UUID>` из P2 backlog чтобы вытащить текст.

Сервис всё так же active, Phase 1 intact, auto-hangup active. **Пилот живой.** Полный анализ откладывается на следующую сессию — прослушивание + cross-ref с journalctl даст реальный feedback для Option A решения.

---

## 17.04.2026 — OUTBOUND_DIALER_v1: dial.py + [outbound-audiosocket] context

**Сделано:**

Добавлена возможность инициировать исходящий звонок через Asterisk — Sofia звонит клиенту, proigрывает RIZALTA-greeting, ведёт разговор. Первая версия — один звонок на вызов скрипта, stateless.

### Компоненты

- **Asterisk dialplan `[outbound-audiosocket]`** в `/etc/asterisk/extensions.conf` — extension `s` с `Set(CALL_UUID=...)` + `AudioSocket(${CALL_UUID},127.0.0.1:9090)` + `Hangup()`. Зеркало `[from-telphin]`. UUID через `${SHELL(cat /proc/sys/kernel/random/uuid)}` — AudioSocket app требует RFC-4122 формат, `${UNIQUEID}` (`<epoch>.<counter>`) не подходит.
- **`/opt/sofia-voice/dial.py`** — нормализация телефона (+7/8/7/10-digit формы) → `channel originate PJSIP/<phone>@telphin-endpoint extension s@outbound-audiosocket` через `asterisk -rx` → capture uniqueid через `core show channels concise` → CDR polling (primary: по uniqueid; fallback: по timestamp+dcontext=outbound-audiosocket) → JSONL запись в `/var/log/sofia-voice/outbound_YYYY-MM-DD.jsonl` → exit code per disposition (0=ANSWERED billsec≥5, 1=NO ANSWER/BUSY/short-hangup, 2=invalid input, 3=FAILED). Таймаут 600с (покрывает 3-5 минут реального разговора).
- **UFW** — добавлено правило `5090/udp ← 213.170.84.105` (второй Telphin IP из `pjsip show endpoints`).

### Live test `98332baf-c2d8-4d0a-829a-b6bc598e4e4b` (CDR uniqueid `1776429384.330`, 119с)

`python3 /opt/sofia-voice/dial.py 89181011091` → Сергей получил звонок с номера 79310091644 → услышал RIZALTA-greeting → 7 полноценных turns разговора → нормальный barge-in на turn 4.

Per-turn тайминги Yandex EOU=high: EOU wait медиана ~1920мс, LLM 543-940мс, TTS first chunk 130-227мс. Phone AEC: 0 false partials во время TTS. Stream open TTFB: **1мс** (быстрее чем на inbound 4ad65942 где было 2мс). Длинная фраза на turn 7 (117 симв / 22 partials / одна EOU) склеена целиком.

### Баги по пути и фиксы

1. **Первый попыток v1:** `${UNIQUEID}` в AudioSocket → `ERROR: Failed to parse UUID '1776428982.328'` (AudioSocket требует 128-bit UUID, не Asterisk-шный `epoch.counter`). Канал мгновенно hangup'нулся billsec=0. **Фикс:** вернуть SHELL-генерацию UUID зеркально с inbound context'ом. Revert коммит не понадобился — правка в том же спринте.
2. **dial.py не ловил uniqueid** на втором (успешном) live test'е: `find_new_telphin_uniqueid` polls 5 секунд после originate, но реальный channel setup занял ~24с (ring + answer). Window промазал, fallback по `phone in channel` не сработал потому что CDR outbound-row вообще не содержит номер (src=пусто, channel=endpoint-name без цифр). **Фикс:** fallback matcher теперь сравнивает CDR row start timestamp >= ts_start − 5s tolerance + dcontext=outbound-audiosocket. Ретроактивно проверено на тот же звонок — находит `1776429384.330` с disposition=ANSWERED billsec=119. Живой re-test не понадобился (правка только в matching-логике, hot path звонка не тронут).

### Побочные наблюдения (в backlog)

- **Turn 4 9.3с blocking** — в звонке 98332baf turn 4 между `🎤 USER` log и LLM t0 прошло ~9 секунд. LLM сам был 834мс (быстро), stream_voice_response нормальный. Подозрение — SQLite `save_message()` WAL checkpoint или file lock. **Одна точка данных, не воспроизводимо.** В P1 backlog: `save_message() timing instrumentation` — добавить per-call ms логирование, дождаться повторения на 5+ звонках перед слепым фиксом.
- **Два Telphin IP'а в identify** — `46.229.221.93/32` (известный, уже в UFW) + `213.170.84.105/32` (новый, добавлен сегодня). В будущем мониторить `pjsip show endpoints` на появление третьего IP.

### Коммиты (17.04 вечер)

- FIX_DATE follow-ups + финализация сессии (`a64b3354`)
- Outbound v1 (следующий коммит этого session-close) — `dial.py` + `asterisk/extensions.conf` + SESSION_LOG + BACKLOG

### Последующие fix'ы (после коммита 96b68ae7)

В ту же сессию выявлены и исправлены два баг-а в matching-логике dial.py:

1. **`find_cdr_fallback` искал по `phone in channel`** — не работает для outbound (CDR row не содержит номер, только endpoint-имя). Fix: сверять по `CDR.start >= ts_start − 5s` + `dcontext=outbound-audiosocket`. Retroactively проверено на звонке `1776429384.330` — matcher находит корректно. Fallback запускается в `wait_for_cdr` ВСЕГДА (не только при uniqueid=None), чтобы компенсировать следующий баг.

2. **`cdr_line_count` off-by-N** — считала `\n` байты в файле через `open("rb")`, но CDR rows могут содержать embedded newlines в quoted CallerID полях. На 17.04 18:00 UTC: 256 newlines vs **254 csv rows** — расхождение 2. `initial_lines = cdr_line_count()` → `rows[initial_lines:]` давал **пустой slice** → fallback scan window пустой → dial.py висел до timeout. Fix: `cdr_line_count` теперь делает `sum(1 for _ in csv.reader(f))`. Unit-tested 4 сценария (consistency, fresh-row match, empty slice when no new rows, reproduction of old bug).

3. **`captured_uniqueid` в JSONL** — добавлено поле для post-mortem: что вернул concise parser. Сравнивается с `uuid` (реальный CDR uniqueid) — расхождение подтверждает P3 задачу «concise parser field index bug на Asterisk 20». Fallback sempre compensated.

4. **Realtime status + post-call transcript** — `dial.py` теперь выводит `[HH:MM:SS] Originating → Ringing → Answered → Ended` по мере polling'а `core show channels concise` (substring-match на `!Up!` / `!Ring*!`, не по индексу — чтобы не попасть в P3 concise-parser bug). После summary печатается транскрипт из SQLite — SELECT по `chat_id = md5(audiosocket_uuid)[:8] mod 1M + 9_500_000` (зеркальная формула `voice_asterisk.py:125`, дублирование отмечено P3 `Extract chat_id derivation to shared module`). Транскрипт пишется в `/var/log/sofia-voice/transcripts/transcript_<UUID>.txt` + выводится в stdout как `[MM:SS] SOFIA:/USER: <text>` (offset от `call_start`). JSONL дополнен полями `transcript_path` и `message_count`. Unit-тест на исторических `dfc4aee9` и `86c53f97` — 7 и 1 сообщений соответственно, формат корректен.

Test звонки в сессию: `98332baf` (19:15 live — нормальный UX, но dial.py висел → убит), `dfc4aee9` (17:15 retest первого fix — dial.py висел → убит), `86c53f97` (17:41 retest второго fix timestamp fallback — dial.py всё равно висел из-за cdr_line_count bug → убит). **Live re-test после csv-row-count fix не делаем** — `csv.reader` поведение детерминировано, unit-test achieves same confidence без лишних звонков Сергею.

### Следующее (P1) — уточнённые приоритеты к концу сессии (коммит `17470b15`)

1. **🔴 SSH alias sofia-voice починить** — блокер для любых VPS-операций, первым делом
2. **🔴 Запись звонков (MixMonitor WAV)** — дополнение к dialplan перед живой серией, без WAV нет post-mortem
3. **🔴 Начать пилотную живую серию RIZALTA** — 10-20 реальных звонков для сбора UX-метрик
4. **Structured turn_metrics JSONL** — инструментация `voice_asterisk.py` (события turn_start/stt_done/llm_done/tts_*/barge_in)
5. **Post-barge-in ack timer** — отложено до данных #3
6. **Outbound v2** (batch + retry + Bitrix) — после v1 stabilization
7. **`save_message()` timing instrumentation** — диагностика 9.3с blocking'а (98332baf turn 4)

---

## 17.04.2026 — YANDEX_STT_V3_EOU_TUNING (Phase 2D): EouSensitivity=HIGH через env-switch

**Сделано:**

Один env-switch `YANDEX_STT_EOU_MODE=default|high` добавлен в `yandex_stt_grpc.py::YandexSTTStream` и `voice_asterisk.py`. При `high` — в `StreamingOptions` прокидывается `EouClassifierOptions(default_classifier=DefaultEouClassifier(type=EouSensitivity.HIGH))`. Live-тестирован звонком `4ad65942`.

### Изменения

- `yandex_stt_grpc.py` (+14 строк): параметр `eou_mode: str = "default"` в `__init__`, warning на unknown значение с fallback на default, `eou_classifier` в `_request_iterator` с HIGH/DEFAULT в зависимости от параметра.
- `voice_asterisk.py` (+5 строк): env-const `YANDEX_STT_EOU_MODE`, передача в `YandexSTTStream(..., eou_mode=...)`, startup-log `Pipeline: Yandex STT (GRPC, EOU=high)`.
- `.env` на VPS: добавлена строка `YANDEX_STT_EOU_MODE=high`.

### Live test звонок `4ad65942` (83.0с, 5 turns + 3 barge-in)

| Метрика | 4b109925 (EOU=default) | 4ad65942 (EOU=high) | Δ |
|---|---|---|---|
| EOU wait медиана (чистые измерения) | 2240мс | **1920мс** | −320мс |
| EOU wait короткая фраза («все спасибо») | 2168мс | **1545мс** | **−620мс** |
| User pause от stable text → TTS first | 3099мс | **2119мс** | **−980мс** |
| Длинная фраза с микропаузами — 1 final? | ✅ | ✅ (100 симв, 32 partials) | без регресса |
| Длинная 109 симв с повторами | ✅ | ✅ (23 partials, 1 final) | без регресса |
| Barge-in #1 latency | 1404мс | 1252мс | −152мс |
| Barge-in clean recovery | BI#1, BI#3 ok; BI#2 deadlock | BI#1, BI#2 ok; BI#3 deadlock | сопоставимо |
| is_broken | False | False | — |
| ERROR/Exception | 0 | 0 | — |

Sergey subjective: «работает, ура».

### Rollback

Одной строкой `.env` без правки кода:
```
sed -i "s/^YANDEX_STT_EOU_MODE=high/YANDEX_STT_EOU_MODE=default/" /opt/sofia-voice/.env && systemctl restart sofia-voice
```

### Побочные находки

- **E402 в `yandex_stt_grpc.py:31`** (pre-existing от Phase 2A — import после `sys.path.insert`). flake8 на этом файле не запускался раньше (нет pre-commit для VPS-only модуля). Добавил `# noqa: E402` по образцу `voice_asterisk.py:39-41`. Не scope creep — project pattern.
- **DEV продолжает не содержать `yandex_stt_grpc.py`** — правка применена только на VPS через scp-workflow. В git commit войдёт только `voice_asterisk.py`. Гэп известен с Phase 2A, закрывается отдельной P2-задачей (см. BACKLOG).

### Следующие шаги

Осталось **«Post-barge-in ack timer»** (P1) — 3-секундный таймер после `_process_turn` finally при barge-in exit, проговаривающий «я вас слушаю?» если новый turn не начался. Решает deadlock-класс BI#2 в 4b109925 и BI#3 в 4ad65942. Независимо от STT-mode.

Deadlock в BI#3 4ad65942 (9.3с silence) подтверждает что Phase 2D не решает эту проблему — требуется отдельный таймер-механизм.

---

## 17.04.2026 — YANDEX_STT_V3_INTEGRATION_v1 (Phase 2B+2C): gRPC стриминг в production под STT_MODE=grpc

**Сделано:**

Интегрирован gRPC STT v3 streaming в `voice_asterisk.py` двумя раундами — Phase 2B (bifurcate через method-pointer) и Phase 2C (continuous streaming + TTS-echo guard). STT_MODE=grpc задеплоен и live-тестирован звонками `fe7eed5c` и `4b109925`.

### Phase 2B — bifurcate method-pointer

- **Архитектурное решение (из Build Report YANDEX_STT_V3_BIFURCATE_ADVICE):** вариант (d)-light. В `__init__` `AudioSocketCall`: `self._process_audio = self._stream_audio_to_grpc` при STT_MODE=grpc, иначе `_process_audio_vad`. В `_handle_packet` AUDIO-ветка — `await self._process_audio(payload)` без if. REST-путь при STT_MODE=rest **байт-в-байт** идентичен тому что работал до Phase 2B.
- **`_process_turn` — одна функция с параметром** `text_override: str | None = None`. При REST (`text_override=None`) идёт через `transcribe_audio`, при gRPC — получает готовый текст из `_on_grpc_eou` callback и пропускает STT-шаг. 81 строк LLM+TTS+timings shared, дублирование исключено.
- **Новые методы в `voice_asterisk.py`:** `_open_grpc_stream` (19 строк), `_stream_audio_to_grpc` (23), `_on_grpc_partial/final/eou` (36), `_fallback_to_rest` (8). Plus 18 полей в `__init__` + dispatch (7 state + method pointer). Итого **+137 строк** к файлу.
- **Fallback:** при `_stt_stream.is_broken=True` → `_fallback_to_rest()` переприсваивает pointer на `_process_audio_vad`, до конца звонка REST. Логируется одноразово.
- **Live test Phase 2B (звонок `fe7eed5c`, 107.7с, 7 turns):**
  - gRPC stream ready за 2мс (TLS handshake)
  - Все turn'ы обработаны без ошибок, 0 broken-state событий
  - Длинная фраза «а так хорошо а какая говорите минимальная цена не услышал» (2 микропаузы!) склеена в **один final** — главный выигрыш gRPC vs REST. В REST эта фраза 100% порезалась бы на VAD_SILENCE=500мс.
  - Barge-in + продолжение: клиент договаривал после перебивания, Yandex подхватил новую фразу полностью (в REST тот же сценарий дал 8.36с deadlock на звонке 71b461f4 — buffer discard + MIN_BYTES).
  - **Регрессия:** user pause **+1.2с медиана** по сравнению с REST, целиком из-за Yandex server-side `DefaultEouClassifier` wait ~2240мс (vs нашего VAD_SILENCE_THRESHOLD=500мс).

### Phase 2C — continuous stream + TTS-echo guard

**Триггер:** Sergey в Phase 2B тесте пропустил продолжение клиента после первого ответа Sofia — при `_is_responding=True` `_stream_audio_to_grpc` return'ил без отправки в stream. Замер latency первого partial (preparation task YANDEX_STT_V3_PHASE_2C_PREP) показал: Yandex-only barge-in слишком медленный (~1100мс estimated), Silero нужен как детектор.

**Решение — гибрид:**

- **Stream всегда принимает audio** — удалена блокировка `if self._is_responding: return` из `_stream_audio_to_grpc` (строки 745-748). Фреймы текут непрерывно весь звонок.
- **TTS-echo guard в `_on_grpc_*` callbacks:** `if self._tts_playing and not self._cancel_playback: return` в каждом из трёх event handler'ов.
  - `_tts_playing=True, _cancel_playback=False` — активное Sofia TTS без barge-in → события игнорируются как TTS-echo
  - После Silero barge-in confirm (`_cancel_playback=True`) → guard снимается → все события обрабатываются
  - Во время greeting (12.4с cached PCM) guard тоже активен — защита на случай если Yandex начнёт hallucinate
- **`_on_grpc_eou` — buffer intact в echo-ветке:** при срабатывании TTS-echo guard **не чистим** `_grpc_final_buffer`, чтобы при последующем легитимном EOU текст был на месте.
- **Компромисс**: первые ~200мс речи клиента до Silero confirm игнорируются как potential echo. Зафиксировано явным NOTE-комментарием в `_on_grpc_partial`. Это **лучше** Phase 2B (теряли 700мс = 200мс confirm + 500мс cooldown).

**Добавлено:** +14 строк в файл (4 изменения × 3 callback'а + guard в `_stream_audio_to_grpc` минус старый блок). Final size: 1183 строки.

**Live test Phase 2C (звонок `4b109925`, 140.3с, 8 turns, 3 barge-in):**

| Событие | Результат |
|---|---|
| TTS-echo в логах | **0 partials** в логе за ~60с кумулятивно активного TTS (guard работает) |
| BI#1 turn 3→4 | Первое слово `[пожалуйста]` чисто, полный текст "пожалуйста еще раз доходность и окупаемость", **1404мс** до первого partial |
| BI#2 turn 5→6 | **Deadlock 7.3с** (pre-existing UX issue: Sergey коротко перебил + ждал ack от Sofia, Yandex не emit'ил EOU на тишину). НЕ регрессия Phase 2C — тот же паттерн в Phase 2B fe7eed5c и REST 71b461f4 |
| BI#3 turn 7→8 | Первое слово `[интересно]` чисто, **1453мс** — такой же clean recovery как BI#1 |
| Yandex EOU wait медиана | **2240мс** — идентично Phase 2B (параметры Yandex EOU не меняли) |
| Длинные фразы с микропаузами | Turn 3: 75 симв., 20 partials, склеены целиком ✅ |
| is_broken | False всю сессию |
| ERROR/Exception | 0 |

### Побочные находки

1. **Phone AEC работает отлично** — 12.4с cached greeting на живой линии дают **0 false partials от Yandex**. Это нерегулируемая нами зависимость (hardware AEC мобильного), но наблюдение стабильное.
2. **Yandex EOU — основной bottleneck пауз.** ~2240мс wait server-side unchanged by continuous streaming. Решается либо `EouSensitivity=HIGH` (один-строчная правка `yandex_stt_grpc.py`), либо `ExternalEouClassifier` (шлём EOU по триггеру Silero VAD endpoint). Обе в backlog (Phase 2D).
3. **Deadlock post-barge-in класс проблем** — pre-existing во всех STT-режимах. Клиент перебивает коротко, ожидает ack от Sofia, Sofia молчит (нет EOU триггера) → 7+ секунд тишины. Решение: таймер в P1 backlog («Post-barge-in ack timer»).
4. **Orphan `/opt/sofia-gpt-dev/yandex_stt.py`** (26.03, Pipecat-специфичный) остаётся как референс. После стабилизации Phase 2C можно удалить — не подключён нигде.
5. **DEV отсутствует `yandex_stt_grpc.py` + `yandex_proto/`** (только на VPS). Phase 2A коммит был docs-only. `voice_asterisk.py` импортирует `from yandex_stt_grpc import ...` — в DEV модуль отсутствует. Не блокер (DEV-файл не исполняется локально, только коммитится). Портбэк на DEV — отдельная follow-up задача.

### Коммит DEV
`feat(voice): Yandex STT v3 gRPC streaming (Phase 2B+2C) — hybrid barge-in Silero + continuous stream to Yandex, TTS-echo guard in event handlers, verified 4b109925`

### Следующее (Phase 2D, P1)

1. **Yandex EouSensitivity=HIGH тест** — одна строка в `yandex_stt_grpc.py::_request_iterator`, добавить `DefaultEouClassifier` с `type=HIGH` в `StreamingOptions.eou_classifier`. Ожидаемый gain: −500-1000мс user pause. Деплой + один тестовый звонок. 30 минут.
2. **Post-barge-in ack timer** — таймер 3с после `_process_turn` finally при barge-in exit; если новый turn не триггернулся → Sofia говорит «я вас слушаю?». Решает deadlock-класс проблем при коротких barge-in. Независимо от STT-mode.

---

## 17.04.2026 — YANDEX_STT_V3_INFRA_v1 (Phase 2A): gRPC-инфра на VPS без интеграции

**Сделано:**

Подготовлена инфра + standalone-модуль STT v3 gRPC streaming на VPS sofia-voice **без** правки voice_asterisk.py. Интеграция (bifurcate в `_handle_packet`) — отдельный спринт Phase 2B.

- **Reconnaissance (Phase 1 YANDEX_STT_V3_RECON_v1, read-only):** собрана полная карта — текущий REST v1 flow, proto-файлы v3 (есть в DEV, нет на VPS), auth Api-Key работает для gRPC, оценка VAD/barge-in logic ~240 строк (не 400+ как в userMemories), 8 open questions для Phase 2B.
- **grpcio 1.80.0** установлен в `/opt/sofia-voice/venv` (protobuf 7.34.1 уже был, совместим).
- **yandex_proto/** скопирован DEV → VPS (`scp -r`), 29 файлов 196K. `sys.path.insert` даёт `from yandex.cloud.ai.stt.v3 import stt_pb2, stt_service_pb2_grpc`.
- **`/opt/sofia-voice/yandex_stt_grpc.py`** создан (185 строк) — `YandexSTTStream` per-call wrapper, callback-based (`on_partial/on_final/on_eou`), без Pipecat-фреймов, без auto-reconnect, `is_broken` property для caller-side fallback. Session config: LINEAR16_PCM / 8000 Hz / ru-RU / general:rc / REAL_TIME.
- **`.env` на VPS:** добавлен `STT_MODE=rest` (default). Переключение в `grpc` — Phase 2B.
- **voice_asterisk.py не изменён** (md5 `7dda8e9f161b21202655bdcd0c899ef6` до и после). sofia-voice.service не перезапускался, работает на REST v1 как прежде.

**Smoke test (реальный API-key + один 320B silence chunk, VPS):**

| Шаг | Результат |
|---|---|
| Импорт `yandex_stt_grpc` + инстанциация с dummy-ключом | ✅ `is_broken=False is_started=False` |
| `start()` с реальным `YANDEX_SPEECHKIT_API_KEY` | ✅ `gRPC stream opened` за 4ms |
| `send_audio(b'\x00' * 320)` + 3с ожидания | ✅ сервер молчит (ожидаемо для тишины) |
| `close()` + событие `eou_update t=0ms` во время teardown | ✅ `is_broken=False` сохраняется — правка `if not self._closed` работает |

Auth подтверждён (никаких UNAUTHENTICATED/PERMISSION_DENIED), TLS handshake + bidirectional stream + callbacks + clean shutdown end-to-end.

**Побочные находки:**

1. **Proto-generated stubs используют голый `from yandex.cloud.ai.stt.v3 import ...`** — требует `/opt/sofia-voice/yandex_proto` в `sys.path` целиком, не `yandex_proto.yandex.cloud...`. Первая попытка импорта через namespace-путь упала `ModuleNotFoundError: No module named 'yandex'` внутри самого stub'а. Фикс: `sys.path.insert(0, os.path.join(basedir, "yandex_proto"))` (как в orphan `yandex_stt.py` из DEV).
2. **Race в `_receive_loop` при teardown:** Yandex прислал `eou_update t_ms=0` после нашего `close()` — recv-task ещё жил, ивент прошёл через callback. В первой версии любая ошибка в recv-loop ставила `_broken=True`, что ложно сломало бы Phase 2B fallback logic при нормальном закрытии. Правка: `if not self._closed: self._broken = True` в обоих except-ветках.
3. **«400+ строк VAD/barge-in»** в userMemories — переоценка. Реально ~240 строк, из которых ~180-210 убирается при Phase 2B (полный список — в Build Report YANDEX_STT_V3_RECON_v1).
4. **Orphan `/opt/sofia-gpt-dev/yandex_stt.py`** (Pipecat-специфичный, 26.03) остаётся — пригодится как референс до Phase 2B, потом можно удалить.

**Следующее (Phase 2B — интеграция):**

1. Bifurcate в `voice_asterisk.py::_handle_packet`: при `STT_MODE=grpc` открывать `YandexSTTStream` на UUID-пакете, стримить фреймы туда вместо накопления в `_speech_buffer`. При `STT_MODE=rest` — поведение дословно как сейчас (rollback fidelity).
2. Barge-in: Silero остаётся как early-warning; EOU — с сервера Yandex.
3. Fallback: при `stream.is_broken` → переключение на REST `transcribe_audio()` для остальных turn'ов звонка.
4. A/B на живом звонке — `general:rc` на 8kHz vs REST v1 качество и латентность.
5. Эффорт Phase 2B: 1-2 дня. Нужен план спринта от оркестратора.

---

## 17.04.2026 — FAIL2BAN_DEPLOY_v1 (утро): второй слой защиты VPS sofia-voice

**Сделано:**

- Установлен `fail2ban 1.0.2-3ubuntu0.1` на VPS `185.207.66.201` (Ubuntu 24.04)
- `/etc/fail2ban/jail.local` с двумя jail:
  - `[sshd]` — `backend=systemd`, `maxretry=10`, `bantime=3600`, `findtime=600`
  - `[asterisk]` — `backend=auto`, `logpath=/var/log/asterisk/messages.log`, `port=5090,5060`, `maxretry=5`, `bantime=3600`, `findtime=600`
- `[DEFAULT] banaction=ufw`, `ignoreip = 127.0.0.1/8 ::1 46.229.221.93 72.56.64.91 77.106.252.172` (Telfin + главный sofia-gpt сервер + личный IP Сергея)
- С первого старта из systemd journal sshd поймано и забанено через `ufw prepend reject` **9 SSH-сканеров** (maxretry=5 на момент первичного обнаружения пакетным дефолтом, далее новые баны идут с нашим threshold=10)
- Базовые UFW allow-правила (22/tcp, 5090/udp←46.229.221.93, 10000-20000/udp) **не тронуты** — fail2ban только prepend'ит reject выше
- `sofia-voice`, `asterisk`, `fail2ban` — все три active после деплоя

Изменения — только на VPS (pкет+config), в git-репо sofia-gpt-dev не коммитились. Рабочая SSH-сессия (72.56.64.91→185.207.66.201) не пострадала благодаря ignoreip.

**Побочные находки (пополнят CLAUDE.md «Уроки»):**

1. **apt install сразу стартует fail2ban** с дефолтным `banaction=nftables` из `/etc/fail2ban/jail.d/defaults-debian.conf`. После правки `jail.local` нужен `systemctl restart fail2ban`, **не** `reload` — reload не перевыполняет actionban, остаются phantom in-memory баны без реальных правил firewall. После restart состояние восстанавливается из persistence DB корректно.
2. **Приоритет fail2ban-конфигов:** `jail.d/*.conf` → `jail.local` → побеждает последний. Наш `jail.local` корректно перекрывает `defaults-debian.conf` по banaction. Но любой будущий `*.local` в `jail.d/` побьёт наш `jail.local`.
3. **Asterisk не пишет в systemd journal** на этой сборке Ubuntu — `journalctl -u asterisk` пусто, логи только в `/var/log/asterisk/{messages,full}.log`. Глобальный дефолт `backend=systemd` оставил бы asterisk-jail с пустым источником → фильтр никогда бы не сматчил. Явный `backend=auto` в `[asterisk]` — обязательно.
4. **`maxretry=5` в UFW-комментариях** при конфиге `maxretry=10` — это `<failures>` на момент первого бана (до загрузки нашего jail.local). Новые баны идут с threshold=10, комментарий в существующих правилах не обновляется. Не требует правки.

**Эффект:**

| Слой | Что покрывает |
|---|---|
| UFW (17.04) | Блокирует ~100% SIP-сканеров на SYN до Asterisk. `full.log` рост 44 KB/s → 0 B/s |
| fail2ban (17.04) | SSH brute-force через открытый 22/tcp; sip-атаки, если кто-то пролезет через whitelisted IP (маловероятно, но копеечная страховка) |

**Следующее:**

1. **Yandex STT v3 gRPC streaming** (P1, 1-2 дня) — архитектурное упрощение, server-side EOU убирает кастомную VAD+silence-threshold логику целиком. `docs/VOICE_RESEARCH_2026_04_16.md` идея #1.
2. **Мониторинг fail2ban:** `fail2ban-client status <jail>` раз в неделю, смотреть на рост `Total banned` и список IP. В P3 можно завести алерт на рост сверх baseline.

---

## 17.04.2026 — VOICE_STACK_STABILIZATION_v1: barge-in fixes × 4 + Silero VAD + UFW

**Сделано:**

### 1. Barge-in buffer reset (утренний fix, коммит `5104a0cc`)

**Trigger:** звонок 21b96626 (16.04 вечер). После cancel TTS `_process_turn` finally переносил barge-in buffer (~13KB) в `_speech_buffer` → garbled STT «Со стороны» → LLM-фолбэк «плохо слышно» из блока «Не расслышала» RIZALTA.

**Fix:** в `_process_turn` finally **не** re-feed'ить barge-in buffer, а просто `.clear()`. VAD начинает слушать свежий поток после cooldown. Правка ~10 строк в voice_asterisk.py.

### 2. Silero VAD миграция (коммиты `761ef1eb`, `97934f47`)

**Research:** `docs/VOICE_RESEARCH_2026_04_16.md` идея #4 — energy-based VAD ловил мусор (кашель, шум) → STT вернул «Эротика», «Зависят облака». Silero ONNX модель 1.8MB, <1ms CPU, 8kHz natively.

**v5 vs v4 discovery:**
- Скачали v5 (2.3MB) → offline-тест дал 13% детектирования на чистой речи greeting_rizalta.pcm
- Причина: v5 оптимизирован под 16kHz, 8kHz — деградация. Confirmed через debug probability distribution.
- Скачали v4 (1.8MB, md5 `03da8de2fec4108a089b39f1b4abefef`) → 73% detection на том же файле, 86% на speech+noise
- v5 сохранена как `silero_vad_v5.onnx.legacy` для будущих re-tests

**Integration:**
- `SileroVAD` класс per-call с LSTM state (`h`, `c`, [2,1,64])
- Singleton ONNX session (loaded once at startup: «Silero VAD loaded: ... (v4, 8kHz, md5=...)»)
- env `VOICE_VAD_PROVIDER=silero` (default) / `energy` (rollback)
- Dispatch в `_process_audio_vad` и `_detect_barge_in` через `self._vad is not None`
- Threshold 0.5 для normal VAD и barge-in (изначально пробовали 0.6 для barge-in — не пробивался)
- Зависимости: `onnxruntime 1.24.4`, `numpy 2.4.4` (pulled by onnxruntime)

**Коммит `761ef1eb`** — первый Silero live (threshold 0.5).

**Sliding-silence reset (коммит `97934f47`):** звонок bcf67956 показал **0 BARGE-IN confirmed** за 6 turns (57с TTS). Root cause: AudioSocket frames 320B / Silero chunks 512B → `is_speech()` **альтернирует True/False** на каждом фрейме. Старая логика `_barge_in_buffer.clear()` при любом False сбрасывала counter — 5 consecutive никогда не набиралось. Fix: track `_last_barge_in_speech_ts`, clear buffer только после 300ms sustained silence.

### 3. TTS race (коммит `830a5722`)

**Trigger:** звонок 89dadd55. После sliding-silence fix barge-in стал срабатывать, но **2 turn'а с TTS played=0s** — Sofia сгенерировала ответ, клиент услышал тишину.

**Root cause:** `_is_responding=True` с начала `_process_turn` (включая STT+LLM). Клиент договаривал свою реплику, Silero детектил → BARGE-IN confirmed → `_cancel_playback=True` ДО того как TTS начал играть. Первый же `_send_audio` видел cancel → break → total=first_chunk (0s audio).

**Fix:** новый флаг `_tts_playing` (True только с первой реально отправленной фрейма). В `_handle_packet` barge-in dispatch только при `_tts_playing=True`. Во время STT/LLM фазы фреймы от клиента **игнорируются** (он договаривает свою же реплику).

### 4. UFW firewall (нет коммита — VPS config)

**Trigger:** рост `/var/log/asterisk/full.log` 8GB/сутки от SIP-сканеров (193.46.255.104 давал 99% трафика).

**Разведка:**
- Telfin IP: `46.229.221.93` (DNS sipproxy.telphin.ru, /32, подтверждено `pjsip show registrations` Active)
- PJSIP bind: `UDP 5090` (из pjsip.conf)
- RTP: 10000-20000 UDP (rtp.conf)
- Открыты наружу также UDP 5060 (chan_sip legacy), UDP 4569 (IAX2) — только для сканеров, закрываем

**Rules (порядок строгий):**
```
ufw allow 22/tcp                                            # SSH (ПЕРЕД enable!)
ufw allow from 46.229.221.93 to any port 5090 proto udp     # Telfin SIP
ufw allow 10000:20000/udp                                   # RTP media
ufw default deny incoming
ufw default allow outgoing
ufw --force enable
```

**Результат:** baseline 43697 B/s (44 KB/s, 3.77 GB/день) → **0 B/s** (замер 60с после enable). SYN-пакеты сканеров блокируются до Asterisk, в лог не пишутся. `pjsip show registrations` — Active (Telfin trunk не затронут).

### 5. VAD_RELAX (коммит `95b4eeae`)

**Trigger:** звонок e177d7ad. Клиент: «Скажите примерно минимальную цену **и** [срок]» — `VAD_SILENCE_THRESHOLD=300ms` сработал на паузе между «и» и «срок», обрезал фразу посреди. Затем одиночное «ээ» ~100ms (5 frames) триггернуло `BARGE-IN confirmed` → deadlock (Sofia молчит, клиент ждёт, 17с тишины → hangup).

**Fix (bifurcate по провайдеру):**
- `VAD_SILENCE_THRESHOLD` 0.3 → **0.5 сек** (глобально, любой провайдер)
- barge-in confirm: `confirm_frames = 10 if self._vad is not None else 5` — Silero 10 frames (~200ms real speech с учётом chunking), energy 5 frames (kept for rollback fidelity через `VOICE_VAD_PROVIDER=energy`)

**Временная заплатка** до Yandex STT v3 gRPC streaming (server-side EOU определяет конец фразы, убирает silence threshold вообще).

### Финальный тест (звонок UUID `95e12e88-63dc-4ff8-bf03-fe91e4fb9d13`, 8 turns)

| Метрика | e177d7ad (до VAD_RELAX) | **95e12e88 (итог)** |
|---|---|---|
| USER turns | 2 + deadlock | **8 полноценных** |
| BARGE-IN confirmed | 1 (false на «ээ») | **1 (legit, 10-frame confirm)** |
| TTS 0s played | 0 | **0** |
| «плохо слышно» fallback | 0 | **0** |
| Audio too short skips | 2 | **0** |
| Deadlock 10+ сек | да | **нет** |
| ERROR/WARNING/Exceptions | 0 | **0** |

**Полный продажный flow:** питч → уточнение города → согласие → доходность/окупаемость → выбор Telegram → **диктовка ника «@сергей_7ид»** → прощание. Лид-конверсия через voice канал работает.

**Turn 4 «А сколько окупаемости и сколько годовой доход примерно»** (4.10с, 65600 bytes, 13.2 chars/sec) — фраза с союзом «и» в середине, ровно такая структура сломала e177d7ad. Прошла целиком.

**Turn 7 «Собака сергей нижнее подчеркивание 7 ид»** (4.76с) — клиент диктовал Telegram-ник с длинными паузами. Полная фраза.

### Коммиты 17.04 (в порядке времени MSK)

| SHA | Время | Сообщение |
|---|---|---|
| `5104a0cc` | 23:07 (16 → 17) | fix(voice): barge-in buffer reset instead of re-feed to VAD |
| `761ef1eb` | 23:39 | fix(voice): lower Silero barge-in threshold 0.6 → 0.5 (initial Silero integration) |
| `97934f47` | 23:59 | fix(voice): sliding-silence reset for Silero barge-in buffer |
| `830a5722` | 00:45 | fix(voice): introduce _tts_playing flag, ignore pre-TTS barge-in race |
| `95b4eeae` | 01:10 | fix(voice): relax VAD silence 0.3→0.5s, barge-in confirm 5→10 (Silero only) |

Плюс VPS config: UFW enabled, Silero VAD v4 model file `/opt/sofia-voice/silero_vad.onnx`.

### Текущее состояние voice pipeline

- **VAD**: Silero VAD v4 ONNX, threshold 0.5 normal+barge-in, `VAD_SILENCE_THRESHOLD=500ms`, `VAD_MIN_SPEECH_DURATION=300ms`, `MIN_SPEECH_BYTES_FOR_STT=10240`
- **Barge-in suppression**: `BARGE_IN_COOLDOWN=0.5s`, `BARGE_IN_SILENCE_RESET=0.3s`, 10-frame confirm Silero / 5-frame energy, `_tts_playing` флаг для STT/LLM phase-gate
- **STT**: Yandex SpeechKit v1 REST, ~200ms медиана
- **LLM**: YandexGPT 5 Pro, ~620ms медиана, promo RIZALTA v3 prompt
- **TTS**: Yandex Alena v1 REST lpcm 8kHz, TTFB ~155ms
- **Firewall**: UFW whitelist (22/tcp, 46.229.221.93:5090/udp, 10000-20000/udp), default deny incoming
- **Service**: sofia-voice.service active, PID 107061, память ~54M

### Следующая сессия — P0

1. **fail2ban deploy** (контракт готов в истории чата — два jail для sshd и asterisk, `banaction=ufw`, `ignoreip=46.229.221.93`). UFW закрывает ~100% трафика, fail2ban = multi-layered defense. Не срочно — можно в утренние часы.
2. **Yandex STT v3 gRPC streaming** (docs/VOICE_RESEARCH_2026_04_16.md идея #1, 1-2 дня) — архитектурное упрощение: server-side EOU уберёт нашу VAD+silence-threshold кастомную логику целиком.

---

## 16.04.2026 — VOICE_YANDEX_MIGRATION_v1: полная миграция голосового стека на Yandex

**Сделано:**

### Диагностика (начало сессии)
- Groq убрал модель `moonshotai/kimi-k2-instruct` без предупреждения (HTTP 404)
- OpenAI fallback мёртв (GeoIP 403 с VPS). Голосовой канал полностью неработоспособен
- 4 клиента RIZALTA получили "подвисла" утром до фикса

### Sprint 1: миграция LLM + TTS на Yandex (VOICE_YANDEX_MIGRATION_v1)
- **LLM:** Groq kimi-k2-instruct → YandexGPT через OpenAI-compatible endpoint (`llm.api.cloud.yandex.net/v1/chat/completions`), openai SDK 2.30.0
- **TTS:** ElevenLabs eleven_v3 Nastya (через proxy) → Yandex SpeechKit Alena v1 REST (напрямую), format=lpcm 8kHz, emotion=neutral, speed=1.1. ffmpeg убран из hot path
- **Cached greeting:** greeting_rizalta.pcm (83KB, 5.2s) и greeting_atlantis.pcm (95KB) предгенерированы через Yandex TTS, TTFB=0ms
- **Anti-hallucination:** YandexGPT генерировал fake-диалоги (маркеры "Пользователь:", "Ассистент:"). Фикс: (1) CRITICAL-инструкция в начало VOICE_SYSTEM_PROMPT_RIZALTA и VOICE_SYSTEM_PROMPT, (2) regex post-filter в stream_voice_response() обрезает на маркерах
- **SSML break fix:** Yandex отвергает `<break time="0.3s"/>` (дробные секунды). Заменено на `<break time="300ms"/>`
- **Dead branches:** legacy Groq/ElevenLabs код сохранён под `VOICE_PROVIDER=groq` и `VOICE_TTS_PROVIDER=elevenlabs`
- **5 тестовых звонков Сергея:** 2 на этапе B (ElevenLabs TTS), 2 на этапе C (SSML баг), 1 финальный (полный успех, 4 turns, 66.9s)

### A/B тест 4 моделей YandexGPT (живые звонки, одинаковый скрипт RIZALTA)
| Модель | LLM медиана | User pause | "Откуда данные" | Вердикт |
|--------|------------|------------|-----------------|---------|
| YandexGPT Lite | 815ms | ~1070ms | FAIL (сдалась) | быстро но тупо |
| Qwen3-235B-A22B-FP8 | 2340ms | ~2726ms | OK (подробно) | умно но медленно |
| **YandexGPT 5 Pro** | **638ms** | **~860ms** | OK (кратко) | **ЛУЧШИЙ БАЛАНС** |
| Alice AI LLM | 1290ms | ~2160ms | OK (полный) | умнее всех но многословна |

**Решение:** YandexGPT 5 Pro (`yandexgpt/latest`) для голоса. Переключено на VPS через .env.

### Финальные метрики (звонок d3e92e56 + A/B серия)
| Метрика | Старый стек (ElevenLabs+Groq) | Новый стек (Yandex) | Delta |
|---------|------|------|-------|
| TTS TTFB | 1100ms медиана | **177ms медиана** | -84% |
| LLM latency | 379-1677ms | **638ms медиана (Pro)** | улучшение |
| STT latency | 201-247ms | 158-239ms | ~same |
| User pause (end-to-end) | ~1300ms | **~860ms (Pro)** | -34% |
| Greeting TTFB | 1106-1818ms | **0ms** (cached) | -100% |
| Proxy dependency | Да | Нет | eliminated |

**Коммиты:** `a7f45612` feat(voice): migrate LLM+TTS to Yandex stack (VOICE_YANDEX_MIGRATION_v1)
**Файлы:** voice_asterisk.py, core/pipeline.py, .env (VPS)
**Env добавлены (VPS):** YC_API_KEY, YC_FOLDER_ID, VOICE_MODEL_YANDEX, VOICE_TTS_PROVIDER, YANDEX_TTS_VOICE, YANDEX_TTS_EMOTION
**Env изменены (VPS):** VOICE_PROVIDER=yandex (было groq), VOICE_MODEL_YANDEX=yandexgpt/latest (Pro)
**Rollback:** VOICE_PROVIDER=groq / VOICE_TTS_PROVIDER=elevenlabs в .env + systemctl restart sofia-voice

**Побочные находки:**
- SIP-сканеры (193.46.255.104 + 172.110.223.135) раздувают Asterisk full.log ~8G/сутки, диск рос 15%→45% за сутки → fail2ban/UFW переведён в P0

### Sprint 1 продолжение: Barge-in fix + RIZALTA v3 + voice research

**Barge-in cascade fix:**
- После миграции на Yandex Alena TTS (быстрее ElevenLabs) barge-in стал заметнее — 50% пустых STT на звонках с перебиванием, каскад ложных VAD после cancel TTS
- Добавлено в `voice_asterisk.py`: константы `BARGE_IN_COOLDOWN=0.5`, `MIN_SPEECH_BYTES_FOR_STT=10240`, поле `_barge_in_cooldown_until`
- Гейт в `_handle_packet` AUDIO-ветке: `time.monotonic() < _barge_in_cooldown_until` → дропать фрейм
- Cooldown активируется в `_detect_barge_in` при подтверждении barge-in (вместе с `_cancel_playback=True`)
- MIN_BYTES проверка в `_process_audio_vad` перед созданием `_process_turn` task → debug-лог `Audio too short (N bytes < 10240), skipping STT`
- Проверено в живом звонке 16.04 18:40 (UUID 21b96626): cooldown сработал 2×, MIN_BYTES 3×

**RIZALTA промпт v3 (коммит `ef2888ae`):**
- **Без представления** («Алло, здравствуйте! У меня для вас важная новость...» сразу в greeting)
- **Двухчастный питч:** часть 1 — крючок с доходностью (greeting); часть 2 — регион/спрос/Сибирь (после согласия)
- **Логика мессенджеров:** Ватсап/Макс = номер уже знаем, прощаемся; Телеграм = уточняем ник; иначе — спрашиваем «Куда удобнее?»
- **Вход повышен** 10 млн → 15 млн рублей (по факту проекта)
- Добавлены: Совкомбанк ипотека, траншевая ипотека Сбербанка, сравнение с депозитом, минимальный гарантированный платёж
- Запрещены фразы «скину пакет» / «в Телеграм пакет» (неестественно)
- Cached greeting `greeting_rizalta.pcm` регенерирован через Yandex Alena (190 chars → 198318 bytes PCM, 12.4s аудио, 346ms синтез)
- Hardcoded greeting в `voice_asterisk.py:506-511` обновлён на питч-часть-1

**Тестовый звонок с перебиванием (UUID 21b96626, 81.8s):**
- Greeting проиграл целиком (1ms TTFB, 12.4s без прерываний)
- Turn 1 barge-in через 10с игры TTS → cooldown 500ms сработал
- **Проблема:** 13120-байтовый barge-in buffer (0.82с, порог 10240 прошёл) отправился в STT → garbled «Со стороны» → LLM-ответ «Простите, плохо слышно» из блока «Не расслышала» промпта
- Логика мессенджеров дошла: «Куда отправить? Телеграм, ватсап или макс?» на «Да давайте» ✅

### Исследование voice stack (отчёт `docs/VOICE_RESEARCH_2026_04_16.md`)

- 20 идей улучшения, каждая с gain/effort/risk/priority/источниками
- Сравнение 5 мировых платформ (Vapi, Retell, LiveKit, Pipecat, 11L Conversational)
- Обзор 6 отечественных стеков (Yandex, Sber SaluteSpeech, Tinkoff VoiceKit, T-one OSS, GigaAM v3, Silero TTS v5)
- **Топ-5 по gain/effort:** Silero VAD (0.5д, −150ms), Yandex STT v3 gRPC streaming (1-2д, −300ms), sentence-level LLM→TTS (2д, −350ms), TTS cache + fillers (1.5д, перцептивно→0ms), per-turn JSON metrics (1д, observability)
- **Целевая метрика:** 860ms median user-perceived pause → **300-400ms** + субъективно <100ms через filler маскирование
- Эффорт top-5 ≈ 7 дней чистой работы

### Следующая сессия — P0

1. **Barge-in buffer reset** вместо re-feed в VAD (сейчас `_process_turn` finally копирует barge-in buffer в `_speech_buffer` → 13120-байтный polluted fragment попал в STT). Вариант: после cooldown просто очищать buffer, ждать свежую речь
2. **Silero VAD** замена energy-based RMS (0.5 дня, drop-in замена, +90% precision)
3. **Yandex STT v3 gRPC streaming** — убрать REST TLS handshake + VAD 300ms timeout (−150-300ms)
4. **Sentence-level LLM streaming → TTS pipelining** (−200-350ms на репликах >1 предложения)

**Коммиты 16.04:**
- `3edc908f` docs: session 16.04 — voice diag (Groq model removed)
- `a7f45612` feat(voice): migrate LLM+TTS to Yandex stack (VOICE_YANDEX_MIGRATION_v1)
- `ae61ed8d` docs: session 16.04 — voice yandex migration + 4-way A/B
- `ef2888ae` feat(voice): RIZALTA v3 prompt + voice research report

**Файлы:** voice_asterisk.py, core/pipeline.py, docs/VOICE_RESEARCH_2026_04_16.md, greeting_rizalta.pcm (VPS)

---

## 15.04.2026 — Аудит расхождений + DISK_RESCUE + правила оркестратора

**Сделано:**

### 1. Context reconciliation (CONTEXT_RECONCILIATION_v1)
- Сверка модели Claude Code с реальностью по 7 пунктам
- Найдено критичное: VPS sofia-voice диск снова 100% (4 дня после прошлой чистки вместо прогноза 4-6 недель)
- Sprint 2 (Radist username→Bitrix) verified в production: лид 265712 (Arkadiy, @pordiregrwe) прошёл полный цикл — UF_CRM_TELEGRAM заполнен, ASSIGNED восстановлен на менеджера 14708, БП 152 отработал
- Edge-case клиент без публичного username (лид 265590) обработан корректно — поле не заполнено, не затёрто пустотой
- Тильда: единственная ссылка `https://t.me/m/QinKZEsTNmRi` стабильно отдаётся для всех User-Agent
- Урок: фильтр Bitrix `TITLE LIKE "AI-бот"` не работает для ATL (Sofia обновляет существующий Tilda-лид, не создаёт). Правильный фильтр — `SOURCE_ID=397 + DATE_MODIFY` + кросс-проверка с `radist_leads`

### 2. DISK_RESCUE_v2 (пятиэтапный спринт)
- **Диагностика:** на 185.207.66.201 диск 100% (29 GB / 29 GB)
- **Корневая причина найдена:** `/etc/logrotate.d/asterisk` (поставленный с пакетом в 2022) имел сломанные glob-паттерны — `messages` вместо `messages.log`, `full` вместо `full.log`, `*_log` вместо `*.log`. logrotate каждую неделю отрабатывал, ничего не находил, тихо завершался. Файлы росли неограниченно 4 года. Это баг сборки Asterisk-пакета для Debian/Ubuntu — старые версии писали без расширения, новые с .log, конфиг logrotate в пакете не обновили.
- **Очистка диска:** освобождено 25 GB
  - Этап 3: `rm` архивных `full.log.0` + `messages.log.0` (по 9.9 GB) + `journalctl --vacuum-size=200M` + `truncate` btmp = +21 GB
  - Этап 4: `asterisk -rx 'logger rotate'` (родная команда, корректно переоткрывает fd через inode change) + `rm` ротированных = +3 GB
- **logrotate починен:** новый `/etc/logrotate.d/asterisk` с явными `full.log`, `messages.log`, `queue_log`, `daily rotate 7 compress`, postrotate через `asterisk -rx 'logger rotate'`. Бэкап старого в `/etc/logrotate.d/asterisk.broken.20260415`
- **Финальное состояние:** диск 15% used / 85% free, asterisk + sofia-voice оба active, голосовой канал ожил после очистки, mtime `/etc/asterisk/logger.conf` не изменился (доказательство неприкосновенности)
- **Усиление методологии:** Claude Code применил inode-check вместо опасного size-check для подтверждения ротации (поправка в Этапе 4)

### 3. Правила оркестратора зафиксированы в отдельном документе
- Создан `docs/ORCHESTRATOR_RULES.md` с правилами работы Claude.ai как оркестратора
- В CLAUDE.md добавлена ссылка на новый документ
- Поводом стали ошибки сегодняшней сессии: захардкоженный systemd-unit без знания файлов (10.04), длинные ответы на простые вопросы (15.04), отсутствие прохода "что забыл" перед отдачей контракта (15.04)

### 4. Gitpull-гигиена (UPDATE_GITPULL_DOCS)
- Найдено: `start-session.sh` (на локалке Сергея) копирует только CLAUDE.md / SESSION_LOG.md / BACKLOG.md, новый `docs/ORCHESTRATOR_RULES.md` в контекст Claude.ai не попадал. Без этого правила оркестратора, записанные сегодня, при следующем `start-session.sh sofia` оркестратор бы не увидел.
- Блок «Gitpull» в CLAUDE.md дополнен: `mkdir -p ~/projects_claude/Sofia/docs` + 4-я scp-команда для `docs/ORCHESTRATOR_RULES.md`
- Блок «Session End» дополнен: новый пункт 3 «при изменении правил оркестратора — обновить ORCHESTRATOR_RULES.md», файл добавлен в `git add`-команду
- Сергей синхронно обновил локальный `start-session.sh` — проверено на следующем запуске
- Урок: любой новый файл, который должен попадать в контекст Claude.ai, требует **парной** правки: и CLAUDE.md, и локального скрипта, иначе документация и реальный flow расходятся

### 5. ATLANTIS_CHAT_WIDGET_v1
- Создан `widgets/atlantis_chat_widget.html` (15.9 KB) — самодостаточный HTML-блок для Tilda T123
- Десктоп: фиксированный круг 72×72 справа по центру, золотой градиент, два concentric pulse-ring через `::before/::after`, hover scale 1.08
- Мобильный: фиксированная плашка снизу с base64-аватаркой Софии, зелёной точкой онлайн, двумя строками текста, slide-up анимацией, iOS `env(safe-area-inset-bottom)`
- Все CSS-классы `atl-chat-*`, z-index 99999, никакого JS, никаких внешних ресурсов
- Ведёт в @SofiaOazis через Telegram Business Link `https://t.me/m/Fiw3ldhkN2My` (вторая ссылка, не основной QinKZEsTNmRi)
- Правка по фидбеку Сергея: круг зелёный `#4ade80 → #16a34a` вместо золота (точечная замена одной строки CSS)
- Коммит `3de1fbf9`

### 6. SPRINT_TEMPLATE_v2 + wiring
- Создан `docs/SPRINT_TEMPLATE_v2.md` (13.3 KB) — универсальный шаблон Sprint Contract на XML-структуре по гайду Anthropic
- 9 обязательных секций (role/context/task/investigate_first/acceptance_criteria/do_not/rollback/build_report_format/done_when) + 4 опциональных (subagents/stop_for_confirmation/edge_cases/external_artifacts)
- Два встроенных блока: `<anti_overengineering>` и `<investigate_before_answering>` — копируются в каждый контракт дословно. Filling example в конце с эталоном заполнения
- Коммит `057b6811`
- TEMPLATE_V2_WIRING (`71103849`) — добавил правило в ORCHESTRATOR_RULES.md п.4 «новые контракты строить по SPRINT_TEMPLATE_v2.md», добавил scp-строку в Gitpull блок CLAUDE.md, обновил git add в Session End
- Урок закрепился: шаблон без проводки в Gitpull — остаётся сиротой. Парная правка (репо + локальный скрипт) обязательна

### 7. SAFETY_RULES_v1 — промпт-правила (DEV)
- В `sofia_prompt_v2.py` добавлен блок «ЧЕГО SOFIA НЕ ДЕЛАЕТ» (+18 строк) между «ПРИНЦИПЫ ОБЩЕНИЯ» (строка 321) и «ТЕХНИКИ ПРОДАЖ» — универсальные запреты для всех каналов: не запрашивать паспорт/реквизиты/коды, не давать юр. гарантий, не обещать доходность, не заключать сделки, не подтверждать бронь окончательно
- В `config/source_objects.py` `prompt_addon` Атлантиса расширен с 1 строки до triple-quoted multi-line с блоком «ПЕРЕДАЁТ ДИАЛОГ МЕНЕДЖЕРУ» — триггеры: политическое мнение (с уточнением про отличие от возражения по безопасности региона), юр/фин о компании, СВО, дискриминация, незаконные схемы, мошеннические запросы
- Stop-point после разведки: обнаружен конфликт старого возражения «В Крыму опасно / политика / нападения» со новым триггером, решён переформулировкой первого триггера
- Коммит `772cbe6e` с `--no-verify` (pre-existing долг в `format_state_summary` по `black`, не связан со scope; явное разрешение оркестратора)
- DEV Smoke #1 (Атлантис + СВО): Sofia НЕ применила новое правило — выяснилось что web_api.py вообще не устанавливает `source_object` в state, поэтому Atlantis-addon никогда не склеивается в промпт через web. Плюс Analyzer классифицировал СВО как OBJECTION → RAG затянул примеры возражений
- DEV Smoke #2 (банковские реквизиты + СМС-код через общий web): Sofia **корректно** применила все три правила общего блока — явно предупредила не присылать СМС-код, отказалась выдавать реквизиты, сослалась на менеджера, не выдала внутреннюю инфу

### 8. SAFETY_RULES_DEPLOY_PROD — split-deploy в PROD
- Задача: port коммита 772cbe6e в PROD. Получилось только наполовину — по очень хорошей причине
- Разведка PROD показала: `sofia_prompt_v2.py` PROD vs DEV — чистый diff (только +18 моих строк). `config/source_objects.py` — есть pre-existing косметический drift (black на `detect_source`/`load_object_context`, backport не делался)
- Первая попытка — `git cherry-pick 772cbe6e` в PROD — упала с `fatal: bad revision`: PROD и DEV **разные git-репо**, SHA одного недоступен в другом. Мой пропуск в рекомендации
- Вторая попытка — `git format-patch | git am` — упала с `patch does not apply at config/source_objects.py:18`
- Анализ конфликта открыл **большую находку**: в PROD `config/source_objects.py` **вообще нет** ключа `prompt_addon` в Атлантисе, а в PROD `core/pipeline.py` **нет** ветки `if obj_config.get("prompt_addon")` — весь Atlantis-addon-механизм DEV-only, никогда не был в PROD. Это подтверждает давний пункт BACKLOG про «prompt_addon только в dev, не закоммичен», но масштаб больше: там **400+ строк** разницы в `core/pipeline.py` DEV vs PROD
- Решение (вариант D, split): применить **только** `sofia_prompt_v2.py` часть через `git show 772cbe6e -- sofia_prompt_v2.py | git apply --index -`, Atlantis-часть отложить до отдельного спринта `ATLANTIS_ADDON_INFRA_PORTBACK`
- PROD коммит `d60e9b0b` feat(prompts): safety rules (core only) — port from dev 772cbe6e (atlantis-addon deferred). Локальный, без push
- Рестарт всех трёх PROD-сервисов (sofia-gpt / sofia-web-api / sofia-radist) — все active running, 0 ERROR в логах за 5-минутный мониторинг
- PROD smoke с тем же СМС-триггером — Sofia PROD применила все 3 правила общего блока, буквальный ответ зафиксирован в Build Report

### 9. GAPS_CLOSE_BEFORE_NEXT_SESSION
- Перед закрытием сессии зафиксированы 3 пробела:
- `docs/ORCHESTRATOR_RULES.md` «Стиль ответов» расширен пунктами 6-10: «lf» = «да», запрет ритуальных оборотов, короткое признание ошибок без самозащиты, «по шагам» = один шаг/сообщение, «человеческим языком» как сигнал усталости Сергея
- `CLAUDE.md` Gitpull блок дополнен scp-командами для 4 критичных memory-файлов: `project_prod_dev_drift.md`, `user_sergey.md`, `project_voice_sprint_next.md`, `project_voice_vps.md`. `mkdir` объединён (`docs` + `memory`). Без этого оркестратор Claude.ai в новой сессии не увидит каталог PROD↔DEV drift и свежие наблюдения про Сергея
- `BACKLOG.md` P3: добавлен пункт «Обновить userMemories оркестратора» — устарели на сутки, оркестратор сам обновит через memory_user_edits в начале следующей сессии
- Коммит `3081ea0e`

**Коммиты DEV (15.04, полный список):**
- `923f229c` docs: session 15.04 close — DISK_RESCUE + orchestrator rules
- `5fee930c` docs: добавить ORCHESTRATOR_RULES.md в Gitpull блок CLAUDE.md
- `b5eb6822` docs: финализация session 15.04 — UPDATE_GITPULL_DOCS зафиксирован
- `3de1fbf9` feat(widget): atlantis chat widget for tilda T123
- `057b6811` feat(docs): sprint contract template v2 with xml structure
- `71103849` docs: wire SPRINT_TEMPLATE_v2 into orchestrator rules and gitpull
- `772cbe6e` feat(prompts): safety rules + manager handoff triggers (atlantis)
- `d3d20d9e` docs: session 15.04 close (часть 2) — widget + template + safety rules + prod deploy
- `3081ea0e` docs: close 3 pre-session gaps (style rules, memory gitpull, userMemories backlog)

**Коммит PROD:**
- `d60e9b0b` feat(prompts): safety rules (core only) — port from dev 772cbe6e (sofia_prompt_v2.py only, atlantis-addon deferred)

**Уроки сессии (зафиксированы в CLAUDE.md + ORCHESTRATOR_RULES.md):**
- `git cherry-pick` **не работает** между отдельными git-репозиториями (PROD/DEV — отдельные репо, а не ветки одного). Нужно `git format-patch | git am` или `git fetch <path> && git cherry-pick FETCH_HEAD`
- При деплое DEV→PROD в investigate_first обязательно сравнивать не только целевые файлы, но и **файлы-потребители** целевых изменений (pipeline.py когда трогаем config/*.py, bot_server.py когда трогаем core/bitrix.py и т.д.)
- PROD может содержать не «DEV минус целевой коммит», а «DEV минус целая фича». Сегодня: Atlantis-addon как механизм отсутствует в PROD целиком (данные + код-потребитель), 400+ строк разницы в pipeline.py
- Правило «ловить нестыковки контракта ДО выполнения» работает: 3 stop-point'а сегодня (A→A'→A'', A'→конфликт, D→split) сэкономили откатов и ошибок

**Файлы сессии (DEV):**
- sofia_prompt_v2.py (+18)
- config/source_objects.py (+16/-1)
- widgets/atlantis_chat_widget.html (новый, 15.9 KB, круг зелёный)
- docs/SPRINT_TEMPLATE_v2.md (новый, 13.3 KB)
- docs/ORCHESTRATOR_RULES.md (новый + дополнения)
- CLAUDE.md (Gitpull блок, Session End блок, Docs ссылки, 5+ новых уроков)
- SESSION_LOG.md, BACKLOG.md

**Файлы сессии (PROD):**
- sofia_prompt_v2.py (+18, через git apply, коммит d60e9b0b)

**Открытые задачи после сессии:**
- 🔴 **ATLANTIS_ADDON_INFRA_PORTBACK (P0)** — полный аудит pipeline.py PROD vs DEV (400+ строк разницы), план порта Atlantis-addon-механизма в PROD. Блокер для работы Atlantis-specific safety-триггеров в production
- Кнопка «Чат с менеджером» на сайте — Сергей использует готовый виджет из widgets/
- 20-минутный робот Bitrix у админа (ждём)
- SIP-сканеры на VPS (P2)
- Whisper STT vs Yandex SpeechKit несоответствие (P2)
- chore(format): run black on prompt files (sofia_prompt_v2.py + source_objects.py backport в PROD)

---

## 11.04.2026 — Деплой Radist username→Bitrix в PROD

**Сделано:**

### Деплой Спринта 2 (RADIST_USERNAME_DEPLOY_PROD_v1)
- Фича из коммита 8b504869 (DEV) выведена в production
- Файлы: sofia_radist_gateway.py (+76 строк), core/bitrix.py (+12 строк)
- Pre-deploy: diff показал только username-изменения, ничего постороннего
- Снапшоты PROD сохранены: `/tmp/radist_gw.prod.before_deploy`, `/tmp/bitrix.prod.before_deploy`
- ast.parse обоих файлов OK
- `sudo systemctl restart sofia-radist.service` → active (running), PID 2460093
- Логи чистые: БД init, каналы active (max, telegram), 0 ошибок
- Git commit в PROD: `1146ea2c` (без push — by design)
- Функциональная проверка отложена до первого реального ATL-клиента

**Коммиты:**
- 1146ea2c (PROD) — feat(radist): deploy username→Bitrix from dev (8b504869)

**Файлы (PROD):** sofia_radist_gateway.py, core/bitrix.py

---

## 10.04.2026 — Аудит Атлантис + merge bot_server.py (Observer portback)

**Сделано:**

### 1. Полный аудит Атлантиса (docs/AUDIT_ATLANTIS_2026-04-10.md)
- Зафиксирован переход на @SofiaOazis через Telegram Business Link
  (https://t.me/m/QinKZEsTNmRi) — Тильда переключена на всех 3 формах
  invest-apartmens.online, старая ссылка t.me/humanAINeural_bot?start=ATL
  нигде не используется
- ATL-flow через Radist работает полностью: 8 сессий за 2 дня, 6 реальных
  клиентов, 5 из 6 финализированы через БП 152
- Radist dedup fix (3892c648) фактически верифицирован живым трафиком
- Виджет на invest-apartmens.online/atlantis отключён 04.04, код страницы
  очищен от упоминаний Sofia (возврат — Спринт 3)
- 3 домена виджета по web_sessions: invest-apartmens.online (180),
  atlantis-invest.ru (6), sochiremstroy (2)
- rizaltabelokurikha.ru — другой виджет (EvaChatWidget), не наш
- Атлантис = Крым, Новофёдоровка, Cosmos Crimea (не Сочи — зафиксировано
  исправление в userMemories)

### 2. Расследование зависших лидов на ASSIGNED=428
- Лид #264518 (Роман) — Тильда-форма "Презентация в WhatsApp", клиент
  не дошёл до бота, висит 87ч. Sofia такого клиента не видит в принципе.
- Лид #264372 ("пывп") — тест-мусор, 110ч
- Системная причина: safety-net для Тильда-лидов без диалога
  отсутствует. 20-минутный Bitrix-робот должен был быть настроен 04.04,
  админ забыл — добивает сегодня
- Добавлено в BACKLOG P1: safety-net verification после настройки робота

### 3. Спринт: merge bot_server.py — Observer portback (коммит 75b779a5)
- Проблема: коммит 49659ffb (08.04) добавил Observer напрямую в PROD,
  не был портирован в DEV. Любой будущий деплой DEV→PROD молча удалил бы
  Observer из PROD.
- Разведка Фазы 1: первая попытка Claude Code ошибочно показала одинаковый
  49659ffb в обеих ветках (неправильный cwd при git log). Повторная
  проверка подтвердила: коммит есть только в PROD, в DEV его никогда не
  было, reflog чистый, shell history чистый — Observer никто специально
  не отключал, просто не дошёл до dev
- Merge: 6 блоков (86 строк) перенесены из PROD в DEV:
  1. import logging + logging.basicConfig (строки 27, 29-34)
  2. OBSERVER_CHAT_ID (структура из PROD, env-default "-5206139579" для
     dev-группы сохранён)
  3. CREATE TABLE observer_topics_bot (339-345)
  4. get_or_create_bot_topic() + notify_bot_observer() (896-961)
  5. notify_bot_observer для входящего (979-981)
  6. notify_bot_observer для ответа Софии (1035-1037)
- Итоговый diff PROD vs DEV: ровно 1 строка (OBSERVER_CHAT_ID default),
  остальные 86 строк идентичны
- flake8 + black проходят, ast.parse + import bot_server OK
- PROD не трогали, snapshot /tmp/bot_server.prod.snapshot и
  /tmp/bot_server.dev.snapshot оставлены как rollback

### 4. Спринт 2: Radist username → Bitrix (коммит 8b504869)
- chat.username и chat.profile_link из Radist webhook теперь извлекаются
  и передаются в Bitrix: UF_CRM_TELEGRAM = https://t.me/username (кликабельная
  ссылка) + COMMENTS строка "Telegram: @username"
- Нормализация: пустой username → не пишем, не затираем существующее.
  Fallback: profile_link если username пуст
- tg_username сохраняется в radist_chats (миграция ALTER TABLE) для доступа
  при финализации по таймауту
- Dry-run тест: payload с username содержит UF_CRM_TELEGRAM, без username —
  поле отсутствует (не затирает)
- Файлы: sofia_radist_gateway.py (+76), core/bitrix.py (+12)

### 5. Спринт: sofia-voice systemd unit (VPS 185.207.66.201)
- **Инцидент:** ребут сервера хостингом (апгрейд 14→29 GB диск,
  961 MB → 1.9 GB RAM), voice_asterisk.py не поднялся (~40 мин даунтайма)
- Создан `/etc/systemd/system/sofia-voice.service`: Type=simple,
  Restart=on-failure, RestartSec=3, EnvironmentFile, LOGURU_COLORIZE=false
- systemctl enable + start → active (running), MainPID=2941, 34.6M памяти
- Auto-restart протестирован: kill -9 → NRestarts=1, новый PID через 3 сек
- Голосовой канал восстановлен и защищён от будущих ребутов
- **Подсветка:** логи voice_asterisk говорят "Whisper STT", CLAUDE.md
  говорит "Yandex SpeechKit" — требует проверки что реально используется

### 6. Зафиксировано на будущее (см. ниже — в CLAUDE.md как правила)
- Правило: любой прямой коммит в PROD должен немедленно портироваться
  в DEV или явно фиксироваться в SESSION_LOG
- Нужна регулярная git-sanity проверка расхождений prod vs dev по всем
  файлам (как минимум core/, config/, *_server.py, *_gateway.py)

**Коммиты:**
- 75b779a5 (DEV) — merge: bot_server.py — Observer portback из PROD
- 8b504869 (DEV) — feat(radist): Telegram-username → Bitrix

**Файлы:**
- docs/AUDIT_ATLANTIS_2026-04-10.md (новый)
- bot_server.py (DEV, +86 строк Observer portback)
- sofia_radist_gateway.py (DEV, +76 строк username)
- core/bitrix.py (DEV, +12 строк telegram_url)
- /etc/systemd/system/sofia-voice.service (VPS, новый)
- SESSION_LOG.md, BACKLOG.md, CLAUDE.md (этот апдейт)

**Открыто для следующих спринтов:**
- Спринт 3: возврат виджета в новом формате (slide-out side tab), ждёт
  verification 20-минутного робота Bitrix
- source_objects.py prompt_addon (DEV-only, не закоммичен) — требует
  разделения логики запроса контактов по каналам (виджет vs Telegram)
- git-sanity полный scan prod vs dev — можно выполнить отдельным мини-спринтом
- Деплой Radist username → Bitrix в PROD — отдельный шаг после визуальной
  проверки Сергеем

---

## 10.04.2026 — Stress Research + TTS A/B Test + Eleven v3 Locked

**Сделано:**

### 1. Stress Research (ruaccent + U+0301)
- ruaccent 1.5.8.3 протестирован на 16 словах-ловушках: **75% точность** (12/16)
- Латентность ruaccent: **388ms среднее** — превышает порог 200ms в 2x
- Баг ONNX: `token_type_ids` отсутствует, патч `np.zeros_like(input_ids)` в accent_model.py
- U+0301 (combining acute accent) — **не документирован** в ElevenLabs
- Phoneme tags — только для английского, только eleven_flash_v2
- **Решение: Вариант B — ручной словарь фонетических замен** (0ms, 100% контроль)
- Отчёт: `docs/STRESS_RESEARCH.md`
- Тестовые аудио: `voice_samples_v2/stress_test/` (4 mp3)

### 2. TTS Model Research (Flash v2.5 vs MLv2 vs v3)
- eleven_v3 доступен через API на Starter плане, model_id = `eleven_v3`
- v3 TTFB = 700-900ms (Flash = 367ms, MLv2 = 585-3060ms)
- v3 НЕ поддерживает `optimize_streaming_latency`
- v3 PVC "not fully optimized" по документации, но по факту Nastya звучит хорошо
- v3 = 2x дороже Flash по кредитам (1 vs 0.5 за символ)
- Отчёт: `docs/ELEVENLABS_V3_RESEARCH.md`
- Семплы: `voice_samples_v2/v3_vs_multilingual/` (6 mp3), `voice_samples_v2/stability_test/` (8 mp3)

### 3. Live A/B Test (на реальных звонках)
- Этап 1: v3 → Сергей: "прекрасно звучит"
- Этап 2: MLv2 stable (stab=0.7, sim=0.9) → отклонён
- **Решение: eleven_v3 = production TTS модель**
- Компромисс: TTFB +400-500ms vs Flash, компенсируется fillers (следующий спринт)

### 4. Sync DEV от VPS
- VPS → DEV: voice_asterisk.py (Flash v2.5 → v3, add_ssml_breaks, VoiceSettings, RIZALTA prompt v2)
- Два коммита: `8d468477` (sync), `04d9a710` (v3 adoption)

### 5. CLAUDE.md обновлён
- ElevenLabs: Flash v2.5 → eleven_v3
- Тайминги обновлены: TTS TTFB ~700-900ms

**Коммиты DEV:** `8d468477` (sync), `04d9a710` (v3 lock)
**Файлы:** voice_asterisk.py, core/pipeline.py, docs/STRESS_RESEARCH.md, docs/ELEVENLABS_V3_RESEARCH.md, docs/SOFIA_CURRENT.md, SESSION_LOG.md

**Текущие тайминги (обновлены):**
- VAD silence: 300ms
- STT (Yandex): ~300ms
- LLM (Groq kimi-k2 via proxy): ~300ms
- TTS TTFB (ElevenLabs v3 via proxy): ~700-900ms
- **Итого: ~900-1100ms ощущаемая пауза** (было ~600-700ms с Flash)

**Следующий спринт:** Fillers (B1) для маскировки латентности v3

---

## 09.04.2026 — Radist dedup fix + Voice Research + Voice Stack Tuning v2 + RIZALTA Prompt v2

**Сделано:**

### 1. Диагностика и фикс дублирования сообщений в Radist (DIAG+FIX)
- Диагностика: клиентские реплики дублировались кумулятивно в radist_messages, Observer и Bitrix COMMENTS
- Причина: `save_message()` и `notify_observer()` вызывались на каждой итерации `_process_loop` в message_queue.py
- Фикс: вынос save/notify в замыкание `save_user_and_notify()`, вызов один раз через `send_callback`
- Доп. фикс: `get_history()` ORDER BY timestamp → id (устранение недетерминированности)
- DEV коммит: `7f4c96a2`, PROD cherry-pick: `3892c648`
- Деплой в PROD: рестарт sofia-radist.service, подтверждён работающим

### 2. Voice Research Sprint (3 часа, 3 параллельных агента)
- Протестировано: 9 LLM (Groq+OpenAI), 16 TTS движков, 7 STT
- Сгенерировано: 23 коротких + 12 длинных + 19 finalists = 54 аудиофайла
- Главное открытие: **kimi-k2-instruct** на Groq — лучший русский для голоса (TTFT ~300ms, качество 5/5)
- ElevenLabs Flash v2.5 = Turbo v2.5 (deprecated) — 3x быстрее MLv2
- Yandex SpeechKit: лучшие ударения (99%), но нет voice cloning
- Отчёт: `docs/RESEARCH_REPORT_VOICE_AGENT_v1.md`
- Семплы: `voice_samples_v2/` (short + long + finalists)

### 3. Voice Stack Tuning v2 (деплой на VPS sofia-voice)
- LLM: llama-4-scout → **kimi-k2-instruct** (устранение Йода-русского)
- TTS: eleven_multilingual_v2 → **eleven_flash_v2_5** (TTFB 960ms→300ms)
- VoiceSettings: stability 0.35→0.50, similarity 0.79→0.85, speed 1.19→1.10
- max_tokens: 400→150
- VAD: 0.4→0.3
- SSML: `add_ssml_breaks()` — автовставка `<break time="0.3s"/>` между предложениями (без `<speak>` обёртки!)

### 4. RIZALTA Prompt v2
- Полностью новый промпт: канонический питч (дословный), ГЛАВНОЕ ПРАВИЛО «всегда вопрос после информации», 6 примеров диалогов
- Софья → София (глобально в RIZALTA)
- Greeting: «Здравствуйте! Это София, агентство Оазис. Вам удобно сейчас разговаривать?»
- Первый тестовый звонок — «в целом приемлемо, не идеально, ударения и паузы требуют доработки»

### Баг найден и пофиксен в процессе
- `<speak>` обёртка SSML ломала ElevenLabs streaming endpoint (30s timeout) — убрана, breaks идут инлайн

**Ключевые метрики:**
- Латентность: ~1000ms → ~600-700ms (perceived)
- Качество русского LLM: 3/5 → 5/5 (kimi-k2 vs llama-4-scout)
- TTS TTFB: ~960ms → ~300ms

**Коммиты DEV:** `7f4c96a2` (radist dedup)
**Файлы на VPS:** voice_asterisk.py, core/pipeline.py, .env (прямые правки, без git)

---

## 08.04.2026 — Bitrix-Radist интеграция + RIZALTA промпт + git recovery

**Сделано:**

### Git recovery после краша
- Восстановлен контекст: 5 uncommitted файлов в DEV, 9 в PROD
- DEV: 3 коммита (Bitrix-Radist, docs, TTS model switch)
- PROD: 5 коммитов по каналам (core/bitrix, Telegram, Radist, Web API, docs)
- PROD push заблокирован by design (push URL = `no_push`)

### Bitrix-интеграция в Radist gateway (задача из прошлой сессии)
- Таблица radist_leads, привязка к ATL-лидам через find_recent_atlantis_lead
- Таймауты 15/60/15 мин (аналог bot_server.py)
- manager_active guard, финализация
- Окно матчинга 60 секунд в find_recent_atlantis_lead (core/bitrix.py)
- find_user_id_by_lead расширен для telegram_leads + radist_leads

### RIZALTA голосовой промпт
- Добавлена константа VOICE_SYSTEM_PROMPT_RIZALTA в core/pipeline.py
- Переключатель VOICE_PROMPT_MODE (env, default "atlantis")
- Обнаружено: voice_asterisk.py имеет захардкоженный greeting в _send_greeting()
- Фикс: переключатель в _send_greeting() по VOICE_PROMPT_MODE
- Промпт v1 (скриптовый, 3 диалога) → заменён на goal-oriented v1 (минималистичный)
- Деплой на VPS sofia-voice, .env VOICE_PROMPT_MODE=rizalta

### Тестовые звонки (Сергей)
- Звонок 1: Софья отвечала в Atlantis-стиле → найден баг (greeting не переключался)
- Звонок 2: после фикса greeting — RIZALTA-стиль, но диалог "плохой" (ударения, обрыв)
- Звонок 3: goal-oriented промпт — "не очень хорошо, перестала отвечать"
- **Вывод: нужна тонкая настройка промпта, таймингов, stability. Утром продолжим.**

### Прочее
- ElevenLabs TTS model switch: eleven_turbo_v2_5 → eleven_multilingual_v2 (для PVC)

**Коммиты:**
- 12e4bf18 feat: Bitrix CRM integration for Radist channel + 60s lead matching window
- ee24321b docs: session 07.04-08.04
- e72bc253 chore: switch ElevenLabs TTS to eleven_multilingual_v2
- 32c9996d feat(voice): add RIZALTA outbound prompt + VOICE_PROMPT_MODE switch
- 2d51ede5 feat(voice): wire VOICE_PROMPT_MODE switch into voice_asterisk.py greeting
- c47d1f1b feat(voice): goal-oriented RIZALTA prompt v1 (no script, no stages)

**Файлы:** core/pipeline.py, core/bitrix.py, sofia_radist_gateway.py, voice_asterisk.py, CLAUDE.md, BACKLOG.md

**Открытые проблемы для следующей сессии:**
- RIZALTA промпт: диалог обрывается, качество речи плохое
- Нужна тонкая настройка: ElevenLabs parameters, max_tokens, промпт
- Возможно eleven_multilingual_v2 хуже по latency чем turbo_v2_5
- Нужен анализ логов звонков для понимания где именно проблема

---

## 07.04.2026 — Research Qwen3-TTS + ElevenLabs voice tuning + VAD 0.4s + промпт-дамп

**Сделано:**

### Research: Qwen3-TTS качество для голосовой Софии
- Исследованы 5 API для Qwen3-TTS: WaveSpeed AI, DashScope (Alibaba), fal.ai, Replicate, HuggingFace
- Выбран WaveSpeed AI ($1 free credit, REST API, без карты)
- Сгенерировано **30 аудиофайлов** с реальными фразами Софии:
  - 20 базовых: 5 фраз × 4 голоса (Vivian, Serena, Sohee, VoiceDesign)
  - 10 со стилями: 3 голоса × 3 style_instruction + 2 voice_description варианта
- Файлы в `/tmp/qwen3_tts_test/`, REPORT.md с таблицей
- Вывод: для production нужен DashScope (streaming, Katerina для русского, $0.115/10k chars) или self-hosted GPU

### ElevenLabs Voice Settings (по настройкам Сергея из UI)
- stability: 0.5 → **0.35** (более выразительный)
- similarity_boost: 0.75 → **0.79**
- speed: **1.19** (новый параметр, top-level в API body)
- style и use_speaker_boost — протестированы, убраны (добавляли латентность)

### VAD threshold снижен
- VAD_SILENCE_THRESHOLD: 0.7s → **0.4s** (-300ms ощущаемой паузы)
- Задача A1 из бэклога выполнена (1.2 → 0.7 → 0.4)

### Промпт-дамп
- Создан `TASK_DUMP_SOFIA_PROMPTS.md` — полный дамп всех 9 промптов системы
- Карта: какой промпт где вызывается (Extractor → Analyzer → RAG → Generator)
- Анализ логов: 3 голосовых звонка + 1 текстовый диалог за 07.04

### Анализ диалогов — найденные проблемы
- LLM выдумал фейковый номер телефона (+7 123 456 78 90) — критический баг
- "В Сочи → в Туапсе" бессвязная логика (llama-4-scout)
- Реакция на мусор STT ("Эротика", "Зависят облака")
- Длинные ответы для голоса (194-240 символов при лимите 1-2 предложения)

**Коммиты:** TBD (текущий)

**Файлы:** voice_asterisk.py, TASK_DUMP_SOFIA_PROMPTS.md, /tmp/qwen3_tts_test/

**Текущие тайминги (обновлены):**
- VAD silence: **400ms** (было 700ms)
- STT: ~300ms
- LLM: ~500ms
- TTS first byte: ~450-700ms
- **Итого: ~1000ms** (было ~1300ms)

**Следующая сессия:** Сценарий исходящего обзвона — ЖК RIZALTA (сбор информации, оффер, новый промпт)

---

## 06.04.2026 — Голосовой стек: Телфин → Asterisk → AudioSocket → STT/LLM/TTS

**Сделано:**

### Фаза 1: Asterisk + SIP trunk Телфин
- SSH доступ к российскому VPS (`ssh sofia-voice`, 185.207.66.201)
- VPS очищен (x-ui, zabbix удалены, DNS починен, система обновлена)
- Asterisk 20 установлен, PJSIP trunk к sipproxy.telphin.ru:5068 (порт 5090)
- SIP регистрация работает, входящие звонки доходят до Asterisk

### Фаза 2: AudioSocket сервер
- voice_asterisk.py: TCP сервер на порту 9090, протокол AudioSocket (UUID=0x01, Audio=0x10, Hangup=0x00)
- Двусторонний аудиопоток подтверждён (433 фрейма за 8.7 сек, clean hangup)
- Документация протокола исправлена (официальная была неточной)

### Фаза 3: Полный pipeline STT → LLM → TTS
- **Проблема**: Groq/OpenAI/ElevenLabs заблокированы из России (403)
- **Решение**: nginx proxy на основном сервере (72.56.64.91:8095), UFW rule для VPS IP
- STT: Yandex SpeechKit REST (~300ms, напрямую с VPS)
- LLM: Groq llama-4-scout через proxy (~500ms)
- TTS: ElevenLabs Nastya через proxy
- Полный диалог работает: квалификация, ответы по контексту

### Попытка перенести Asterisk на основной сервер
- Телфин ответил 403 Forbidden Ip — IP 72.56.64.91 не в белом списке
- Asterisk на основном сервере отключен, вернулись на VPS

### TTS оптимизация: streaming
- ElevenLabs streaming endpoint + optimize_streaming_latency=4
- MP3 stream → ffmpeg pipe → 8kHz PCM (proper resampling)
- First audio: **~400-500ms** (было 5-8 сек полное ожидание)
- Voice ID исправлен: YjESejviApN7SHrbfnA2 (Nastya, был Jessica)

### Промпт: фикс "Повторите пожалуйста" loop
- LLM не понимал "Завтра" как ответ на "Когда удобнее?"
- Добавлен пример и явное правило для дат/времени в VOICE_SYSTEM_PROMPT

### A1: VAD + barge-in
- VAD silence threshold: 1.2с → 0.7с (-500ms ощущаемой паузы)
- Barge-in: клиент перебивает → TTS мгновенно останавливается
- 5+ фреймов (~100ms) sustained speech для подтверждения barge-in
- Barge-in аудио → VAD → STT → LLM (не теряется контекст)

**Коммиты:** f59186fb → 4c5b34ad (6 коммитов)

**Файлы:** voice_asterisk.py, core/pipeline.py, asterisk/pjsip.conf, asterisk/extensions.conf, asterisk/logger.conf, /etc/nginx/sites-available/llm-proxy

**Текущие тайминги (конец речи → первый звук):**
- VAD silence: 700ms (клиент не ощущает)
- STT: ~300ms
- LLM: ~500ms
- TTS first byte: ~500ms
- **Итого до первого звука: ~1300ms** (ощущаемая пауза ~1300ms)

**Оставлено на завтра:** B1 (filler звуки), A3 (LLM streaming + sentence-level TTS)

---

## 05.04.2026 — Диагностика застрявших лидов, фикс SOFIA_PATH + логирование

**Сделано:**

### Диагностика 4 лидов (264270, 264264, 264260, 264252)
- Все 4 лида "Планировки Атлантис" (SOURCE_ID=397) уже распределены менеджерам — ни один не застрял на София AI (428)
- Клиенты заполнили форму Тильды ночью, но НЕ перешли в Telegram-бот → София их не видела
- Битрикс-робот раздал лиды напрямую, без квалификации Софией
- 0 лидов с ASSIGNED=428 во всём Битрикс с 1 апреля

### Фикс SOFIA_PATH (повтор бага 21.03)
- Prod `.env` не содержал `SOFIA_PATH` → бот использовал дефолт `/opt/sofia-gpt-dev` и писал в DEV базу данных
- Добавлен `SOFIA_PATH=/opt/sofia-gpt` в prod `.env`
- При рестарте таблица `telegram_leads` автоматически создана в prod БД (ранее не существовала)

### Фикс логирования bitrix.py в bot_server.py
- `bot_server.py` не вызывал `logging.basicConfig()` → все `log.info()/warning()` из `core/bitrix.py` молча проглатывались
- Добавлен `logging.basicConfig(level=INFO)` — логи `[sofia.bitrix]` теперь видны в `journalctl -u sofia-gpt`
- Все вызовы `finalize_lead`, `start_distribution_bp`, `set_lead_assigned` теперь логируются

### Деплой в PROD
- Оба фикса задеплоены, `sofia-gpt.service` перезапущен
- Верификация: DB_PATH=/opt/sofia-gpt/sofia_gpt.db, telegram_leads создана, логи видны

**Коммиты:** (текущий)

**Файлы (prod):** /opt/sofia-gpt/.env, /opt/sofia-gpt/bot_server.py

---

## 04.04.2026 — Деплой Bitrix-интеграции в прод, фикс дублей и таймаутов

**Сделано:**

### Диагностика и фикс дублей лидов
- **core/bitrix.py**: `find_lead_by_phone()` — поиск существующего лида по телефону через `crm.lead.list` перед созданием нового
- **core/bitrix.py**: дедупликация в `create_or_update_lead()` — если `lead_id=None` и есть телефон → ищет в Битрикс, обновляет вместо создания

### Деплой finalize_lead + start_distribution_bp в PROD
- **core/bitrix.py**: `finalize_lead()` и `start_distribution_bp()` были только в DEV — задеплоены в PROD
- **bot_server.py**: `restore_assigned()` → `finalize_lead()` (строки 790, 986)
- **web_api.py**: `restore_assigned()` → `finalize_lead()` (строка 272)
- **.env prod**: `BITRIX_BP_TEMPLATE_ID=152`

### Фикс ASSIGNED_BY_ID для БП
- БП 152 не срабатывает при ASSIGNED_BY_ID=428 (София AI)
- **core/bitrix.py**: `finalize_lead()` теперь ставит `BITRIX_BP_ASSIGNED_ID=24932` перед запуском БП (вместо `restore_assigned`)
- **.env**: `BITRIX_BP_ASSIGNED_ID=24932` (dev + prod)

### Фикс краша таймаута (manager_active)
- Таймаут падал: `no such column: manager_active` — колонка не в `state_manager.py`
- **state_manager.py**: добавлены `manager_active` и `finance_interested` в ClientState, get_state(), _save_state(), CREATE TABLE
- **bot_server.py**: ALTER TABLE миграции в init_db() (не зависеть от web-api)

### Фикс webhook-токена
- Старый токен (`z61d...`) не имел прав на `bizproc` → ошибка "higher privileges"
- **.env**: новый `BITRIX_BASE_URL` с токеном `uviwr0b350u3m6gf` (crm + bizproc)

### Фикс Тильды
- Redirect вёл на dev-бота (`SofiaDev01_bot`) → клиенты не попадали в прод
- Исправлено на `t.me/humanAINeural_bot?start=ATL`

### Документация
- **docs/LEAD_LIFECYCLE.md**: полная архитектура интеграции с CRM, конфигурация, масштабирование
- **docs/NEW_CLIENT_ONBOARDING.md**: пошаговая инструкция подключения нового ЖК

### Успешный E2E тест
- Форма Тильды → лид #264242 в Битрикс → /start ATL → привязка → 15 мин таймаут → ASSIGNED=24932 → BP 152 started → статус лида изменился

**Коммиты:** 276aebf6 → 9ee60d22 (5 коммитов)

**Файлы:** core/bitrix.py, bot_server.py, web_api.py, state_manager.py, docs/LEAD_LIFECYCLE.md, docs/NEW_CLIENT_ONBOARDING.md, BUILD_REPORT_BITRIX_DEPLOY.md

**Логи:** бот пишет в файл `/opt/sofia-gpt/sofia_bot.log` (не journalctl!), Bitrix-операции — в journalctl через logging

---

## 02.04.2026 — Битрикс: запуск БП раздачи после квалификации

**Сделано:**
- **core/bitrix.py**: `start_distribution_bp(lead_id)` — вызов `bizproc.workflow.start` с TEMPLATE_ID из env; `finalize_lead(db_path, lead_id)` — обёртка restore_assigned + BP start; `build_qualification_summary(state)` — итог квалификации в COMMENTS (цель, бюджет, оплата, созвон)
- **bot_server.py**: оба пути финализации (`_finalize_timeout` и `delayed_response`) используют `finalize_lead()` вместо `restore_assigned()`
- **.env**: `BITRIX_BP_TEMPLATE_ID=152`
- Radist не затронут — у него нет Bitrix-интеграции (P1 задача)
- web_api.py и voice_api.py не изменены

**Коммиты:** c1987ff5

**Файлы:** core/bitrix.py, bot_server.py, .env, BUILD_REPORT_BITRIX_BP.md

---

## 30.03.2026 — CLAUDE.md: шаблон промптов для Claude Code

**Сделано:**
- Добавлена секция «Промпты для Claude Code» в CLAUDE.md — формат "Задача готова когда" с проверяемыми критериями (3–6 на задачу)

**Коммиты:** 1

**Файлы:** CLAUDE.md

---

---
