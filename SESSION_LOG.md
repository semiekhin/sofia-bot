# SESSION_LOG — Последние сессии

> 📁 **Архив старых сессий:** [SESSION_LOG_ARCHIVE.md](SESSION_LOG_ARCHIVE.md). Если нужен контекст по старым сессиям — читать оттуда.

## 06.05.2026 — ATLANTIS-виджет: post-deploy polish prompt_addon (бренд + жаргон в PDF)

### TL;DR

Микро-итерация после live-smoke виджет-Sofia 06.05 утром (по итогам PORTBACK 05.05). Smoke прошёл правильно по логике (квалификация по чек-листу, факты карточки реактивно, контакт получен, созвон назначен, PDF в финальной точке) — но Сергей нашёл два косметических замечания в реальных репликах: (1) Sofia представилась «помощник отдела продаж Oazis Estate» — упоминание бренда агентства некорректно по контексту виджета (клиент только что был на сайте Атлантиса, агентство называть не нужно) + мешает будущему масштабированию на других заказчиков; (2) фраза отправки PDF «Накину вам презентацию» — жаргонизм с двусмысленным оттенком (может читаться как «накину сверху» = повышу цену). Решение — две точечные правки текста `prompt_addon` в `config/source_objects.py` обоих репо. Никаких изменений логики, никакого portback'а, никаких новых полей конфига.

### Хронология коммитов

| # | Репо | SHA | Subject |
|--:|------|------|---------|
| 1 | DEV | `27cb23c4` | refactor(atlantis): polish prompt_addon - drop brand mention in greeting, ban slang in PDF send. (push origin/main `d53a4a47..27cb23c4`) |
| 2 | PROD | `a8d0921e` | refactor(atlantis): polish prompt_addon - drop brand mention in greeting, ban slang in PDF send. (без push by-design) |

### Sprint — ATLANTIS_PROMPT_ADDON_POLISH_v1

**Investigate (STOP #1):**
- md5 файлов: PROD `4e8308fd152c1b65093088367c0f5c00`, DEV `89ae82f2ebe5134c469a73b7b27d2108` — **различаются** на уровне файла (известный black-cosmetic drift на функциях `detect_source/load_object_context` в PROD vs DEV, отложен).
- md5 значения **`prompt_addon` в runtime через `importlib`**: оба `a6673db6729e0426ad5e6badb9a0820a` (3464 байт) — **идентичны побайтно**. Это правильный критерий синхронности после ATLANTIS_WIDGET_PROMPT_ADDON_v1 (05.05): на уровне поведения LLM текст совпадает, на уровне файла отличается из-за pre-existing формата.
- Точки вставки: блок «ПЕРВАЯ РЕПЛИКА» — после образца (строка 32 DEV/PROD) перед фразой про локацию (строка 34); блок «ПРЕЗЕНТАЦИЯ (PDF)» — после пункта 4 (строка 48), перед заголовком `ЗАПРОС КОНТАКТА` (строка 50). Структура SOURCE_OBJECTS обоих репо совпадает по строкам.
- Snapshots: `/tmp/source_objects.py.{prod,dev}.before_addon_polish_20260506_082633` (9519 / 9567 байт).

**Edit (одинаковый текст в обоих репо, 4 правки = 2 блока × 2 репо):**

В блок «ПЕРВАЯ РЕПЛИКА» добавлен один абзац после образца:
```
Не упоминай в первой реплике название агентства / бренд («Oazis Estate» и т.п.) — клиент пришёл с сайта объекта, его внимание на проекте, не на агентстве.
```

В блок «ПРЕЗЕНТАЦИЯ (PDF)» добавлен один абзац после пункта 4:
```
Формулируй отправку презентации нейтрально и официально: «Отправлю вам презентацию для ознакомления» / «Вот презентация Атлантиса». Не используй жаргонные обороты: «накину», «держите», «лови», «кину», «скину» — они звучат фамильярно или двусмысленно (например, «накину» читается как «повышу цену»).
```

**Деплой:**
- Smoke load: оба assert'а прошли (`'Oazis Estate' in addon` + `'накину' in addon.lower()`), длина addon 3464 → **3920 байт** (+456, два абзаца с пустыми строками-разделителями), runtime md5 `4f08421d2e5cabd2b246b62be6fdc515` × 2 идентичны.
- AST-syntax обоих файлов ok.
- 5 рестартов: sofia-radist-dev + sofia-web-api-dev (DEV) + sofia-radist + sofia-web-api + sofia-gpt (PROD) — все active, 0 ERROR/Traceback/Exception в журналах за 2 минуты, 4 health-endpoint'а ok (`:5001`/`:5002`/`:8080`/`:8081`).
- DEV pre-commit hook: flake8 + black прошли.
- DEV push в `origin/main`: `d53a4a47..27cb23c4`.
- PROD коммит локально без push (by-design).

### Финальные md5 после сессии

| Файл | до 06.05 | после 06.05 |
|---|---|---|
| `/opt/sofia-gpt/config/source_objects.py` | `4e8308fd15...` | `db07133816d8fcddd5193733034eb219` |
| `/opt/sofia-gpt-dev/config/source_objects.py` | `89ae82f2eb...` | `988eac5fc588cb5ad0da857dfe1a803f` |
| `prompt_addon` в runtime (DEV=PROD) | `a6673db672...` (3464) | `4f08421d2e5cabd2b246b62be6fdc515` (3920) |

### Уроки

1. **Runtime-сравнение через `importlib` сильнее md5 файла** для проверки синхронности значения dict-ключа между репозиториями с известным cosmetic drift. После 05.05 PORTBACK файловые md5 разошлись (black-нонформатирование функций PROD vs DEV), но текст addon побайтно идентичен — это корректное состояние «функционально синхронно, косметика отложена». Не путать «файлы разошлись» с «значения разошлись».
2. **Polish после live-smoke — отдельный микро-спринт без portback'а.** Когда основная инфра уже в проде (как 05.05), косметические правки текста делаются прямой Edit в обоих репо без новых файлов / env / конфига. Минимально-достаточное решение по `<anti_overengineering>`.
3. **Расширенная формулировка из контракта vs пример в go-сообщении.** Сергей дал в `<task>` подробный текст с 5 запрещёнными словами + объяснением «накину = повышу цену», а в go-подтверждении упомянул «например... без слов "накину", "держите", "лови" и подобных» — короче. Применил расширенную формулировку из контракта (она шире, явнее) — Сергей подтвердил «согласен».

### Открыто в следующую сессию

- **Live smoke виджет-Sofia 06.05** через `t.me/m/Fiw3ldhkN2My` — Сергей сверяет: (a) первая реплика без слов «Oazis Estate» / без упоминания агентства, (b) фраза отправки PDF нейтральная без 5 запрещённых слов. Если оба пункта чисты — итерация закрыта окончательно. При расхождении — L0 rollback или новая микро-правка формулировки.
- **Carry-over P3:** в PROD `core/pipeline.py:350-358` `stream_voice_response` всё ещё имеет второй блок инжекции `object_context+presentation_url`, в который addon **не пробрасывается**. Atlantis в голос не используется — если когда-нибудь вернётся, новые запреты на бренд/жаргон тоже не дойдут до voice-промпта. Не блокер.
- **Carry-over from 05.05 cosmetic drift:** PROD `config/source_objects.py` всё ещё не black-форматирован (drift на `detect_source`/`load_object_context`). Backlog P2 «chore(format): backport black on source_objects.py from dev to prod» остаётся открытым.

### Snapshots

- `/tmp/source_objects.py.prod.before_addon_polish_20260506_082633` (9519 байт)
- `/tmp/source_objects.py.dev.before_addon_polish_20260506_082633` (9567 байт)

---

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
