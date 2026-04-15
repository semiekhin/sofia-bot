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
- Модель: Groq `kimi-k2-instruct` (primary, переключено 09.04 с llama-4-scout), OpenAI `gpt-5.4-mini` (fallback)
- `max_tokens=400`, **без RAG** (скорость), без Analyzer
- Rule-based state extraction ДО LLM: goal, budget, payment_type, meeting_agreed
- VOICE_SYSTEM_PROMPT: компактный промпт со скриптом продаж и примерами
- `sanitize_for_tts()`: убирает латиницу, URL, email, @mentions

### Голосовой стек Asterisk (voice_asterisk.py)

**Архитектура (2 сервера):**

```
Клиент звонит +79310091644
    │
    ▼
Телфин SIP (sipproxy.telphin.ru:5068)
    │
    ▼
┌─────────────── VPS 185.207.66.201 (ssh sofia-voice) ───────────────┐
│ Asterisk 20 (PJSIP, порт 5090)                                     │
│    │                                                                 │
│    ▼ AudioSocket (TCP localhost:9090)                                │
│ voice_asterisk.py:                                                   │
│    ├─ VAD (energy-based, 0.4s silence threshold)                    │
│    ├─ Barge-in detection (5+ frames, cancel TTS)                    │
│    ├─ STT: Yandex SpeechKit REST v1 (~300ms) ──── напрямую         │
│    ├─ LLM: Groq kimi-k2 (~300ms) ───────────────── через proxy ──┐  │
│    └─ TTS: ElevenLabs Nastya streaming (~500ms) ── через proxy ─┤  │
└─────────────────────────────────────────────────────────────────┘  │
                                                                      │
┌─────────────── Основной сервер 72.56.64.91 ────────────────────────┤
│ nginx proxy :8095 (UFW: only 185.207.66.201)                       │
│    ├─ /groq/     → https://api.groq.com/                           │
│    ├─ /openai/   → https://api.openai.com/                         │
│    └─ /elevenlabs/ → https://api.elevenlabs.io/                    │
└────────────────────────────────────────────────────────────────────┘
```

**Архитектурное решение (08.04.2026):** Двухсерверная архитектура — **постоянная**, не временная. Телфин не меняет GeoIP настройки, задача переноса Asterisk на NL-сервер закрыта как невыполнимая. Proxy на 72.56.64.91 = production-компонент, не костыль. +20-30ms на API запрос — приемлемо.
- Телфин блокирует SIP по IP (403 Forbidden Ip) — VPS в белом списке
- Groq/OpenAI/ElevenLabs блокируют Россию — proxy через нидерландский сервер

**AudioSocket протокол (TCP):**
- Пакет: `[1 byte type][2 bytes length BE][payload]`
- UUID=0x01 (16 bytes binary), Audio=0x10 (slin 8kHz), Hangup=0x00, Error=0xFF
- Телфин отправляет INVITE на extension 's'

**Тайминги (конец речи → первый звук ответа, обновлено 09.04):**
- VAD silence: 300ms (снижено с 400ms, 09.04)
- STT (Yandex): ~300ms
- LLM (Groq kimi-k2 via proxy): ~300ms (было ~500ms с llama-4-scout)
- TTS first byte (ElevenLabs v3 via proxy): ~700-900ms (было ~300ms с Flash v2.5)
- **Итого: ~900-1100ms ощущаемая пауза** (было ~600-700ms с Flash, качество v3 значительно лучше)

**TTS streaming:** ElevenLabs `/stream` endpoint + `optimize_streaming_latency=4` → MP3 stream → ffmpeg pipe → 8kHz PCM → AudioSocket фреймы (320 bytes = 20ms)

**SIP данные Телфин:**
- Сервер: sipproxy.telphin.ru:5068
- Добавочный: 15400*101, пароль: jAJk6585e
- Кодеки: alaw, ulaw (G.711)
- Номер: +79310091644

**Файлы голосового стека:**
- `voice_asterisk.py` — AudioSocket сервер + VAD + STT/LLM/TTS pipeline
- `asterisk/pjsip.conf` — PJSIP trunk к Телфин
- `asterisk/extensions.conf` — dialplan (входящий → AudioSocket)
- `asterisk/logger.conf` — логирование Asterisk
- `/etc/nginx/sites-available/llm-proxy` — nginx proxy config
- VPS: `/opt/sofia-voice/` — рабочая директория, venv, .env, sofia_voice.db

**Деплой голосового стека:**
```bash
# Скопировать код на VPS
scp voice_asterisk.py sofia-voice:/opt/sofia-voice/
scp core/pipeline.py sofia-voice:/opt/sofia-voice/core/
# Перезапустить через systemd (НЕ nohup!)
ssh sofia-voice "systemctl restart sofia-voice"
# Проверить статус и логи
ssh sofia-voice "systemctl status sofia-voice"
ssh sofia-voice "journalctl -u sofia-voice -n 50 --no-pager"
```

**systemd unit (создан 10.04):** `/etc/systemd/system/sofia-voice.service` — Type=simple, Restart=on-failure, RestartSec=3, EnvironmentFile=/opt/sofia-voice/.env, LOGURU_COLORIZE=false. Автостарт при ребуте включён (enabled).

**VOICE_PROMPT_MODE (08.04):**
- env-переменная `VOICE_PROMPT_MODE`: `atlantis` (default) или `rizalta`
- Переключает greeting в `voice_asterisk.py` (`_send_greeting()`) и system prompt в `core/pipeline.py` (`stream_voice_response()`)
- На VPS `.env`: `VOICE_PROMPT_MODE=rizalta`
- `VOICE_SYSTEM_PROMPT` — Atlantis (входящая квалификация), НЕ ТРОГАТЬ
- `VOICE_SYSTEM_PROMPT_RIZALTA` — RIZALTA goal-oriented промпт (исходящий обзвон)

**ElevenLabs TTS (обновлено 10.04, v3 locked):**
- Nastya — Professional Voice Clone (PVC), voice_id=YjESejviApN7SHrbfnA2
- Модель: `eleven_v3` (переключено 10.04 после A/B теста v3 vs MLv2 vs Flash v2.5)
- v3 TTFB ~700-900ms (медленнее Flash, но значительно лучше просодия и ударения)
- v3 НЕ поддерживает optimize_streaming_latency
- v3 стоимость 1x кредит/символ (Flash = 0.5x)
- Настройки (09.04): stability=0.50, similarity_boost=0.85, speed=1.10
- SSML: `<break time="0.3s"/>` поддерживается (inline, без `<speak>` обёртки). Max 2 breaks на реплику
- Pronunciation dictionaries: alias-правила доступны, но требуют Scale план ($99/мес) — не используем
- Ударения: ~80% точность на русском (все модели ElevenLabs одинаково). Yandex SpeechKit лучше (99%), но нет voice cloning
- `add_ssml_breaks()` — функция в voice_asterisk.py, автоматически вставляет breaks между предложениями

**Стадии (RAG stages):** GREETING → ACTUALIZATION → QUALIFICATION → PRESENTATION → OBJECTION → MEETING → CLOSING

**core/bitrix.py** — Битрикс CRM:
- `SOFIA_AI_USER_ID = 428` — ответственный на время квалификации (робот-распределитель не трогает)
- `BITRIX_ASSIGNED_ID = 426` — fallback при restore
- `BITRIX_ATLANTIS_SOURCE_ID = "397"` — источник Тильда/Атлантис
- `BITRIX_SOURCE_ID = "504"` (env, default) — источник для новых лидов
- `create_or_update_lead()`: create → ASSIGNED_BY_ID=428; update → COMMENTS с диалогом; final → `restore_assigned()`
- `restore_assigned(db, lead_id)`: original из `lead_assigned` → fallback 426
- `find_recent_atlantis_lead()`: последний лид с SOURCE_ID=397
- Webhook (`/api/bitrix/webhook`): если ASSIGNED_BY_ID != 428 → менеджер перехватил → `manager_active=1`
- `is_manager_active()` / `set_manager_active()`: флаг перехвата, София молчит

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
| Radist Telegram @SofiaOazis | sofia_radist_gateway.py | -(offset + chat_id)* | Да, полный цикл (find_recent_atlantis_lead → finalize_lead → БП 152) | **Основной ATL-канал с 08.04**. Telegram Business Link https://t.me/m/QinKZEsTNmRi с prefilled "Здравствуйте, отправьте презентацию АК «Атлантис»" → detect_source("Атлантис") → source_object=atlantis → Bitrix full cycle. `process_with_queue()`, Observer, radist_leads таблица |
| Radist Max | sofia_radist_gateway.py | -(1000000 + chat_id) | Нет | Dormant с февраля 2026, 0 сообщений за 30 дней |
| Voice V1 (Retell) | voice_api.py | 7_000_000 + md5[:8] % 1M | Нет | WS адаптер, `is_responding` флаг, `clean_for_voice()` |
| Voice V2 (Pipecat) | voice_pipecat_daily.py | 8_000_000 + md5[:8] % 1M | Нет | SofiaPipelineProcessor → stream_voice_response(), `sanitize_for_tts()`, Yandex TTS |

*Radist offsets: Max = 1M, Telegram = 2M, WhatsApp = 3M (отрицательные)

### Конфиги

- `config/source_objects.py`: маппинг объектов. `atlantis`: keywords `[атлантис, atlantis, #ATL]`, context из `objects/atlantis_context.md`, `prompt_addon` = не запрашивать контакты
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

- **SOFIA_PATH баг (21.03):** dev писал в prod БД. Фикс: `SOFIA_PATH=/opt/sofia-gpt-dev` в .env
- **process_message сбрасывает dialog_finished:** строки 52-56. Async Extractor в voice вызывает extract_sync напрямую
- **hash() для ID:** непредсказуем между процессами. Фикс: autoincrement из БД (web_api) или md5 (voice)
- **reasoning модели + max_tokens:** gpt-5.2 с reasoning тратит токены на думание, max_output_tokens=4000 для текста, 800 для голоса
- **ElevenLabs блокер:** бесплатный план → HTTP 402, WS молча глотал. Pipecat таймауты: `AUDIO_CONTEXT_TIMEOUT` пропатчен до 15с в системном пакете — при обновлении повторить
- **Yandex STT ломает turn detection:** push_frame напрямую, user_aggregator не видит. Нужна интеграция
- **Yandex TTS REST v1 + латиница:** плохие ударения. Нужен gRPC v3 + unsafe_mode
- **user_aggregator пушит LLMContextFrame**, НЕ LLMRunFrame — SofiaPipelineProcessor ловит именно его
- **Retell двойной ответ:** два response_required подряд. Фикс: `is_responding` флаг
- **Observer portback (08.04 → 10.04):** при git recovery 08.04 коммит 49659ffb был сделан напрямую в PROD. Не попал в DEV. 2 дня мина лежала — любой деплой DEV→PROD молча удалил бы Observer. Нашли через аудит. Урок: прямые prod-коммиты = источник расхождения, требуют немедленного backport или явной фиксации в SESSION_LOG.
- **Аудит должен сверять git и диск (10.04):** первая версия аудита AUDIT_ATLANTIS заявила "prod и dev разошлись по bot_server.py, prod новее по Observer". При детальной проверке оказалось что коммит 49659ffb есть только в prod-git, в dev его вообще нет. Аудит смотрел только на файлы на диске. Урок: при сравнении веток проверять `git log --oneline`, `md5 git HEAD:file`, `md5 on-disk file` — все три показателя, и явно различать "расхождение в git" vs "расхождение между git и диском".
- **Claude Code и cwd при git-операциях (10.04):** при проверке коммита 49659ffb Claude Code дважды запустил `git log` с неправильным cwd (из /opt/sofia-gpt когда ожидался /opt/sofia-gpt-dev), получил ложный вывод "коммит есть в обеих ветках". Исправлено явным `cd` перед каждой git-командой. Урок: в multi-repo окружении всегда явный `cd /opt/sofia-gpt` или `cd /opt/sofia-gpt-dev` перед git-вызовами, не полагаться на текущую cwd.
- **logrotate-конфиг Asterisk сломан с 2022 (15.04):** glob-паттерны `messages`/`full`/`*_log` в `/etc/logrotate.d/asterisk` не матчили реальные файлы `messages.log`/`full.log`. logrotate каждую неделю молча проходил мимо. Файлы росли 4 года. Урок: при первой установке любого пакета — проверять что его logrotate-конфиг реально матчит файлы которые сервис создаёт. Простой способ: `logrotate --debug /etc/logrotate.d/<package>` — должен показать "considering log <file>" для каждого ожидаемого файла.
- **Длинные ответы оркестратора на простые вопросы (15.04):** на вопросы вида "есть ли N в твоём промпте" Claude.ai давал эссе с ходом рассуждений вместо списка из N пунктов. Урок зафиксирован в ORCHESTRATOR_RULES.md.
- **Отсутствие прохода "что забыл" перед отдачей контракта (15.04):** Claude.ai отдавал спринт-контракт с 10 пропусками, которые нашёл только ретроспективно после вопроса Сергея. Урок: обязательная финальная проверка контракта на полноту перед отдачей. Зафиксировано в ORCHESTRATOR_RULES.md.
- **--vacuum-size vs --vacuum-time для journalctl (15.04):** на disk-rescue `journalctl --vacuum-size=200M` снёс логи тихих сервисов целиком. Для тихих сервисов (sofia-voice пишет редко) `--vacuum-time=7d` предсказуемее.
- **Bitrix-фильтр TITLE LIKE для ATL даёт ложноотрицательный результат (15.04):** Sofia в ATL-flow обновляет существующий Tilda-лид (TITLE "Клиент #Планировки Атлантис"), а не создаёт свой "AI-бот: ...". Фильтр по TITLE никогда не найдёт ATL-клиентов. Правильный фильтр — `SOURCE_ID=397 + DATE_MODIFY`, кросс-проверка с `radist_leads`/`radist_messages`. Общее правило: вывод "пусто → значит нет" подозрителен и требует второй независимой проверки.
- **git cherry-pick не работает между отдельными git-репо (15.04):** PROD `/opt/sofia-gpt/.git` и DEV `/opt/sofia-gpt-dev/.git` — **разные репозитории**, не ветки одного. `git cherry-pick <sha>` в PROD падает с `fatal: bad revision` потому что SHA существует только в DEV-objects. Рабочий способ — `cd /opt/sofia-gpt-dev && git format-patch -1 <sha> --stdout | (cd /opt/sofia-gpt && git am --no-verify -)`. Альтернатива — `cd /opt/sofia-gpt && git fetch /opt/sofia-gpt-dev main && git cherry-pick FETCH_HEAD` (оставляет dangling objects до gc). Прецедент `3892c648 (cherry-pick 7f4c96a2)` в PROD сделан именно через format-patch+am, метка «cherry-pick» — лишь в commit message.
- **DEV→PROD деплой: учитывать файлы-потребители, не только целевые (15.04):** при деплое `config/source_objects.py` с расширенным `prompt_addon` в PROD выяснилось что PROD `core/pipeline.py` вообще **не читает** `prompt_addon` (нет ветки `if obj_config.get("prompt_addon")`), и в `source_objects.py` PROD этого ключа никогда не было. Atlantis-addon — DEV-only фича целиком, 400+ строк разницы в pipeline.py PROD vs DEV. Урок: в investigate_first обязательно сравнивать не только целевые файлы, но и файлы-потребители (pipeline.py когда трогаем config/*.py, bot_server.py когда трогаем core/bitrix.py). Иначе деплой превращается в «данные есть, код-потребителя нет → мёртвый текст в словаре».
- **Split-deploy как честное решение при разошедшихся DEV↔PROD (15.04):** когда деплой одного коммита обнаруживает что в PROD отсутствует инфраструктура, **не** делать слепой cp всей фичи из DEV. Правильно: применить **только** те файлы, где diff чистый и инфраструктура готова, остальное отложить в backlog как `ATLANTIS_ADDON_INFRA_PORTBACK`-подобный спринт с полной разведкой и планом порта. Сегодняшний `d60e9b0b` — прецедент: `sofia_prompt_v2.py` в PROD применён через `git show <sha> -- <file> | git apply --index -`, Atlantis-addon часть отложена.

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
| GROQ_API_KEY | + | — | Groq (kimi-k2 voice LLM) |
| DAILY_API_KEY | + | — | Daily WebRTC |
| WEB_API_PORT | 8081 | 8080 | Порт web API |

## Docs (справочники)

- `docs/SOFIA_CURRENT.md` — текущий статус, таблица сервисов, тайминги
- `docs/SOFIA_TASKS.md` — задачи и бэклог
- `docs/KNOWLEDGE_INDEX.md` — лог решений, уроки из ошибок, инструкции отката
- `docs/VOICE_RESEARCH_2026.md` — исследование голосового стека (50+ решений)
- `docs/STRESS_RESEARCH.md` — research ударений: ruaccent, U+0301, ElevenLabs (10.04)
- `docs/ELEVENLABS_V3_RESEARCH.md` — research v3 vs MLv2 vs Flash, API, PVC, pricing (10.04)
- `docs/AUDIT_ATLANTIS_2026-04-10.md` — полный аудит Атлантиса на 10.04: виджет, Telegram-бот + Тильда (ATL-flow), Radist (@SofiaOazis), Bitrix, контент, git-состояние, переход на @SofiaOazis
- `docs/ORCHESTRATOR_RULES.md` — правила работы Claude.ai как оркестратора (роль, стиль ответов, перед спринт-контрактами, доверие к Claude Code)
- `SESSION_LOG.md` — последние 10 сессий (компактно)
- `BACKLOG.md` — невыполненные задачи по приоритетам

## Workflow

- **Claude.ai** = архитектор (планирование, исследование)
- **Claude Code** = исполнитель (кодинг, деплой)
- Подтверждения: `python3`, `grep`, `curl`, `ps`, `ss`, `black`, `flake8`, `journalctl`, `systemctl`, `cat`, `ls`, `find` → авто-approve
- Перезапуск dev: `sudo systemctl restart sofia-web-api-dev`
- Health check: `curl -s http://localhost:8081/api/health`
- Линтер: `flake8 *.py --max-line-length=120 --exclude=__pycache__ && black *.py`

### Gitpull (скачать на локалку для Claude.ai)

```bash
# Один раз создать папки docs и memory если их нет
mkdir -p ~/projects_claude/Sofia/docs ~/projects_claude/Sofia/memory
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/BACKLOG.md ~/projects_claude/Sofia/
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/SESSION_LOG.md ~/projects_claude/Sofia/
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/CLAUDE.md ~/projects_claude/Sofia/
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/docs/ORCHESTRATOR_RULES.md ~/projects_claude/Sofia/docs/
scp -P 2222 root@72.56.64.91:/opt/sofia-gpt-dev/docs/SPRINT_TEMPLATE_v2.md ~/projects_claude/Sofia/docs/
scp -P 2222 root@72.56.64.91:/root/.claude/projects/-opt-sofia-gpt-dev/memory/project_prod_dev_drift.md ~/projects_claude/Sofia/memory/
scp -P 2222 root@72.56.64.91:/root/.claude/projects/-opt-sofia-gpt-dev/memory/user_sergey.md ~/projects_claude/Sofia/memory/
scp -P 2222 root@72.56.64.91:/root/.claude/projects/-opt-sofia-gpt-dev/memory/project_voice_sprint_next.md ~/projects_claude/Sofia/memory/
scp -P 2222 root@72.56.64.91:/root/.claude/projects/-opt-sofia-gpt-dev/memory/project_voice_vps.md ~/projects_claude/Sofia/memory/
```

### Session End (обязательно в конце каждой сессии)

1. Обновить **SESSION_LOG.md** — что сделано, коммиты, файлы, ключевые метрики
2. Обновить **BACKLOG.md** — новые задачи в P0, перенести завершённые в "Завершено"
3. При изменении правил оркестратора — обновить **`docs/ORCHESTRATOR_RULES.md`** (этот файл попадает в контекст Claude.ai через Gitpull, см. блок выше)
4. Обновить **memory** файлы Claude Code (`/root/.claude/projects/-opt-sofia-gpt-dev/memory/`):
   - `project_voice_sprint_next.md` — текущий контекст спринта, что делать дальше
   - `project_voice_vps.md` — VPS архитектура, proxy, SIP данные
   - `user_sergey.md` — профиль пользователя
   - `MEMORY.md` — индекс всех memory файлов
5. Закоммитить и запушить: `git add SESSION_LOG.md BACKLOG.md CLAUDE.md docs/ORCHESTRATOR_RULES.md docs/SPRINT_TEMPLATE_v2.md && git commit && git push`

```bash
# Скачать memory файлы (для Claude.ai контекста)
scp -P 2222 root@72.56.64.91:/root/.claude/projects/-opt-sofia-gpt-dev/memory/*.md ~/projects_claude/Sofia/memory/
```

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
