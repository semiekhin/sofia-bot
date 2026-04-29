# SOFIA-GPT — Контекст для Claude

## Проект

AI-менеджер по продажам курортной недвижимости для Oazis Estate. Общается с клиентами в 5 каналах (Telegram, Web-виджет, Radist Max/Telegram/WhatsApp) + голосовой канал (dev). Квалифицирует клиентов, отвечает на вопросы, предлагает созвон с экспертом, передаёт лиды в Битрикс CRM.

## Инфраструктура

- **Сервер:** 72.56.64.91:2222
- **PROD:** `/opt/sofia-gpt/` — **ЗАПРЕТНАЯ ЗОНА**, деплой только по явной команде
- **DEV:** `/opt/sofia-gpt-dev/` — рабочая директория
- **Бэкапы:** `/opt/sofia-gpt-backup-20260321_1355`, `/opt/sofia-gpt/backups/20260326_0724/` (НЕ УДАЛЯТЬ)

## Сервисы (systemd)

| Сервис | Среда | Порт | Что делает |
|--------|-------|------|-----------|
| sofia-gpt.service | PROD | — (long polling) | Telegram бот @humanAINeural_bot |
| sofia-web-api.service | PROD | 8080 | Web-виджет + Bitrix webhook |
| sofia-radist.service | PROD | 5001 | Radist gateway (Max/TG/WA) |
| sofia-web-api-dev.service | DEV | 8081 | Web-виджет dev + voice_api.py (Retell WS) |
| sofia-radist-dev.service | DEV | 5002 | Radist gateway dev |
| voice_pipecat_daily.py | DEV | 8083 | Pipecat + Daily WebRTC (ручной запуск) |

## Стек

Python 3.12, FastAPI, SQLite, OpenAI gpt-5.2 (Responses API), ChromaDB (RAG, text-embedding-3-small, 1965 примеров), Telegram Bot API, Radist.Online v2, Bitrix24 CRM, Pipecat 0.0.107, Daily WebRTC, ElevenLabs TTS, Yandex SpeechKit (TTS REST v1 + STT gRPC v3), Nginx

## Архитектура

### Единое ядро (core/)

**core/pipeline.py** — `run_pipeline()` и `stream_voice_response()`:

1. **Source routing:** если `state.source_object` и `user_msg_count <= 2` → принудительно `stage=GREETING`, Analyzer пропускается
2. **Analyzer** (gpt-5.2, `reasoning.effort=medium`): определяет `stage` + `rag_query` из JSON. Пропускается в `voice_mode`
3. **RAG** (ChromaDB): `search_examples(stage, query, limit=10)` → `format_examples_for_prompt()`
4. **Generator** (gpt-5.2, `reasoning.effort=high`, `max_output_tokens=4000`): system prompt + RAG примеры + история → ответ
5. **[END] check:** убирает маркер, ставит `dialog_finished=True, finish_type="llm_end"`
6. **Object context:** при `source_object` → инъекция карточки объекта + presentation_url в system prompt

**stream_voice_response()** — голосовой pipeline (используется в voice_asterisk.py и voice_api.py):
- Модель (с 16.04): **YandexGPT 5 Pro** (`yandexgpt/latest` через AI Studio OpenAI-compatible endpoint)
- Env переключатель `VOICE_PROVIDER`: `yandex` (default) / `groq` / `openai` — dead branches сохранены для rollback
- `max_tokens=400`, **без RAG** (скорость), без Analyzer
- Rule-based state extraction ДО LLM: goal, budget, payment_type, meeting_agreed
- VOICE_SYSTEM_PROMPT: компактный промпт со скриптом продаж и примерами
- Anti-hallucination regex post-filter в stream_voice_response() — обрезает на маркерах `Пользователь:`/`Клиент:`/`Ассистент:` (YandexGPT иногда генерирует продолжение диалога)
- `sanitize_for_tts()`: убирает латиницу, URL, email, @mentions

### Голосовой стек Asterisk (voice_asterisk.py)

Двухсерверная архитектура: **VPS sofia-voice `185.207.66.201`** (Asterisk 20 PJSIP 5090 + voice_asterisk.py + AudioSocket TCP 9090) ↔ **основной сервер `72.56.64.91`** (nginx proxy :8095 только для текстового OpenAI-трафика, не для голоса с 16.04).

Стек VPS: Silero VAD v4 ONNX (8kHz, 500ms silence) → Yandex STT v3 gRPC streaming (EOU=high, `YANDEX_MAX_PAUSE_HINT_MS=700`) → YandexGPT 5 Pro → Yandex TTS Alena v1 LPCM. Тайминги: ~1.0с от конца речи до первого звука ответа, greeting TTFB 0ms (cached PCM).

Ключевые env-переключатели: `VOICE_PROMPT_MODE=rizalta|atlantis`, `AUTO_HANGUP_ENABLED=true`, `STT_MODE=grpc|rest`, `YANDEX_STT_EOU_MODE=high`, `VOICE_VAD_PROVIDER=silero|energy` (energy = L1 rollback). UFW whitelist: 22/tcp + Telfin SIP 5090/udp (`46.229.221.93` + `213.170.84.105`) + RTP 10000-20000/udp.

Фичи 18.04: Phase 1 VLAT-07 (EOU median −742мс), auto-hangup после farewell/`[END]`, MixMonitor recording (WAV→Opus ротация >72h), dial.py realtime stream в терминал.

Pacing 20.04 (коммит `8f3eeaf0`): **`_speak_pcm=sleep(0.020)`**, **`_speak=sleep(0.019)`** (асимметрия под разный event loop overhead — 855us в активном `_speak` с gRPC+Silero vs 610us в тишине `_speak_pcm`). Target wall_per_chunk = 20ms = audio rate. До 20.04 было `sleep(0.018)` → AudioSocket buffer overflow → дроп фреймов → проглатывания слогов. После фикса: 0 dropouts, correlation greeting-source vs MixMonitor 0.987 (было 0.034). VPS апгрейд 1→2 vCPU 20.04 — аппаратно ok, но к проглатываниям не относился (см. SESSION_LOG 20.04).

Pilot-инфра 21.04 (коммиты `8ac8233f` `f28cd748` `f501d719` `37e099a5` `2304b075` `38c42abf` `75082b73`): **dial.py per-turn METRICS** (EOU/LLM/TTS-first-chunk, `[MM:SS]` таймеры, `Recording:` + scp one-liner в post-call), **`bin/listen_live.sh`** (live-прослушка через ssh-pipe+ffplay 8kHz s16le mono, `inotifywait` на сегодняшний recordings dir), **`bin/hangup_audiosocket.sh` + `ExecStop=`** в sofia-voice.service (targeted hangup каналов с `application=AudioSocket` перед SIGTERM → защита от root-cause 20.04 orphan), **dial.py channel_giveup** (требует 3 consecutive Up/Ringing polls — иначе escape через 30с при silent originate failure, фикс hang'а на invalid/unanswered номерах). Runbook: `docs/PILOT_WORKSTATION_RUNBOOK.md`.

Post-mortem 20.04 вечер: инцидент 14:56–15:53 UTC (Asterisk 193% CPU / load 27) — **root cause orphan AudioSocket channels** от 4 подряд `systemctl restart sofia-voice` во время активных звонков. Python TCP socket (port 9090) умирает, Asterisk PJSIP-канал остаётся с работающим `AudioSocket()` app → tight retry loop на dead socket. Safety net (`ExecStop=hangup_audiosocket.sh` + cron load_watchdog) draft'нут, деплой отложен до первых пилотных звонков 21.04. Secondary — kernel 6.8.0-110 PSI bug (D-state SSH сессии, P2).

🔴 **КРИТИЧЕСКОЕ ОПЕРАЦИОННОЕ ПРАВИЛО:** НЕ делать `systemctl restart sofia-voice` во время активных звонков — до деплоя safety net это единственная защита от orphan AudioSocket. Перед любым hot-patch: `ssh sofia-voice 'asterisk -rx "core show channels count"'`, убедиться `0 active channels`, только тогда restart. Planned deploy'и — в окно тишины между тестерами.

Открыто на 21.04 (carry-over P1, не блокер): «склейки внутри слов» на **cached greeting** (live TTS чистый после speed=1.2). Speed A/B (1.1→1.0→1.2) показал что 1.2 помогает live, но не cached → путь проблемы в static file readback / SSML break gaps / waveform phase при сохранении. Бесплатная диагностика: выключить cached-load на 1 звонок, MixMonitor diff live vs cached.

**Полный текст: [docs/VOICE_ARCHITECTURE.md](docs/VOICE_ARCHITECTURE.md)** (hot-reference) и **[docs/VOICE_TECH_STACK_FULL.md](docs/VOICE_TECH_STACK_FULL.md)** (исчерпывающий 49KB стек от SIP INVITE до клиента, 19 шагов, 25 параметров с `file:line`, diagnostic команды).

**Стадии (RAG stages):** GREETING → ACTUALIZATION → QUALIFICATION → PRESENTATION → OBJECTION → MEETING → CLOSING

**core/bitrix.py** — Битрикс CRM:
- `SOFIA_AI_USER_ID = 428` — ответственный на время квалификации (робот-распределитель не трогает)
- `BITRIX_BP_ASSIGNED_ID = 24932` — передача раздатчику перед запуском БП 152
- `BITRIX_ATLANTIS_SOURCE_ID = "397"` — источник Тильда/Атлантис
- `BITRIX_SOURCE_ID = "504"` (env, default) — источник для новых лидов
- `create_or_update_lead()`: create → ASSIGNED_BY_ID=428; update → COMMENTS с диалогом; final → `finalize_lead()`
- `finalize_lead(db, lead_id)`: **stage-guard 19.04** — сначала `get_lead_status(lead_id)`, если `!= "NEW"` → менеджер взял в работу, `set_manager_active(user_id, True)` + log `[FINALIZE_SKIP]` + return. Иначе `set_lead_assigned(24932)` + `start_distribution_bp()`.
- `get_lead_status(lead_id) -> str | None` — pull-проверка STATUS_ID через `crm.lead.get`. Fail-safe: None при любой ошибке API → caller трактует как не-NEW → skip финализации (тишина лучше перезаписи менеджера).
- `find_recent_atlantis_lead()`: последний лид с SOURCE_ID=397
- Webhook (`/api/bitrix/webhook`): если `ASSIGNED_BY_ID != 428` → `manager_active=1`. **Defense in depth**: подписка ONCRMLEADUPDATE у Bitrix пока не настроена (P2 backlog, Stetsenko), stage-guard — основной механизм защиты.
- `is_manager_active()` / `set_manager_active()`: флаг перехвата, София молчит во всех каналах.

Stage-guard также встроен в `sofia_radist_gateway.py`: `radist_send_reminder` (2 свежих вызова — перед отправкой + перед finalize после sleep) и `_radist_finalize_timeout`.

**RIZALTA Bitrix bypass (29.04, коммит `9947721d` DEV / `3be32d68` PROD).** Для `source_object=="rizalta"` Bitrix-интеграция отключена by design (менеджеры заносят лиды вручную). Двухуровневая защита:
- **Уровень 1** — `_is_radist_bitrix_session(user_id)` в `sofia_radist_gateway.py:391-408` возвращает `False` для rizalta → шортит все Bitrix-вызовы в обоих caller-блоках (`radist_callback` + `radist_finalize_timeout`). Skip пишется в лог как `🚫 [BITRIX_SKIP] source=rizalta function=<name>`.
- **Уровень 2** (defense-in-depth) — внутри `create_or_update_lead` в `core/bitrix.py:430-449`: если caller пропустил rizalta-сессию (баг рефакторинга / новый канал-потребитель), payload **подменяется** на `TITLE/NAME="Тестовый лид"`, `PHONE="89181011091"` через `title_override`-параметр в `create_lead`, дедупликация (`find_lead_by_phone`) пропускается. Громкий `🚨 [BITRIX_RIZALTA_LEAK]` ERROR-лог — видно в мониторинге, call-центр по тестовому номеру не звонит.

`bot_server.py` имеет свой `_is_bitrix_session()` без rizalta-фильтра — там работает только level-2 (P3 backlog: добавить level-1 если RIZALTA когда-нибудь придёт через @humanAINeural_bot).

### Обработка сообщения (message_processor.py)

`process_message()`: Extractor → State update → Signals. Вызывается ДО `run_pipeline()`.
- Сбрасывает `dialog_finished` если клиент написал снова
- `extract_sync()` — gpt-5.2, NLU: слоты (goal, location, budget, payment_type, lpr, strategy, usage, family), confidence (confirmed/mentioned/null), signals (friction, call_readiness, engagement, urgency), question_type, objection
- `merge_extraction_to_state()` — мёрж: confirmed перезаписывает, mentioned → `mentioned_*` поля

### Каналы

| Канал | Файл | User ID формула | Bitrix | Особенности |
|-------|------|-----------------|--------|-------------|
| Telegram бот @humanAINeural_bot | bot_server.py | telegram_user_id (положительный) | Только source-сессии (`_is_bitrix_session()`) | Legacy канал. До 08.04 был основным ATL-каналом через /start ATL. После 08.04 Тильда переключена на @SofiaOazis (Radist), новых ATL-клиентов через @humanAINeural_bot нет. Сервис крутится, решение о статусе (оставить как fallback / потушить) — открытый вопрос. |
| Web виджет | web_api.py | 9_000_000 + autoincrement | Да, каждое сообщение | UUID session_id → user_id, resume session, Observer |
| Radist Telegram @SofiaOazis | sofia_radist_gateway.py | -(offset + chat_id)* | Зависит от source_object: для **atlantis** — полный цикл (find_recent_atlantis_lead → finalize_lead → БП 152). Для **rizalta** — **Bitrix отключён by design** (двухуровневая защита, см. ниже) | **Основной ATL-канал с 08.04** + RIZALTA-канал с 29.04. Atlantis: Business Link https://t.me/m/QinKZEsTNmRi с prefilled "Здравствуйте, отправьте презентацию АК «Атлантис»" → detect_source → source_object=atlantis → Bitrix full cycle. RIZALTA: Business Link https://t.me/m/Ho-WF9DgNTgy с prefilled "Здравствуйте! Хочу подобрать номер в RIZALTA RESORT BELOKURIKHA" → detect_source → source_object=rizalta → Bitrix bypass + Observer-tag «· rizalta». `process_with_queue()`, Observer, radist_leads таблица |
| Radist Max | sofia_radist_gateway.py | -(1000000 + chat_id) | Нет | Dormant с февраля 2026, 0 сообщений за 30 дней |
| Voice V1 (Retell) | voice_api.py | 7_000_000 + md5[:8] % 1M | Нет | WS адаптер, `is_responding` флаг, `clean_for_voice()` |
| Voice V2 (Pipecat) | voice_pipecat_daily.py | 8_000_000 + md5[:8] % 1M | Нет | SofiaPipelineProcessor → stream_voice_response(), `sanitize_for_tts()`, Yandex TTS |

*Radist offsets: Max = 1M, Telegram = 2M, WhatsApp = 3M (отрицательные)

### Конфиги

- `config/source_objects.py`: маппинг объектов. `atlantis`: keywords `[атлантис, atlantis, #ATL]`, context из `objects/atlantis_context.md`, `prompt_addon` = не запрашивать контакты. `rizalta` (с 29.04, коммит `9947721d`): keywords `[ризалта, rizalta, rizalta resort]` (узкие — без `белокуриха` чтобы не false-match'нуть на упоминание города), context из `objects/rizalta_context.md`, без `prompt_addon` (механизм DEV-only). RIZALTA — **исключительно инвестиционный продукт**, личное проживание собственника не предусмотрено (см. карточку, обновлено `4d79a8ae`).
- `config/radist_config.py`: API ключи, connection_id → channel mapping (Max=80024, TG=80200), DEV_MODE, webhook port 5002/5001
- `yandex_tts.py`: REST v1, PCM 48kHz, чанки по 250 символов, голоса alena/marina
- `yandex_stt.py`: gRPC v3 streaming, protos в yandex_proto/, модель general:rc

## БД (SQLite: sofia_gpt_dev.db)

| Таблица | Ключевые поля |
|---------|---------------|
| client_state | user_id PK, goal, location, budget, payment_type, first_payment, lpr (все с *_confidence), meeting_agreed, call_refused, strategy, usage, family, dialog_finished, finish_type, source_object, manager_active, friction, call_readiness, engagement, urgency, lead_type, finance_interested, bitrix_lead_id |
| messages | chat_id, user_id, role, content, timestamp, stage |
| users | user_id PK, current_stage, messages_count |
| web_sessions | session_id PK, user_id, page_url, bitrix_lead_id, last_active |
| telegram_leads | user_id PK, bitrix_lead_id |
| lead_assigned | lead_id PK, original_assigned_by_id |
| radist_messages | channel, connection_id, chat_id, phone, role, content |
| radist_chats | channel, connection_id, chat_id, phone, user_name (UNIQUE channel+chat_id) |
| observer_topics | phone PK, thread_id, user_name |
| feedback_v2 | chat_id, user_id, rating, comment |
| rag_logs | chat_id, user_message, detected_stage, examples_used |

## Правила

- `/opt/sofia-gpt/` — PROD. НИКОГДА не трогать без явной команды
- Каждую задачу начинать с плана — план утверждает Сергей
- После задачи: `flake8 + black` → коммит
- Деплой в прод: только по явной команде "YES"
- User ID формулы критичны — коллизия = смешанные чаты

### Синхронизация prod ↔ dev

- Любой прямой коммит в PROD (при git recovery, экстренных фиксах, hot-patch) должен **немедленно** портироваться в DEV — либо тем же коммитом, либо явно зафиксирован в SESSION_LOG как "PROD ушёл вперёд по X, нужен backport в dev".
- Без этой фиксации расхождение становится миной: будущий обычный деплой DEV→PROD молча удалит PROD-фичу, никто не заметит.
- Исторический прецедент: коммит 49659ffb (08.04, Observer) был добавлен напрямую в PROD при git recovery, не портирован 2 дня, подсвечен аудитом 10.04, портирован коммитом 75b779a5.
- Периодически (раз в 1-2 недели или при подозрениях) делать git-sanity scan: сравнить md5 HEAD всех критичных файлов (core/, config/, *_server.py, *_gateway.py) между prod и dev. Расхождения — разбирать.

### Парадигмы каналов

- **Atlantis** = только текстовые каналы (Telegram/Web/Radist). Голоса для Atlantis НЕ существует
- **Голосовой канал** = отдельный продукт. Первый сценарий — исходящий обзвон по RIZALTA
- НЕ путать! Не нужно "переписывать промпт для Atlantis-голоса"

### Уроки из тестовых голосовых звонков (07.04)

- **LLM выдумывает телефоны** — "+7 123 456 78 90" → нужен жёсткий запрет в промпте + regex post-processing
- **Бессвязная склейка** — "В Сочи → в Туапсе" → нужна явная логика бюджет → допустимые локации
- **Мусор STT** — "Эротика", "Зависят облака" → нужен фильтр перед LLM (confidence / классификатор)
- **Длинные ответы** — 240 символов при лимите "1-2 предложения" → soft constraint не работает, нужен max_tokens=80 + "25 слов" в промпте
- **Стадии не соблюдаются** — звонок 3 пропустил оплату → нужен детерминированный `compute_next_required_question(state)` инжектируемый в промпт

### Структура V6 промпта (черновик)

1. Жёсткие запреты в начале (LLM видит при каждой генерации)
2. `{stage}` + `{state_summary}` + `{next_required_question}` блок
3. Явная логика бюджет → локация (исключающие диапазоны)
4. Defensive блок про мусор STT
5. Few-shot 6-8 примеров без противоречий со скриптом
6. Стилистические правила в конце

### Уроки из ошибок

~30 прецедентных уроков из сессий 21.03–18.04.2026 с датами, SHA коммитов, UUID звонков. Категории: prod/dev drift и git recovery, Silero VAD / AudioSocket chunking mismatch, barge-in pre-TTS race, fail2ban autostart / backend / jail.d приоритет, Yandex STT v3 gRPC teardown race, Groq model outage, AudioSocket UUID parsing, CDR CSV parsing, logrotate-конфиг Asterisk, Bitrix TITLE-фильтр vs SOURCE_ID, git cherry-pick между репо, Claude Code cwd в multi-repo, reasoning-модели + max_tokens, ElevenLabs блокер, user_aggregator Pipecat.

**Полный текст: [docs/LESSONS_LEARNED.md](docs/LESSONS_LEARNED.md)** — все уроки дословно с техническими деталями, командами rollback, прецедентами.

## .env ключи

| Ключ | Dev | Prod | Назначение |
|------|-----|------|-----------|
| OPENAI_API_KEY | + | + | OpenAI API |
| TELEGRAM_BOT_TOKEN | + | + | Telegram Bot API (разные боты!) |
| ADMIN_CHAT_ID | + | + | Telegram admin |
| MODEL_MODE | gpt-5.2 | gpt-5.2 | Модель генератора |
| DB_PATH | sofia_gpt_dev.db | sofia_gpt.db | Путь к SQLite |
| SOFIA_PATH | /opt/sofia-gpt-dev | /opt/sofia-gpt | Корень проекта |
| OBSERVER_CHAT_ID | закомментирован | + | Telegram группа Observer |
| RADIST_DEV_MODE | true | false | Radist не отправляет ответы |
| ELEVENLABS_API_KEY | + (Starter) | — | ElevenLabs TTS |
| YANDEX_SPEECHKIT_API_KEY | + | — | Yandex STT/TTS |
| GROQ_API_KEY | + | — | Groq (legacy — голос на Yandex с 16.04, dead branch) |
| YANDEX_MAX_PAUSE_HINT_MS | — | — | **700** на voice VPS (Phase 1 VLAT-07, 18.04). 0 = rollback к Yandex default. |
| AUTO_HANGUP_ENABLED | — | — | **true** на voice VPS (18.04). false = rollback, клиент кладёт сам. Gate: только при VOICE_PROMPT_MODE=rizalta. |
| YANDEX_STT_EOU_MODE | — | — | **high** на voice VPS (Phase 2D, 17.04). default = conservative ~2240ms wait. |
| STT_MODE | — | — | **grpc** на voice VPS (Phase 2B, 17.04). rest = REST v1 fallback. |
| STREAM_TRANSCRIPT | — | — | **true** default в dial.py (18.04). false = без realtime stream в терминале. |
| RIZALTA_OBSERVER_ENABLED | — | **false** | **false** на момент PROD-деплоя 29.04 (приватные тесты Сергея). При false — для rizalta-сессий `notify_observer` пропускает с логом `🚫 [OBSERVER_SKIP]`. Включить обратно: `sed -i 's/false/true/' /opt/sofia-gpt/.env && systemctl restart sofia-radist`. |
| DAILY_API_KEY | + | — | Daily WebRTC |
| WEB_API_PORT | 8081 | 8080 | Порт web API |

## Docs (справочники)

- `docs/VOICE_ARCHITECTURE.md` — **hot-reference архитектуры голосового стека** (вынесено из CLAUDE.md 19.04): AudioSocket, Silero VAD v4, Yandex STT gRPC, Phase 1 VLAT-07, auto-hangup, MixMonitor, VOICE_PROMPT_MODE, Pacing fix 20.04
- `docs/VOICE_TECH_STACK_FULL.md` — **исчерпывающий технический стек** (создан 20.04, 49KB): пошаговый путь байта от SIP INVITE до звука клиента, 10 разделов, 19 шагов, 25 параметров с `file:line`, таблица 27 файлов, 2 приложения (навигация по коду + diagnostic команды)
- `docs/LESSONS_LEARNED.md` — **прецедентные уроки 21.03–18.04** (вынесено из CLAUDE.md 19.04): ~30 уроков с SHA, UUID, командами rollback
- `docs/SOFIA_CURRENT.md` — текущий статус, таблица сервисов, тайминги
- `docs/SOFIA_TASKS.md` — задачи и бэклог
- `docs/KNOWLEDGE_INDEX.md` — лог решений, уроки из ошибок, инструкции отката
- `docs/VOICE_RESEARCH_2026.md` — исследование голосового стека (50+ решений)
- `docs/STRESS_RESEARCH.md` — research ударений: ruaccent, U+0301, ElevenLabs (10.04)
- `docs/ELEVENLABS_V3_RESEARCH.md` — research v3 vs MLv2 vs Flash, API, PVC, pricing (10.04)
- `docs/AUDIT_ATLANTIS_2026-04-10.md` — полный аудит Атлантиса на 10.04: виджет, Telegram-бот + Тильда (ATL-flow), Radist (@SofiaOazis), Bitrix, контент, git-состояние, переход на @SofiaOazis
- `docs/ATLANTIS_WIDGETS_STATE.md` — **справочник по двум путям привлечения на Атлантисе** (создан 28.04): форма «Получить презентацию» (Тильда → SOURCE_ID=397) и HTML-виджет «Чат с менеджером» (`widgets/atlantis_chat_widget.html` → дефолтный SOURCE_ID=504). Зафиксирована известная коллизия 60-сек окна `find_recent_atlantis_lead`. Baseline для масштабирования на новые сайты.
- `docs/ORCHESTRATOR_RULES.md` — правила работы Claude.ai как оркестратора (роль, стиль ответов, перед спринт-контрактами, доверие к Claude Code)
- `docs/PILOT_WORKSTATION_RUNBOOK.md` — **операторский runbook пилота холодного обзвона** (создан 21.04): 3 терминала (T1 listen_live Mac / T2 dial.py main-server / T3 scp download), состояние инфры, 6 известных особенностей (orphan AudioSocket+ExecStop, briefly-existing channels H1 fix, два UUID Asterisk, V1 concurrent assumption)
- `SESSION_LOG.md` — последние 10 сессий (компактно)
- `BACKLOG.md` — невыполненные задачи по приоритетам

## Workflow

- **Claude.ai** = архитектор (планирование, исследование)
- **Claude Code** = исполнитель (кодинг, деплой)
- Подтверждения: `python3`, `grep`, `curl`, `ps`, `ss`, `black`, `flake8`, `journalctl`, `systemctl`, `cat`, `ls`, `find` → авто-approve
- Перезапуск dev: `sudo systemctl restart sofia-web-api-dev`
- Health check: `curl -s http://localhost:8081/api/health`
- Линтер: `flake8 *.py --max-line-length=120 --exclude=__pycache__ && black *.py`

### Рабочая станция пилота (three-terminal workflow)

Пилот холодного обзвона RIZALTA: три терминала — два на Mac Сергея, один на main-server.

**T1 (Mac) — live-прослушка разговора** (держится открытым весь день пилота, `while`-loop переключается между звонками автоматически):

```bash
while true; do
  ssh sofia-voice '/opt/sofia-voice/bin/listen_live.sh' 2>/dev/null | \
      ffplay -nodisp -autoexit -f s16le -ar 8000 -ch_layout mono -
done
```

Задержка 2-5с. Скрипт exit'ит после 20с idle файла — ffplay закрывается по EOF, `while` стартует прослушку следующего звонка.

**T2 (main-server через `ssh sofia-dev`) — исходящий звонок**:

```bash
ssh sofia-voice 'python3 /opt/sofia-voice/dial.py +7XXXXXXXXXX'
```

В терминале realtime: `[MM:SS] USER/SOFIA/METRICS (eou/llm/tts)` + `[HH:MM:SS] Ringing/Answered/Ended`. После hangup — post-call summary с `Recording:` путём и `Download (run from your Mac): scp ...` one-liner'ом.

**T3 (Mac) — скачать запись** (опционально, когда нужен аудит конкретного звонка): копипаст `scp`-команды из post-call summary T2.

```bash
scp sofia-voice:/var/lib/asterisk/recordings/YYYY-MM-DD/<CALL_UUID>.wav ~/Desktop/
```

**Рестарт sofia-voice во время звонка — безопасно технически** (ExecStop=hangup_audiosocket.sh делает targeted hangup AudioSocket-каналов, orphan не остаётся). Дисциплинарное правило «не рестартовать зря в середине живого разговора» остаётся — клиент услышит обрыв.

### Gitpull (скачать на локалку для Claude.ai)

```bash
# Один раз создать папки docs и memory если их нет
mkdir -p ~/projects_claude/Sofia/docs ~/projects_claude/Sofia/memory
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/BACKLOG.md ~/projects_claude/Sofia/
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/SESSION_LOG.md ~/projects_claude/Sofia/
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/CLAUDE.md ~/projects_claude/Sofia/
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/docs/ORCHESTRATOR_RULES.md ~/projects_claude/Sofia/docs/
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/docs/SPRINT_TEMPLATE_v2.md ~/projects_claude/Sofia/docs/
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/docs/VOICE_ARCHITECTURE.md ~/projects_claude/Sofia/docs/
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/docs/VOICE_TECH_STACK_FULL.md ~/projects_claude/Sofia/docs/
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/docs/LESSONS_LEARNED.md ~/projects_claude/Sofia/docs/
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/docs/PILOT_WORKSTATION_RUNBOOK.md ~/projects_claude/Sofia/docs/
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/docs/ATLANTIS_WIDGETS_STATE.md ~/projects_claude/Sofia/docs/
scp -P 2222 root@72.56.64.91:/root/.claude/projects/-opt-sofia-gpt-dev/memory/project_prod_dev_drift.md ~/projects_claude/Sofia/memory/
scp -P 2222 root@72.56.64.91:/root/.claude/projects/-opt-sofia-gpt-dev/memory/user_sergey.md ~/projects_claude/Sofia/memory/
scp -P 2222 root@72.56.64.91:/root/.claude/projects/-opt-sofia-gpt-dev/memory/project_voice_sprint_next.md ~/projects_claude/Sofia/memory/
scp -P 2222 root@72.56.64.91:/root/.claude/projects/-opt-sofia-gpt-dev/memory/project_voice_vps.md ~/projects_claude/Sofia/memory/
scp -P 2222 root@72.56.64.91:/root/.claude/projects/-opt-sofia-gpt-dev/memory/project_rizalta_text_channel.md ~/projects_claude/Sofia/memory/
```

### Session End (обязательно в конце каждой сессии)

**Обязательно обновить:**
1. **SESSION_LOG.md** — добавить новую запись о сессии (TL;DR, коммиты, ключевые решения)
2. **BACKLOG.md** — закрытые задачи переместить в секцию "Завершено (<дата>)", добавить новые carry-over в P0-P3
3. **MEMORY.md** — обновить next-session starter (что было главное в этой сессии, точка входа для следующей)

**Обновить если менялось по теме сессии:**
4. **CLAUDE.md** — если менялись каналы / архитектура / env / БД / интеграции
5. **docs/ORCHESTRATOR_RULES.md** — если появились новые правила оркестрации (стоп-поинты, паттерны принятия решений)
6. **memory/user_sergey.md** — если появились новые наблюдения о паттернах работы Сергея
7. **memory/project_prod_dev_drift.md** — если был деплой с расхождениями между DEV и PROD
8. **memory/project_voice_sprint_next.md** + **memory/project_voice_vps.md** — если работали над голосом
9. **memory/project_rizalta_text_channel.md** + **docs/ATLANTIS_WIDGETS_STATE.md** — если работали над текстовыми каналами / виджетами

**Правило ротации (проверить и применить):**
10. Если SESSION_LOG.md содержит более 5 заголовков `## ДД.ММ.ГГГГ` — самые старые сессии (всё что после 5-й сверху) перенести в SESSION_LOG_ARCHIVE.md
11. Если в BACKLOG.md есть свежесозданная секция `## Завершено (<дата>)` — её сразу переносить в BACKLOG_ARCHIVE.md (в активном остаются только P0/P1/P2/P3)

**Закоммитить и запушить:**
```bash
cd /opt/sofia-gpt-dev
git add -u                                    # все изменения в отслеживаемых файлах
git add <список-новых-файлов-если-есть>       # явно перечислить новые если создавались
git status                                    # проверить что в индексе только нужное
git commit -m "session-end <дата>: <короткое описание>"
git push
```

После пуша — Сергей делает обычный `scp` своими 15 строками на Mac.

## Промпты для Claude Code

Каждый промпт для Claude Code должен заканчиваться блоком:

```
Задача готова когда:
1. [проверяемое условие]
2. [проверяемое условие]
...
```

Правила формулировки:
- Каждый критерий проверяемый: "при X происходит Y", не "работает правильно"
- 3–6 критериев на задачу, не больше
- Включать: happy path, основной edge case, логирование если релевантно
- Не включать: очевидное (код запускается, нет синтаксических ошибок)
