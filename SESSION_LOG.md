# SESSION_LOG — Последние сессии

> 📁 **Архив старых сессий:** [SESSION_LOG_ARCHIVE.md](SESSION_LOG_ARCHIVE.md). Если нужен контекст по старым сессиям — читать оттуда.

## 20.05.2026 (вечер) — gpt-5.4 миграция + reminder 15мин + cancel-restart + webhook-dedup (⚠️баг) + [SPLIT] (большой день деплоев)

### TL;DR

Крупный день: миграция модели **gpt-5.2 → gpt-5.4** + 4 новых архитектурных фикса (каждый задеплоен в PROD) + 2 forensics. Хронологически 7 спринтов. (1) **OPENAI_MIGRATION_GPT54_v1** — gpt-5.4 для Extractor/Analyzer/Generator через env, `reasoning.effort`/`max_output_tokens` не трогали, smoke @SofiaOazis прошёл. (2) **REMINDER_TIMEOUT_15MIN_ENV_v1** — `TIMEOUT_REMINDER` 60→15 мин через env `REMINDER_TIMEOUT_MIN`, цикл «замолчал → напоминание → финализация» сокращён 75→30 мин. (3) **REMINDER_TIMER_FORENSICS_v1** — таймер детерминирован, кажущийся недетерминизм объясняется stage-guard'ом. (4) **MESSAGE_BURST_HANDLING_FORENSICS_v1** (read-only) — вердикт: нужен cancel-restart вместо complete-then-rerun. (5) **MESSAGE_BURST_CANCEL_RESTART_v1** — реализован, smoke ок. (6) **WEBHOOK_DEDUP_v1** — дедуп по `message_id` задеплоен, но **⚠️ ПОДТВЕРЖДЁН БАГ: не срабатывает в PROD**. (7) **FIRST_MESSAGE_SPLIT_v1** — разделение первого ответа (PDF + квалификационный вопрос) на 2 Telegram-сообщения с паузой 2с через маркер `[SPLIT]`, smoke ок. Параллельно — устранены SSH-обрывы (упрощён `~/.ssh/config`). **Открытый P0 на завтра: WEBHOOK_DEDUP forensics + фикс.**

### Хронология коммитов

| # | Спринт | DEV (push) | PROD (без push by-design) |
|--:|--------|-----------|---------------------------|
| 1 | OPENAI_MIGRATION_GPT54 | — (env-only, `.env`) | `.env` `OPENAI_MODEL_{EXTRACTOR,ANALYZER,GENERATOR}=gpt-5.4` |
| 2 | REMINDER_TIMEOUT_15MIN | `102b2b33` | `e12195fc` |
| 3 | MESSAGE_BURST_CANCEL_RESTART | `f28de88c` | `6020e501` |
| 4 | WEBHOOK_DEDUP | `19dfb43f` | `cfd1262c` |
| 5 | FIRST_MESSAGE_SPLIT | `5488fb4e` | `15434b28` |

### Sprint 1 — OPENAI_MIGRATION_GPT54_v1

Миграция Extractor/Analyzer/Generator с `gpt-5.2` на `gpt-5.4` через env-переменные `OPENAI_MODEL_{EXTRACTOR,ANALYZER,GENERATOR}` (механизм добавлен 19.05 вечер). PROD `.env` обновлён, 5 сервисов рестарт. **`reasoning.effort` и `max_output_tokens` НЕ менялись** — только имена моделей. Smoke в @SofiaOazis прошёл: Sofia корректно отвечает на gpt-5.4. Снапшоты `/tmp/env.{prod,dev}.before_gpt54_migration_20260520`. **Baseline-сбор расхода токенов на gpt-5.4 начинается с сегодня** — опережает deprecation gpt-5.2 (5 июня 2026).

### Sprint 2 — REMINDER_TIMEOUT_15MIN_ENV_v1 (`102b2b33` DEV / `e12195fc` PROD)

`TIMEOUT_REMINDER` сокращён 60 → 15 мин через env `REMINDER_TIMEOUT_MIN=15`. Цикл «клиент отвечал → замолчал → напоминание → финализация» теперь **30 мин** (было 75). `docs/LEAD_LIFECYCLE.md` раздел 4 обновлён. Подтверждено в смоке: 12:55 stage-guard корректно **заглушил напоминание** на лиде #272120 в `stage=11` (by-design — лид уже не NEW, менеджер в работе).

### Sprint 3 — REMINDER_TIMER_FORENSICS_v1

Read-only (начат вчера, довод сегодня). Подтверждено: reminder-таймер **детерминирован**. Наблюдавшийся «недетерминизм» (напоминание иногда не приходит) полностью объясняется **stage-guard'ом**: если лид в Bitrix уже не в статусе NEW (менеджер взял в работу), `radist_send_reminder` молча подавляет отправку. Не баг.

### Sprint 4 — MESSAGE_BURST_HANDLING_FORENSICS_v1 (read-only)

Разведка как Sofia обрабатывает серию быстрых сообщений. Вердикт: текущая схема **complete-then-rerun** (дообрабатывает текущий ответ, потом перезапускает на combined-тексте) — нужен **cancel-and-restart** (отменить текущую обработку при новом сообщении). Дало контракт для Sprint 5.

### Sprint 5 — MESSAGE_BURST_CANCEL_RESTART_v1 (`f28de88c` DEV / `6020e501` PROD)

Реализован cancel-and-restart: новое сообщение во время обработки отменяет текущий task и рестартует на combined-тексте → **один ответ** вместо нескольких. Smoke 12:35: 4 сообщения залпом → 3 cancel-rerun → один ответ. **Замечание:** cancel-restart выгоден только на быстром залпе (**<3с** между сообщениями); на паузах 5-10с может быть медленнее старой модели из-за повторного запуска Extractor.

### Sprint 6 — WEBHOOK_DEDUP_v1 (`19dfb43f` DEV / `cfd1262c` PROD) ⚠️ БАГ

Дедупликация входящих webhook по `message_id` (in-memory `set` + `deque(maxlen=1000)`, ранний 200 OK + лог `[DEDUP]` при дубле, без БД/Redis). Реализация прошла линт/smoke на старте сервисов. **НО ⚠️ в боевом смоке 13:18 дедуп НЕ сработал:** три webhook'а с текстом «у меня 60» прошли все три, ни одной `[DEDUP]` строки в журнале. **Гипотеза:** Radist присылает **разные `message_id`** у дублей (ретрай меняет id), либо поле извлекается не из того места payload. **Фикс отложен на завтра** (read-only разведка реального payload — сравнить `message_id` у группы дублей одного текста). См. новый P0 в BACKLOG.

### Sprint 7 — FIRST_MESSAGE_SPLIT_v1 (`5488fb4e` DEV / `15434b28` PROD)

Разделение первого ответа Sofia (PDF-ссылка + квалификационный вопрос) на **два** Telegram-сообщения с паузой **2 сек** через маркер `[SPLIT]`: инструкция в `prompt_addon` Атлантиса (`config/source_objects.py`) + парсинг в `send_callback` (`sofia_radist_gateway.py`) — split → strip частей → `asyncio.sleep(2.0)` между; без маркера одна отправка как раньше; в `radist_messages` сохраняется одним блоком. Smoke 13:17 успешен: интервал отправки **2.4 сек**, второй ответ (13:18) одним сообщением — split применился **только к первому касанию с PDF**.

### Параллельно — фикс SSH-обрывов

Упрощён `~/.ssh/config`: устранены дубликаты блоков `Host sofia-dev` (×2) и `Host 72.56.64.91` (×2), keepalive подкручен (`ServerAliveCountMax` 5→10), добавлен `IPQoS=throughput`. Обрывов после правки не было.

### Уроки

1. **Дедуп по message_id предполагает что у дублей один id — проверять до реализации.** WEBHOOK_DEDUP_v1 был корректно написан и задеплоен, но в смоке не сработал: дубли Radist, по-видимому, приходят с разными `message_id`. Урок: при дедупе по внешнему ключу — сначала read-only собрать реальные дубли из журнала и убедиться что ключ действительно совпадает, потом писать дедуп. (Forensics-первым на ключ дедупа, как и forensics-первым на изменение канала — 19.05.)
2. **Smoke в PROD ловит то, что smoke на старте сервиса не ловит.** Сервис поднялся чисто, `[DEDUP]`-код синтаксически рабочий — но семантический провал (id не совпадают) виден только на живом потоке дублей. Деплой ≠ работает; подтверждение работы — отдельный шаг (живой smoke).
3. **cancel-restart — не бесплатный выигрыш.** Выгоден на быстром залпе, на медленном вводе (паузы 5-10с) повторный Extractor может сделать ответ медленнее старой модели. Любой «улучшающий» рефактор обработки очереди оценивать на двух режимах ввода (залп vs медленный набор).

### Открыто в следующую сессию

- 🔴 **P0 WEBHOOK_DEDUP не работает — forensics payload Radist.** Первая задача завтра: read-only разведка — собрать группу дублей одного текста из журнала, сравнить их `message_id`. Если id разные → дедуп по message_id невозможен, нужен другой ключ (например `text + chat_id` в коротком time-window). Затем фикс.
- 🟡 **P2 Двойной ответ Sofia на серию сообщений** — частично закрыт cancel-restart'ом; оставшаяся часть (дубли webhook'ов) завязана на WEBHOOK_DEDUP.
- 🟡 **P2 Гибкость `source_object`** — вернуть клиента с другим интересом (carry-over).
- 🟢 **Baseline-сбор расхода токенов на gpt-5.4** — продолжается, связан с P2 prompt-caching (брать после 24-48ч).

### Snapshots

`/tmp/env.{prod,dev}.before_gpt54_migration_20260520` (gpt-5.4), `/tmp/sofia_radist_gateway.py.{prod,dev}.before_webhook_dedup_20260520` (webhook-dedup), `/tmp/{source_objects.py,sofia_radist_gateway.py}.{prod,dev}.before_split_20260520` ([SPLIT]) — L1 rollback'и сегодняшних правок.

---

## 19.05.2026 (вечер) — OPENAI_USAGE_LOGGING deploy + smoke + 2 read-only forensics (Тильда/Атлантис, Analyzer skip)

### TL;DR

Длинная вечерняя сессия. (1) **OPENAI_USAGE_LOGGING_PROD_DEPLOY_v1** — split-deploy `[USAGE]`-логирования по компонентам и env-переменных `OPENAI_MODEL_{EXTRACTOR,ANALYZER,GENERATOR}` (default `gpt-5.2`). PROD `7b5eec16` (без push by-design), DEV `cc4ee76c` запушен. Сессия дважды обрывалась по SSH (нестабильность канала) — оба раза на STOP-поинтах, состояние сохранилось. (2) **Smoke-тест в PROD** — Сергей провёл 3-турн диалог через @SofiaOazis (user -40076372, prefilled «Здравствуйте, отправьте, пожалуйста, презентацию АК "Атлантис"»). Результат разрешил **carry-over P0 от утренней сессии**: конфликт «ПЕРВАЯ РЕПЛИКА vs Случай 4» de-facto в пользу Случая 4 — Sofia на турне 1 сразу отправила PDF, не уходя в квалификацию. (3) **TILDA_ATLANTIS_DISCONNECT_FORENSICS_v1** — read-only разведка после утверждения админа Bitrix «Тильда-лиды Атлантиса перестали приходить». Через прямой запрос `crm.lead.list` доказали, что лиды SOURCE_ID=397 приходят непрерывно (159 шт. с 19.04, 68 за последние 7 дней, последний сегодня 15:30 МСК) — admin неправ или смотрел на другую метрику. (4) **ANALYZER_SKIP_FORENSICS_v1** — read-only разведка наблюдения «Analyzer = 0 вызовов» из (1). Вердикт **by-design**: для source_object-клиентов Analyzer пропускается **первые 3 турна** (off-by-one в комментарии кода говорит «≤2», фактически 3 из-за отложенного `save_user_and_notify`). Турн 4+ → Analyzer fires нормально. P1 закрыт.

### Хронология коммитов

| # | Репо | SHA | Subject |
|--:|------|------|---------|
| 1 | DEV | `cc4ee76c` | feat(openai): env-overridable model names + [USAGE] logging per component (push `bfb063a2..cc4ee76c`) |
| 2 | PROD | `7b5eec16` | feat(openai): env-overridable model names + [USAGE] logging per component (без push by-design) |
| 3 | DEV | `36bb809d` | session-end 19.05.2026 (вечер): OPENAI_USAGE_LOGGING_PROD_DEPLOY split + Analyzer 0 observation + ротация 21.04 в архив |

### Фаза A — read-only sanity check (до обрыва SSH №1)

Сравнили DEV-патч с состоянием PROD до коммита. **Расхождение на один hunk в `core/pipeline.py`:** `import os` в DEV уже лежал на module-level, в PROD — внутри `_get_client()`. Новые module-level константы `ANALYZER_MODEL = os.getenv(...)` / `GENERATOR_MODEL = os.getenv(...)` без подъёма импорта падают с `NameError` на module-load. `extractor.py` — diff байт-в-байт идентичен. Снапшоты L1 rollback положены в `/tmp/{env,extractor.py,pipeline.py}.prod.before_usage_logging_20260519`. STOP-point: подъём `import os` — обязательная адаптация под структуру DEV-коммита, не самовольное расширение скоупа. Оркестратор дал go.

### Фаза B — deploy (после восстановления SSH)

Линейно: `git add` → commit (без `--no-verify` обходов, with `--no-verify` исключительно для скоупа PROD-репо без pre-commit hook'а на чужом git config) → последовательный рестарт `sofia-radist` → `sofia-web-api` → `sofia-gpt` с 3-секундной паузой и `is-active` проверкой между. Все три active. ActiveEnterTimestamp 2026-05-19 19:01:56 / 19:02:05 / 19:02:16 MSK.

Журнал ошибок старта (`grep -iE "error|traceback|exception|importerror|nameerror|syntaxerror" --since "2 min ago"`): пусто. Sanity-check на непустой журнал: 13 / 17 / 26 строк за окно, tail каждого сервиса показывает нормальный startup (Radist Gateway v2.0 + webhook + каналы max/telegram; Uvicorn на 8080; sofia-gpt long polling Telegram API HTTP 200).

DEV push: `bfb063a2..cc4ee76c main → main`.

### Наблюдение из baseline-сбора — Analyzer 0 вызовов

После рестарта PROD-сервисов в логах появились `[USAGE]` строки от Extractor и Generator, но **Analyzer не отметился ни одним вызовом**. По архитектуре `core/pipeline.py`: Analyzer **пропускается** при `state.source_object AND user_msg_count <= 2` (source-routing) И при `voice_mode=True`. Текущий трафик PROD идёт почти полностью через `@SofiaOazis` Radist (Atlantis/RIZALTA), где `source_object` детектится на первой реплике → Analyzer глушится на 1-2 сообщениях, а дальше клиент финализируется в течение нескольких реплик. Поставлено P1 на расследование, разобрано отдельным sprint'ом ниже (`ANALYZER_SKIP_FORENSICS_v1`) — вердикт **by-design**.

### Smoke-тест в PROD после деплоя (user -40076372, 3 турна)

Сергей провёл живой smoke через @SofiaOazis Business Link `t.me/m/QinKZEsTNmRi` (новая ссылка с 19.05 утром, prefilled-текст «Здравствуйте, отправьте, пожалуйста, презентацию АК "Атлантис"»). Цель — разрешить **carry-over P0 от утренней сессии**: конфликт в `prompt_addon` между блоком «ПЕРВАЯ РЕПЛИКА» (мягко в квалификацию) и «ПРЕЗЕНТАЦИЯ Случай 4» (отправь когда прямо попросили).

**Хронология (radist_messages, MSK):**
| Турн | Время | Кто | Реплика (excerpt) |
|------|-------|-----|-------------------|
| 1 | 19:07:08 | user | «Здравствуйте, отправьте, пожалуйста, презентацию АК "Атлантис"» |
| 1 | 19:07:08 | Sofia | «Да, конечно) Вот презентация АК «Атлантис» для ознакомления: https://api.atlanti...» |
| 2 | 19:07:26 | user | «инвестиции» |
| 2 | 19:07:26 | Sofia | «Отлично!) Тогда подскажите, в каком бюджете комфортно смотреть покупку: до 15 мл...» |
| 3 | 19:11:08 | user | «хотелось бы цены узнать» |
| 3 | 19:11:08 | Sofia | «Да, конечно) По «Атлантису» сейчас цены такие: студии от 16,8 млн, 1-спальня от ...» |

**Результат:** Sofia на турне 1 **сразу отправила PDF**, не уйдя в квалификацию. Случай 4 победил Случай «ПЕРВАЯ РЕПЛИКА» в условиях прямой просьбы. **P0 от утренней сессии разрешён de-facto, точечная правка `prompt_addon` не требуется.** Также подтверждено: после PDF Sofia корректно переходит в квалификацию (бюджет, далее цены) — двух-фазный flow работает чисто.

Bitrix-cторона smoke'а: лид `#272028` создан (`SOURCE_ID=504` — виджет-default, не 397 — `find_recent_atlantis_lead` вернула `0 лидов` как ожидалось — нет Тильда-формы в 60-сек окне) с `ASSIGNED_BY_ID=428` (Sofia AI), `TITLE="AI-бот: ..."`. На турне 2 + 3 — `update_lead` обновляет comments.

### Sprint TILDA_ATLANTIS_DISCONNECT_FORENSICS_v1 (read-only)

**Контекст.** Админ Bitrix утверждал, что Тильда-лиды Атлантиса перестали приходить. Оркестратор подозревал путаницу с RIZALTA-bypass 29.04, но также допускал возможность забытой правки. Цель — установить факты.

**Метод.** 8 параллельных read-only проверок: git log обоих репо 25.04-05.05, детальный осмотр 29.04 коммитов, grep на Atlantis-guards в PROD-коде, `.env` review, webhook-receiver инспекция, прямой `crm.lead.list` к Bitrix REST API.

**Ключевые находки.**

1. **29.04 RIZALTA sprint** (`9947721d` DEV / `3be32d68` PROD): затронул `config/source_objects.py` (только rizalta-блок добавлен), `core/bitrix.py` (`title_override` параметр срабатывает строго при `source_object == "rizalta"`), `sofia_radist_gateway.py` (`_is_radist_bitrix_session` shorts только для rizalta). **Atlantis-блок и atlantis-flow не тронуты ни в одном файле.**

2. **04.05 BOT_BITRIX_ENABLED=false** (`b7bbd500` PROD): затрагивает **только @humanAINeural_bot** (legacy-канал, новых ATL-клиентов через него нет с 08.04 per CLAUDE.md). Atlantis через @SofiaOazis Radist не затронут.

3. **Bitrix REST подтверждение** (`crm.lead.list` с фильтром `SOURCE_ID=397 AND DATE_CREATE>=2026-04-19`): **159 лидов** за месяц, **68 за последние 7 дней**, **последний сегодня 15:30 МСК** (ID=271982 «Клиент #Презентация в WhatsApp Атлантис»). Поток непрерывный. Распределение форм: «Атлантис_попап квиз таймер» (25), «Планировки Атлантис» (18), «Обратный звонок Атлантис» (10), «Презентация в WhatsApp Атлантис» (8).

4. **`find_recent_atlantis_lead` всегда возвращает 0 лидов** с 05.05 (21 вызов из журнала). Не потому что Тильда-лидов нет, а потому что **60-сек окно почти никогда не совпадает с моментом виджет-клика** — Тильда-формы и виджет-флоу почти не пересекаются. Sofia последний раз привязалась к 397-лиду через `find_recent_atlantis_lead` 07.04 (`#264372`, `#264518`). С тех пор `ASSIGNED=428` на 397-лидах не появляется.

5. **Webhook `/api/bitrix/webhook`** (`web_api.py:605`): за 12+ ротированных файлов nginx и месяц journalctl — **0 POSTов**. Это не канал прихода Тильда-лидов (Тильда POSTит в Bitrix напрямую), а subscription для `ONCRMLEADUPDATE` — Stetsenko до сих пор не настроил подписку на стороне Bitrix (известный P2 carry-over).

**Вердикт.** Тильда-Атлантис поток **в порядке**. Гипотеза: оркестраторская память про «отключение 29.04» — путаница с RIZALTA-bypass. Заявление админа — фактически неверно либо он смотрел на другую метрику (возможно «Sofia больше не привязывается через `find_recent_atlantis_lead`», что правда — но это не «лиды не приходят»). Уверенность **высокая**, доказательство — прямой Bitrix REST.

**Обнаружено побочно:**
- `find_recent_atlantis_lead` фактически dead code для текущего трафика (21 вызов, 0 успехов с 05.05) — Тильда-формы ведут в WhatsApp/звонок/PDF, не в Telegram. Архитектурный вопрос на отдельный sprint.
- `docs/ATLANTIS_WIDGETS_STATE.md` пишет про «60-сек коллизию» как риск — реальные данные показывают что Тильда и виджет потоки **практически не пересекаются**, надо обновить документ.

### Sprint ANALYZER_SKIP_FORENSICS_v1 (read-only)

**Контекст.** Из (1) и (2): после деплоя `7b5eec16` и smoke-теста 3-х турнов user'а -40076372 — Analyzer ни разу не вызвался. Оркестратор подозревал by-design (но не помнил точной семантики), баг или silent exception.

**Метод.** Прочитать source-of-truth `core/pipeline.py:109-185`, проследить flow `save_message` → `get_history` → `run_pipeline` в `sofia_radist_gateway.py`, проверить DB-state user'а -40076372, сравнить с DEV.

**Условие skip (`pipeline.py:115`):**
```python
if state and state.source_object and user_msg_count <= 2:
    skip_analyzer = True
```
Плюс `voice_mode=True` всегда пропускает (`:142`).

**Ключевая механика.** `user_msg_count = sum(1 for m in history if m["role"] == "user")`. Но `save_user_and_notify` отложен в `send_callback` (`sofia_radist_gateway.py:962-973`), исполняется **после** `run_pipeline`. То есть на момент Analyzer-gate текущее user-сообщение **ещё не сохранено** в `radist_messages`. **Off-by-one:** комментарий говорит «≤2 сообщений», фактически skip покрывает **3 первых турна** (user_msg_count = 0, 1, 2).

**Применение к smoke -40076372.** Журнал подтверждает:
```
19:07:01,921 🏷️ Source routing: force stage=GREETING (user_msgs=0, object=atlantis)
19:07:19,777 🏷️ Source routing: force stage=GREETING (user_msgs=1, object=atlantis)
19:11:02,282 🏷️ Source routing: force stage=GREETING (user_msgs=2, object=atlantis)
```
Все 3 турна попали в skip. Турн 4 → `user_msg_count=3` → Analyzer fired бы (но Сергей закончил smoke на 3-м).

**Вердикт.** **By-design**, не баг. Семантика:
- На клиентов с `state.source_object` Analyzer пропускается **первые 3 турна**, форсится `stage=GREETING + rag_query="приветствие клиент с сайта интерес к объекту"`.
- Турн 4+ → Analyzer fires нормально с `reasoning.effort=medium`, `max_output_tokens=1000`. Подтверждено историческими `🧠 Analyzer запрос` 12.05 и 19.05 утром (до деплоя — без `[USAGE]`-логов, но сам факт вызова есть).
- `source_object` никогда не сбрасывается — раз поставлен, живёт навсегда для этого user_id. Условие skip держится только на счётчике, не на самом source_object.

**Финансовая оценка** (грубо, baseline'а пока нет): экономия ~$0.005 на пропущенный турн × 3 турна = **~$0.015 на atlantis-клиента**. Скромно, но Analyzer для GREETING-стадии семантически бесполезен (любой первый ответ — приветствие + ссылка), так что skip — архитектурно правильный shortcut.

**P1 закрывается** — гипотеза «Analyzer dead code» опровергнута. Analyzer работает, просто молчит первые 3 турна по дизайну.

**Обнаружено побочно:**
- Комментарий `pipeline.py:110` («≤2 сообщений») устарел из-за off-by-one — стоит привести в соответствие («3 первых турна» или вынести в `GREETING_FORCE_TURNS = 3`). P3.
- `users.messages_count` (`users` table) и `user_msg_count` (локальное в pipeline) — два независимых счётчика; на radist-канале `users` table вообще не заполняется. Дублирующая логика, не критично. P3.

### Уроки

1. **SSH-обрывы во время длинной сессии — состояние Claude Code сохранилось.** Оба обрыва пришлись на STOP-поинты (между Фазой A и Фазой B; перед финальным push), не во время `systemctl restart` или `git push`. Конкретно из 2-го обрыва: продолжающий промпт оркестратора со снапшотом текущего состояния («что есть на сервере прямо сейчас» + «что осталось сделать») позволил продолжить деплой за <1 мин на чистом контексте. Паттерн «снапшот состояния → resume prompt» становится частью runbook'а для long-running сессий.

2. **Split-deploy с одной адаптационной правкой требует явного callout в commit message.** PROD-коммит `7b5eec16` имеет diff чуть больше DEV (+18 / −18 строк на подъём `import os`), это могло бы показаться рассинхроном при будущем audit'е. В commit body явно объяснено: что отличается, почему, и что эффект на поведение Sofia — ноль (импорты уже проверены, NameError не возникает на module-load). Защита от «через 3 месяца забыли почему».

3. **Внешнее утверждение (admin Bitrix) — НЕ авторитет без data-cross-check.** Админ сказал «Тильда-лиды Атлантиса перестали приходить». Оркестратор подозревал путаницу, но мог бы поверить и начать «искать что отключили». Sergey сразу заказал read-only forensics с прямым `crm.lead.list` запросом. Через 5 минут — 159 лидов SOURCE_ID=397 за месяц, последний сегодня 15:30. Без data-проверки можно было потратить часы на «возвращение Тильда-интеграции», которой и не было сломано. Паттерн: **forensics-перед-доверием-внешнему-утверждению**.

4. **Off-by-one между кодом и комментарием — найти можно только живым smoke'ом.** Условие `user_msg_count <= 2` в `pipeline.py:115` + комментарий «≤2 сообщений» создают иллюзию что Analyzer пропускается 2 турна. Реально пропускает 3 — из-за отложенного `save_user_and_notify`. Это нельзя было увидеть статическим чтением кода, только по факту smoke'а с journal-цифрами `user_msgs=0,1,2`. Урок: после ввода нового логирования (`[USAGE]`) обязательно провести 3-4 турновый smoke и сверить с предполагаемой моделью — отклонения от ожидания почти всегда находят latent quirks.

5. **Umbrella-запись в SESSION_LOG для multi-sprint дня лучше серии отдельных entries.** Эта вечерняя сессия = 1 деплой + 1 smoke + 2 forensics. Можно было разнести на 3 записи (deploy / TILDA-forensics / ANALYZER-forensics), но Sergey попросил «session-end день был долгий и продуктивный» — одной записью. Преимущество: следующий читатель видит контекст «всё связано» (smoke выявил наблюдение → forensics ответил → P0/P1 закрылись), не приходится склеивать из 3 entries.

### Открыто в следующую сессию

- ✅ ~~**Live-smoke виджет-Sofia на новой ссылке**~~ — **закрыто smoke-тестом** (см. выше). Sofia отправляет PDF на первой реплике для prefilled-текста «отправьте презентацию» — Случай 4 победил. Правка `prompt_addon` не требуется.
- ✅ ~~**Расследование Analyzer 0 вызовов**~~ — **закрыто** (см. `ANALYZER_SKIP_FORENSICS_v1`). By-design, off-by-one в комментарии. P1 в BACKLOG помечен закрытым.
- 🟡 **Prompt caching оптимизация в Generator** — P2 (см. BACKLOG), остаётся. Baseline данные накапливаются — стоит брать после 24-48ч.
- 🟢 **Baseline-сбор продолжается** — `[USAGE]` логи накапливаются с 19:01 MSK. Первое реальное измерение Analyzer-стоимости появится когда первый клиент дойдёт до турна 4+ (исторически случается).
- 🟡 **`docs/ATLANTIS_WIDGETS_STATE.md` обновить** — реальные данные за 14 дней показывают что Тильда- и виджет-потоки практически не пересекаются в 60-сек окне (find_recent_atlantis_lead: 21 вызов, 0 успехов с 05.05). Документ позиционирует это как «риск коллизии» — стоит переписать секцию исходя из фактов. P3.
- 🟡 **`find_recent_atlantis_lead` фактически dead code** — последняя успешная привязка 07.04. Архитектурный вопрос: оставить функцию для редкого совпадения «Тильда-форма + Telegram-клик в 60с», упростить, или удалить. Не блокер. P3.
- 🟡 **Комментарий `pipeline.py:110`** — устарел («≤2 сообщений» vs реальные 3 турна). Стоит привести в соответствие или вынести в именованную константу `GREETING_FORCE_TURNS=3`. P3.

### Snapshots

`/tmp/env.prod.before_usage_logging_20260519`, `/tmp/extractor.py.prod.before_usage_logging_20260519`, `/tmp/pipeline.py.prod.before_usage_logging_20260519` — L1 rollback до сегодняшнего PROD-коммита. Хранятся до подтверждения чистой работы baseline-сбора (≥48ч).

---

## 19.05.2026 — Claude Code recon + Atlantis виджет forensics + prompt_addon commit в HEAD

### TL;DR

Сессия из трёх read-only/коммит-only спринтов после смены ссылки виджета на сайте Атлантиса (19.05 утром Сергей переключил `t.me/m/Fiw3ldhkN2My` → `t.me/m/QinKZEsTNmRi` — теперь идентично Тильда-форме с prefilled-текстом «Здравствуйте, отправьте презентацию АК «Атлантис»»). (1) **CLAUDE_CODE_LOCAL_RECON_v1** — инвентаризация локальной Claude Code инсталляции перед началом multi-agent workflow: версия 2.1.144 (≥ v2.1.36 для fast mode и ≥ v2.1.117 для fork — оба требования выполнены), fast mode не активирован (ни одной opt-in env-переменной), custom subagents не настроены, AGENT_TEAMS / FORK_SUBAGENT не включены. (2) **WIDGET_BITRIX_FORENSICS_v1** — пошаговая карта что происходит когда виджет-клиент кликает по новой ссылке: с явной новой ссылкой виджет теперь технически проходит ту же воронку что Тильда, но без Тильда-формы на стороне Bitrix → `find_recent_atlantis_lead` всегда вернёт `None` для виджет-юзеров, создастся новый лид с `SOURCE_ID=504` (не 397), `ASSIGNED_BY_ID=428` (Sofia AI), `TITLE="AI-бот: <name>"`. Реальный 60-сек collision-риск с чужими Тильда-лидами: 0 за последние 14 дней (16/16 `find_recent_atlantis_lead` → 0 лидов), оценка при росте виджет-трафика 1.6% средняя / 7.8% пик. (3) **PROMPT_ADDON_COMMIT_v1** — закоммитили uncommitted prompt_addon полировку в HEAD обоих репо (расширение блока «КАНАЛ ПЕРЕДАЧИ» Max/WhatsApp/TG + полировка случая 2). DEV `418b6b5f` (push), PROD `c72b6122` (без push by-design).

### Хронология коммитов

| # | Репо | SHA | Subject |
|--:|------|------|---------|
| 1 | DEV | `418b6b5f` | refactor(atlantis): prompt_addon — channel-transfer block (Max/WhatsApp/TG) + case-2 polish (push origin/main `73aed3e2..418b6b5f`) |
| 2 | PROD | `c72b6122` | refactor(atlantis): prompt_addon — channel-transfer block (Max/WhatsApp/TG) + case-2 polish (без push by-design) |

### Sprint 1 — CLAUDE_CODE_LOCAL_RECON_v1 (read-only)

Перед введением multi-agent workflow Сергей попросил инвентаризовать локальную Claude Code инсталляцию: версия, Fast mode статус (важно — с 14.05.2026 fast mode переключился с Opus 4.6 на 4.7, опасность случайно включённого = x2 стоимость токенов), доступность Task tool / Subagents / Agent Teams / Fork subagents.

**Ключевые находки.**
- **Версия 2.1.144**, путь `/root/.local/bin/claude`. Удовлетворяет минимумам fast mode (v2.1.36) и fork subagent (v2.1.117).
- **Fast mode НЕ активирован.** Ни одной opt-in env-переменной (`CLAUDE_CODE_ENABLE_OPUS_4_7_FAST_MODE`, `CLAUDE_CODE_OPUS_4_6_FAST_MODE_OVERRIDE`, `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS`, `CLAUDE_CODE_FORK_SUBAGENT`), нет блока `env` в `~/.claude/settings.json` (там только `trustedDirectories` + `effortLevel: xhigh` — НЕ относится к fast mode), нет в `~/.claude/settings.local.json`, нет в shell profiles. Все `CLAUDE_CODE_*` переменные в окружении — служебные (`SESSION_ID`, `ENTRYPOINT`, `EXECPATH`).
- **Custom subagents не настроены.** Ни `~/.claude/agents/`, ни `/opt/sofia-gpt-dev/.claude/agents/`, ни inline `agents:` ключа в settings. Доступны только дефолтные через `Agent` tool: `claude`, `claude-code-guide`, `Explore`, `general-purpose`, `Plan`, `statusline-setup`.
- **Slash-команды загружаются как skills внутри интерактивной сессии**, из `claude --help` напрямую не перечисляются. Подтверждены через косвенные сигналы: `/loop` (skill в user-invocable списке), `/resume` (CLI-флаг `-r`). Не смог проверить из bash без интерактива: `/fast`, `/agents`, `/tasks`, `/config`.
- **Multi-agent инструменты доступны** в текущей сессии через `Agent` tool с `subagent_type`, `model`, `isolation: worktree`, `run_in_background` параметрами. CLI поддерживает `--agents '<json>'` для inline-определения custom agents при запуске сессии. `claude agents` subcommand управляет background-агентами (отдельный механизм от Task-tool subagents).
- **Cloud MCP** (Google Drive / Gmail / Calendar) — все 3 «Needs authentication», не подключены. Project-scope MCP: `enabledMcpjsonServers: ["sqlite"]`.

**Побочные обнаружения.** `/opt/sofia-gpt-dev/.claude/settings.local.json` распух до 14599 байт / 249 entries в `allow`-списке (накопилось за месяцы work-around'ов permission-промптов, многие entries — сиюминутные: `kill 1378804`, конкретные `scp` пути, разовые `WAVESPEED_API_KEY=...`). Кандидат на `/fewer-permission-prompts` skill в будущей сессии. Не блокер.

### Sprint 2 — WIDGET_BITRIX_FORENSICS_v1 (read-only forensics)

Сергей сегодня утром поменял ссылку в виджете на сайте Атлантиса с `t.me/m/Fiw3ldhkN2My` (старая, prefilled-текст «Помогите подобрать квартиру в АК Атлантис») на `t.me/m/QinKZEsTNmRi` (новая, prefilled-текст «Здравствуйте, отправьте презентацию АК «Атлантис»» — **идентично Тильда-форме**). Цель — чтобы Sofia при первом касании виджет-клиента отправляла PDF (как делает для Тильда-клиентов) и начинала квалификацию. До этого виджет-клиент шёл в обычную квалификацию без отправки PDF. Документация (`docs/ATLANTIS_WIDGETS_STATE.md`) писалась когда текст был другой, есть подозрение что `find_recent_atlantis_lead` будет срабатывать по-другому (привязка к чужим Тильда-лидам в 60-сек окне).

**Полная пошаговая карта** (16 шагов от Radist webhook до Sofia ответа, с file:line):
1. Radist `messages.create` webhook → `handle_webhook()` (`sofia_radist_gateway.py:1125`). Парсятся phone (часто пуст), user_name, tg_username, tg_profile_link.
2. `process_with_queue` → `process_message_wrapper` → `user_id = -(2_000_000 + chat_id)`.
3. `detect_source(combined_message)` → matches «атлантис» в guillemets («Атлантис») → `source_object="atlantis"`, `is_first_atl=True`.
4. **Bitrix-bind блок** (`:934-958`): `find_recent_atlantis_lead()` — фильтр `SOURCE_ID=397` за последние 60 сек, сортировка `DATE_CREATE DESC`, MSK.
5. При найденном Тильда-лиде: `save_radist_lead_id`, `save_original_assigned`, `set_lead_assigned(428)`, `update_lead(COMMENTS, telegram_url)`.
6. При `None`: лид будет создан позже (после первой реплики Sofia в `send_callback`).
7. Pipeline: `source_object` + `user_msg_count ≤ 2` → Analyzer пропущен, stage=GREETING форсирован, object_context + presentation_url + prompt_addon инжектируются в system_prompt (`core/pipeline.py:194-207`).
8. `send_callback` (`:1010-1081`): save_message, send_message, observer_ping, `create_or_update_lead`.

**Три ветки виджет-клиента (с реальными SOURCE_ID/ASSIGN/TITLE):**

| Сценарий | find_recent | SOURCE_ID лида | ASSIGNED (после первой реплики) | TITLE | UF_CRM_TELEGRAM |
|----------|-------------|----------------|---------------------------------|-------|------------------|
| Свежий клиент (phone пуст у Telegram Business) | `None` | `504` (default `BITRIX_SOURCE_ID`, в `.env` PROD не задано) | `428` → `24932` (после finalize_lead) | `AI-бот: <user_name>` | `https://t.me/<tg_username>` |
| Повторный клиент с phone | `None`; `find_lead_by_phone` нашёл (только `STATUS_ID=NEW`) | Остаётся прежний у найденного | `update_lead` без перетирания ASSIGN | Прежний | Обновится если `telegram_url` непуст |
| **Коллизия 60-сек** (чужой Тильда-лид) | `{id: X, assigned: Y}` (lead 397) | **Остаётся `397`** (привязка не перезаписывает SOURCE_ID) | `Y → 428` → `24932`. Original Y сохранён в `lead_assigned` | Остаётся прежний (Тильда-формат) | **ПЕРЕЗАПИШЕТСЯ** на виджет-юзера |

**60-сек коллизия — реальная статистика за 14 дней:**
- 16 вызовов `find_recent_atlantis_lead`, все 16 вернули `найдено: 0 лидов`. **0 фактических коллизий.**
- Тильда-лидов (`SOURCE_ID=397`) ≥ 50 за 14 дней (хит page limit). Средняя плотность ~1 лид / 62 мин → P(коллизия) ≈ 1.6% средняя, 7.8% в пик (10-12 утра, наблюдались Тильда-лиды с разрывом 69 сек).
- При росте виджет-трафика до 10-20 сессий в день в часы пик — ожидаем **0.5-1.5 false-bind в день**. При коллизии: stranger's manager «теряет» лид молча (Y сохранён в локальную таблицу, не в Bitrix), `UF_CRM_TELEGRAM` перезапишется виджет-юзером, comments попадут не те.

**Реальные данные** (10 последних радист-лидов из Bitrix): 4 виджет-лида (270596 Диана, 270552 Юля, 270220 sergey_7in, 269534 Изосина) — все `SOURCE_ID=504`, `TITLE="AI-бот: ..."`, `UF_CRM_TELEGRAM=t.me/<username>`, без phone. Старые Тильда-лиды (268062, 268056, 266992 и т.д.) — `SOURCE_ID=397`, real-manager ASSIGN (174264, 77598, 84940), phone из формы. Лиды 270854 / 270858 удалены из Bitrix вручную, но остались в `radist_leads` как привязка к призраку (если эти user_id напишут снова — `update_lead` тихо упадёт, на следующей итерации та же ошибка).

**🔴 Главная новая риск-зона после смены ссылки.** Конфликт в `prompt_addon`:
- Блок `ПЕРВАЯ РЕПЛИКА`: «Даже если клиент в первой реплике сам пишет «расскажите про Атлантис» — отвечай мягко и переходи к квалификации.»
- Блок `ПРЕЗЕНТАЦИЯ (PDF)`: «Случай 4 — Клиент прямо попросил презентацию.»

Для нового prefilled-текста «Здравствуйте, **отправьте презентацию** АК «Атлантис»» — это **буквальный случай 4**, но одновременно **первое сообщение**. Эти два правила в прямом конфликте, поведение LLM непредсказуемо: может отправить ссылку сразу (правильно по интенции замены ссылки), может начать квалификацию (по букве правила «ПЕРВАЯ РЕПЛИКА»). Из кода нельзя предсказать — это поведение `gpt-5.2` на неоднозначном промпте. Требуется live-smoke Сергеем и, скорее всего, точечная правка `prompt_addon` чтобы разрешить конфликт (например: «исключение из правила ПЕРВАЯ РЕПЛИКА — если клиент в первом сообщении прямо просит презентацию, см. ПРЕЗЕНТАЦИЯ Случай 4»).

### Sprint 3 — PROMPT_ADDON_COMMIT_v1

Forensics-спринт выявил что `config/source_objects.py` в обоих репо имеет **НЕзакоммиченные** изменения поверх HEAD (расширение блока «ЗАПРОС КОНТАКТА И КАНАЛ ПЕРЕДАЧИ» + полировка случая 2 «отказ от созвона»). Runtime уже работает по working tree (Python подгружает с диска), но HEAD не содержит этой правки — любой `git checkout` или re-deploy откатит работающее поведение.

**Investigate (STOP #1):** diff DEV vs PROD working tree показал расхождение **только в helper-функциях** `detect_source()` (`:119-124`) и `load_object_context()` (`:137-141`) — DEV black-форматирован (двойные кавычки, многострочный `re.sub`, blank lines), PROD не форматирован (одинарные кавычки, однострочный `re.sub`). **`prompt_addon` текст байт-в-байт идентичен в обоих репо** — это известный ambient cosmetic drift, в этот коммит не лезет. Diff каждого working tree против HEAD — 44 строки, ИДЕНТИЧНЫ в DEV и PROD (одна и та же правка `prompt_addon`).

**Сергей дал «go»** + одну минор-правку: опечатку «експерт» → «эксперт» в commit body исправить перед коммитом.

**Deploy.** `git add config/source_objects.py` (явный путь, untracked не затронуты) → commit в обоих репо. DEV pre-commit hook (`flake8 + black --check`) прошёл без замечаний (`All done! ✨ 🍰 ✨ 1 file would be left unchanged.`). DEV push → `73aed3e2..418b6b5f main → main`. PROD коммит локально без push (`origin push=no_push` by-design). Содержимое source_objects.py не менялось — md5 до = md5 после в каждом репо (DEV `7482de1b…`, PROD `cf5a543a…`).

### Финальные md5 после сессии

| Файл | DEV | PROD |
|------|-----|------|
| `config/source_objects.py` | `7482de1bd18f0d39ff7639247ba31021` | `cf5a543ad888e9466d284d68be2916c0` |

(разные md5 — ambient black-drift на helper-функциях, остаётся как был; `prompt_addon` идентичен побайтно)

### Уроки

1. **STOP-poin при unexpected drift между DEV/PROD спасает от коммита разных вещей.** Контракт запросил «если diff DEV vs PROD оказался содержательным — НЕ предлагать коммит». Diff формально был (4 строки на helper-функциях), но не касался `prompt_addon`. Правильный ответ — остановиться, показать структуру расхождения (где именно отличается, относится ли к scope), и дать оркестратору решить. Сергей подтвердил `go` за минуту после остановки. Молчаливое продолжение коммита (даже если drift косметический) — нарушение скоупа, любая будущая правка ambient-drift'а должна идти отдельным sprint'ом.

2. **Forensics-перед-фиксом для каналов с известной конфигурацией риска.** При смене ссылки виджета Сергей не пошёл сразу править prompt_addon под новый flow — сначала запросил полную карту что технически происходит с новым prefilled-текстом, какие три ветки (свежий / повторный / коллизия), какие SOURCE_ID/ASSIGN/TITLE проставятся в каждой, какие реальные данные за 14 дней говорят про collision-risk. Принципиальное открытие forensics'а — конфликт «ПЕРВАЯ РЕПЛИКА vs Случай 4» в prompt_addon, который существует независимо от смены ссылки, но **активируется именно прямой формулировкой «отправьте презентацию»** в первом сообщении. Без forensics его бы не заметили — он не лежит на поверхности.

3. **Pre-commit hook ловит формальные ошибки до push, но не семантику.** DEV-коммит `418b6b5f` прошёл `flake8 + black --check` чисто. Хорошо. Но опечатку «експерт» в commit body это не поймало (body коммит-сообщения хук не проверяет). Поймал Сергей на STOP-point. Правило для исполнителя: после автоматических проверок ещё раз глазами пройтись по commit message целиком, особенно по русскоязычным фрагментам.

### Открыто в следующую сессию

- 🔴 **Live smoke виджет-Sofia на новой ссылке** — Сергей делает первое реальное обращение через `t.me/m/QinKZEsTNmRi` (или находит первого реального клиента). Что критично проверить: (a) отправит ли Sofia PDF на первой реплике (по Случаю 4), или начнёт квалификацию (по букве «ПЕРВАЯ РЕПЛИКА»). Если PDF → конфликт de-facto разрешён в пользу Случая 4, можно не править. Если квалификация без PDF — нужна точечная правка `prompt_addon` (одно предложение-исключение в блоке ПЕРВАЯ РЕПЛИКА). (b) Создаётся ли лид с `SOURCE_ID=504` и `ASSIGNED_BY_ID=428` — проверить через `crm.lead.get` после первого клиента. (c) Нет ли неожиданной 60-сек коллизии — `journalctl -u sofia-radist | grep find_recent_atlantis_lead` после звонка.
- 🟡 **Carry-over: мёртвые лиды 270854/270858 в `radist_leads` PROD** — записи живут как привязка к удалённым из Bitrix лидам. Если те user_id (`-42772202` Lena Volgina, `-42772545` polina) напишут снова, `update_lead` тихо упадёт. Очистка: `DELETE FROM radist_leads WHERE bitrix_lead_id IN (270854, 270858);`. P3, не блокер.
- 🟡 **Carry-over: `find_lead_by_phone` STATUS_ID=NEW only** (`core/bitrix.py:198`) — повторный клиент с закрытым/конвертированным предыдущим лидом не распознаётся как повторный, появится дубликат. By-design, но для виджет-юзеров без phone дедупликация не работает в принципе. P2 если нужно нормально дедуплицировать виджет-клиентов по telegram username.
- 🟢 **Ambient cosmetic drift `detect_source/load_object_context`** — DEV black-форматирован, PROD нет. Существует с 05.05+, в этой сессии не тронут. Можно отдельным sprint'ом `black config/source_objects.py` в PROD + commit (без push автоматом).
- 🟢 **Multi-agent workflow готов к запуску** — инфра Claude Code 2.1.144 поддерживает (`Agent` tool, `--agents` CLI-флаг, `claude agents` subcommand для background). Fast mode и AGENT_TEAMS можно включить точечно env-переменными когда понадобится — сейчас правильно что выключены (избегаем случайной x2 стоимости).

### Snapshots

Нет новых снапшотов — read-only спринты + только коммит-операции, содержимое файлов не менялось. Старые `/tmp/source_objects.py.{prod,dev}.before_atl_funnel_20260508_*` оставлены как L1 страховка от 8 мая.

---

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
