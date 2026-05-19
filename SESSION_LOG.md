# SESSION_LOG — Последние сессии

> 📁 **Архив старых сессий:** [SESSION_LOG_ARCHIVE.md](SESSION_LOG_ARCHIVE.md). Если нужен контекст по старым сессиям — читать оттуда.

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

