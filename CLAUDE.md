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
│    ├─ VAD: Silero VAD v4 ONNX (0.5s silence threshold, 17.04)       │
│    ├─ Barge-in: 10-frame confirm Silero / 5-frame energy            │
│    ├─ Cooldown 500ms + sliding-silence reset 300ms                  │
│    ├─ _tts_playing флаг (barge-in только при active TTS)            │
│    ├─ STT: Yandex SpeechKit REST v1 (~290ms) ──── напрямую          │
│    ├─ LLM: YandexGPT 5 Pro (~620ms) ─────────────── напрямую        │
│    └─ TTS: Yandex SpeechKit Alena v1 LPCM (~155ms) напрямую         │
└─────────────────────────────────────────────────────────────────────┘
                  ▲
          UFW firewall (17.04):
          22/tcp + 46.229.221.93:5090/udp + 10000-20000/udp
          default deny incoming — SIP-сканеры отрезаны на SYN

┌─────────────── Основной сервер 72.56.64.91 ────────────────────────┐
│ nginx proxy :8095 (UFW: only 185.207.66.201) — только для ТЕКСТА   │
│    ├─ /openai/   → https://api.openai.com/  (text: gpt-5.2)        │
│    └─ (legacy: /groq/, /elevenlabs/ — мёртвые ветки голоса)        │
└────────────────────────────────────────────────────────────────────┘
```

**Архитектурное решение (16.04.2026):** После миграции голосового стека на Yandex Cloud (все API доступны из России напрямую) — proxy на 72.56.64.91 **больше не участвует в голосовом пути**. Остаётся для текстового стека (OpenAI gpt-5.2). Двухсерверная архитектура сохраняется: Телфин блокирует SIP по IP (403 Forbidden Ip) — VPS в белом списке.

**AudioSocket протокол (TCP):**
- Пакет: `[1 byte type][2 bytes length BE][payload]`
- UUID=0x01 (16 bytes binary), Audio=0x10 (slin 8kHz, 320 bytes/20ms), Hangup=0x00, Error=0xFF
- Телфин отправляет INVITE на extension 's'

**Тайминги (конец речи → первый звук ответа, обновлено 17.04):**
- VAD silence: 500ms (поднято с 300ms на звонке e177d7ad — резало фразы на микропаузах)
- STT (Yandex REST v1): ~290ms
- LLM (YandexGPT 5 Pro напрямую): ~620ms медиана
- TTS first byte (Yandex Alena v1 LPCM напрямую): ~155ms
- **Итого: ~1.0с ощущаемая пауза** (чуть выше чем 860ms после 16.04 из-за более длинного silence threshold — цена за целые фразы)
- Greeting TTFB: **0ms** (cached PCM), 1ms до первого фрейма

**Silero VAD v4 (17.04):**
- Модель: `/opt/sofia-voice/silero_vad.onnx`, 1.8MB, md5 `03da8de2fec4108a089b39f1b4abefef`
- Singleton ONNX session (eager-load в `main()`, лог «Silero VAD loaded: ... (v4, 8kHz, md5=...)»)
- Per-call `SileroVAD` instance: `_h`, `_c` LSTM states `[2, 1, 64]`, buffer до 512B chunks (256 samples @ 8kHz = 32ms)
- Threshold 0.5 одинаково для normal VAD и barge-in (было 0.6 для barge-in — не пробивалось)
- Inputs: `input` float32 [1, N], `sr` int64 scalar, `h`/`c` state tensors
- **v5 не подошла для 8kHz** (13% detection на чистой речи, оптимизирована под 16kHz). v5 сохранена как `silero_vad_v5.onnx.legacy`
- Python deps: `onnxruntime 1.24.4`, `numpy 2.4.4` (numpy подтянулся с onnxruntime)

**Barge-in логика (17.04, итоговая):**
- Константы: `BARGE_IN_COOLDOWN=0.5` (отбрасывание VAD-фреймов после TTS cancel против echo cascade), `MIN_SPEECH_BYTES_FOR_STT=10240` (0.64с), `BARGE_IN_SILENCE_RESET=0.3`
- Флаги: `_is_responding` (весь STT→LLM→TTS) vs `_tts_playing` (только реальное TTS output). Barge-in detection **только** при `_tts_playing=True` — иначе pre-TTS race (клиент договаривает свою реплику в фазе LLM → cancel_playback=True до первого chunk → 0s played)
- Confirm frames: 10 для Silero (~200ms sustained speech с учётом chunking), 5 для energy (100ms, 1:1 frame→RMS). Bifurcate через `confirm_frames = 10 if self._vad is not None else 5` — energy-ветка сохраняет rollback fidelity для `VOICE_VAD_PROVIDER=energy`
- Sliding-silence reset: `_last_barge_in_speech_ts` отслеживает последний is_speech=True; buffer clear только после 300ms sustained silence (защита от Silero chunking альтернации True/False)
- После cancel TTS `_process_turn` finally **очищает** barge-in buffer (без re-feed в VAD — иначе cascade на polluted fragment >MIN_BYTES)
- Dispatch `_handle_packet`:
  ```
  if not _is_responding:  → _process_audio_vad (normal turn)
  elif _tts_playing:      → _detect_barge_in
  else:                   → ignore (STT/LLM фаза, клиент договаривает свою реплику)
  ```

**UFW firewall (17.04):**
- Whitelist: 22/tcp (SSH), 46.229.221.93:5090/udp (Telfin SIP /32), 10000-20000/udp (RTP media)
- Default deny incoming / allow outgoing
- Закрыты наружу: UDP 5060 (chan_sip legacy), UDP 4569 (IAX2) — только сканеры ими пользовались
- Эффект: рост `/var/log/asterisk/full.log` **44 KB/s → 0 B/s** (SIP-сканеры блокируются на SYN, Asterisk их не видит)
- fail2ban: P1 backlog, не развёрнут (UFW даёт 100%). Контракт для fail2ban готов

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
- `VOICE_SYSTEM_PROMPT_RIZALTA` — RIZALTA v3 (16.04): без представления, двухчастный каноничный питч, логика мессенджеров (Ватсап/Макс = номер уже знаем, Телеграм = уточняем ник), вход 15 млн, Совкомбанк/Сбер ипотека, запрет «скину пакет»

**Yandex TTS Alena (текущий провайдер с 16.04):**
- Голос: `alena`, формат `lpcm` 8kHz 16-bit mono (готовый для AudioSocket, без ffmpeg)
- Модель: Yandex SpeechKit v1 REST, endpoint `tts.api.cloud.yandex.net/speech/v1/tts:synthesize`
- TTFB ~150-185ms медиана (single REST POST, весь PCM одним ответом)
- Настройки: emotion=neutral, speed=1.1
- SSML: `<break time="300ms"/>` (Yandex требует integer ms, не дробные секунды как 0.3s)
- Cached greetings (0ms TTFB): `greeting_rizalta.pcm` (198318 bytes, 12.4s аудио, регенерирован 16.04 под RIZALTA v3), `greeting_atlantis.pcm`
- Регенерация cached PCM: inline Python через `synthesize_tts_yandex()` → запись файла
- Ударения: ~99% на русском (лучше ElevenLabs), voice cloning отсутствует
- `add_ssml_breaks()` — функция в voice_asterisk.py, автоматически вставляет breaks между предложениями
- Env VPS: `YC_API_KEY`, `YC_FOLDER_ID`, `YANDEX_TTS_VOICE=alena`, `YANDEX_TTS_EMOTION=neutral`, `YANDEX_TTS_SPEED=1.1`, `VOICE_TTS_PROVIDER=yandex`

**ElevenLabs legacy (dead branch, rollback-only):**
- Переключается через `VOICE_TTS_PROVIDER=elevenlabs` в .env
- Nastya PVC, voice_id=YjESejviApN7SHrbfnA2, модель `eleven_v3`, через proxy 72.56.64.91:8095 → ffmpeg MP3→PCM
- Код сохранён для экстренного rollback

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
- **Groq может убрать модель без предупреждения (16.04):** `moonshotai/kimi-k2-instruct` полностью исчезла из Groq `/v1/models` между 10-16.04. Все 5 звонков 16.04 получили 404, голос мёртв. Урок: (1) мониторить доступность модели периодически (curl models endpoint), (2) fallback-модель должна РЕАЛЬНО работать (OpenAI fallback без proxy = pre-existing мёртвый код), (3) не полагаться на одну модель одного провайдера для production без запасного пути.
- **Barge-in buffer re-feed пропустил echo через MIN_BYTES порог (16.04):** на звонке UUID 21b96626 после cancel TTS `_process_turn` finally переместил 13120-байтовый barge-in buffer (0.82с) в `_speech_buffer` и скормил VAD после cooldown. Буфер оказался **чуть выше** порога `MIN_SPEECH_BYTES_FOR_STT=10240` → прошёл фильтр → STT получил смесь echo+обрывка речи → вернул garbled «Со стороны» → LLM интерпретировал как невнятное и выдал фолбэк «плохо слышно» из блока «Не расслышала» RIZALTA-промпта. Правильный фикс: **не re-feed'ить** barge-in buffer в VAD, просто очищать после cooldown и ждать свежую речь клиента. Урок: MIN_BYTES порог — только первая линия защиты; любой источник «накопленного накануне» буфера (barge-in, начало захвата до cooldown) может протечь выше порога. Второй слой защиты должен быть в местах, откуда поступают эти источники.
- **Silero VAD v5 vs v4 на 8kHz (17.04):** v5 (2.3MB, latest release на apr 2026) даёт ~13% speech detection на чистой русской речи 8kHz lpcm (проверено на `greeting_rizalta.pcm`). v4 (1.8MB, md5 `03da8de2fec4108a089b39f1b4abefef`) на тех же данных даёт 73% (86% на speech+noise). Причина: v5 тренирована преимущественно на 16kHz, деградация на 8kHz — документированная проблема в GitHub issues репо. Вывод: **для телефонии 8kHz — v4 mandatory**. v5 сохранена как `silero_vad_v5.onnx.legacy` для re-test когда upstream улучшит 8kHz support.
- **AudioSocket / Silero chunking mismatch (17.04):** AudioSocket шлёт 320-byte фреймы (20мс @ 8kHz), Silero требует 512-byte chunks (32мс = 256 samples @ 8kHz). Внутренний буфер `SileroVAD.is_speech()` копит фреймы до 512B chunks и обрабатывает. Результат: **`is_speech()` альтернирует True/False** на каждом AudioSocket-фрейме даже при непрерывной речи (обрабатывается каждый ~1.6-й фрейм). Любая логика «5 consecutive speech frames» на булевом выходе ломается — counter сбрасывается при любом False. Симптом: `BARGE-IN confirmed = 0` за весь звонок (bcf67956, 17.04). Фикс: **sliding-silence pattern** — track `_last_barge_in_speech_ts`, clear buffer только после 300ms sustained silence. Урок: любой VAD с внутренней буферизацией под чанк не 1:1 с входным фреймом требует временно́го окна, а не consecutive-counter.
- **Pre-TTS race (17.04):** `_is_responding=True` устанавливался в начале `_process_turn` (ещё до STT). `_detect_barge_in` вызывался всё это время. Клиент договаривал свою же реплику после VAD endpoint → Silero детектил → BARGE-IN confirmed → `_cancel_playback=True` **до того** как TTS начал играть → первый `_send_audio` видел cancel → break → `total=first_chunk_time` (0s audio). Звонок 89dadd55: Sofia сгенерировала корректный ответ 2 раза, клиент услышал тишину. Фикс: отдельный флаг `_tts_playing` (True только между первой реально отправленной frame и завершением TTS). Barge-in detection только при `_tts_playing=True`. Во время STT/LLM фреймы клиента **игнорируются**. Урок: `_is_responding` (широкая фаза pipeline) ≠ `_tts_playing` (узкая фаза активного output) — разные флаги для разных целей.
- **Energy-ветка = L1 rollback, не просто dead branch (17.04):** дважды в одной сессии Сергей настоял на bifurcate по `self._vad is not None` для sliding-silence (коммит 97934f47) и для confirm_frames (коммит 95b4eeae) — чтобы поведение при `VOICE_VAD_PROVIDER=energy` осталось дословно тем же как было. Мотивация: energy — это rollback на случай внезапной проблемы с Silero (одной env-переменной). Если «по пути» менять семантику energy-ветки — через месяц при срочном rollback получим сюрприз. Паттерн: всегда `if self._vad is not None: <new>  else: <original>` с комментарием `kept for rollback fidelity`.
- **VAD_SILENCE 300ms резал фразы на микропаузах (17.04):** клиент говорит «Скажите примерно минимальную цену **и** [срок]» — Silero endpoint сработал на паузе между «и» и «срок» (300ms silence). STT вернул оборванную фразу, Sofia ответила только на «цену», клиент пытался продолжить → deadlock (UUID e177d7ad). Фикс: поднять `VAD_SILENCE_THRESHOLD` до 0.5s. Параллельно поднят barge-in confirm с 5 до 10 frames (было 100ms, стало 200ms) — одиночный «ээ»/вдох больше не убивает TTS. Временная заплатка до Yandex STT v3 gRPC streaming (server-side EOU определяет конец фразы, убирает silence threshold целиком).
- **Late-night session через полночь UTC/MSK (17.04):** одна непрерывная рабочая сессия может начаться 16.04 вечером и продолжиться после полуночи как 17.04 утром. Git log timestamps показывают реальную последовательность. Не полагаться на mental-date, проверять `git log --since`. Коммит `5104a0cc` сделан 23:07 MSK 16.04 — в SESSION_LOG зафиксирован как «утренний fix 17.04» поскольку является первым действием сессии.
- **Split-deploy как честное решение при разошедшихся DEV↔PROD (15.04):** когда деплой одного коммита обнаруживает что в PROD отсутствует инфраструктура, **не** делать слепой cp всей фичи из DEV. Правильно: применить **только** те файлы, где diff чистый и инфраструктура готова, остальное отложить в backlog как `ATLANTIS_ADDON_INFRA_PORTBACK`-подобный спринт с полной разведкой и планом порта. Сегодняшний `d60e9b0b` — прецедент: `sofia_prompt_v2.py` в PROD применён через `git show <sha> -- <file> | git apply --index -`, Atlantis-addon часть отложена.
- **fail2ban autostart после apt install (18.04):** пакетный установщик на Ubuntu 24.04 сразу запускает fail2ban с дефолтным `banaction=nftables` из `/etc/fail2ban/jail.d/defaults-debian.conf`. При правке banaction в `jail.local` нужен `systemctl restart fail2ban`, **НЕ** `reload` — reload не перевыполняет actionban, остаются phantom in-memory баны без реальных правил firewall (fail2ban думает что IP забанены, но в UFW/nftables их нет). После restart состояние восстанавливается из persistence DB корректно и баны переносятся в новый banaction. Урок: при первой настройке fail2ban или смене banaction — всегда restart.
- **fail2ban jail.d vs jail.local приоритет (18.04):** порядок загрузки конфигов — `jail.conf` → `jail.d/*.conf` → `jail.local` → `jail.d/*.local`, побеждает последний. Наш `jail.local` на VPS sofia-voice корректно перекрывает `defaults-debian.conf` по `banaction` (nftables → ufw). Но если в будущем кто-то положит новый `*.local` файл в `jail.d/` — он побьёт наш `jail.local`. При ревью изменений fail2ban-конфига всегда смотреть **всю** `jail.d/` тоже, не только `jail.local`. Проверка фактической конфигурации: `fail2ban-client -d | grep -iE "<jail>.*action"` показывает итоговые actionban-команды.
- **fail2ban backend для Asterisk (18.04):** Asterisk 20 на Ubuntu 24.04 из пакета Debian/Ubuntu **не пишет** в systemd journal (`journalctl -u asterisk` → `No entries`), только в `/var/log/asterisk/{messages,full}.log`. Глобальный дефолт `backend=systemd` из `defaults-debian.conf` при этом применяется ко всем jail без явного override — asterisk-jail читал бы пустой journal и фильтр никогда бы не сматчил. Фикс: явный `backend = auto` в `[asterisk]` секции (или `backend = polling`) — тогда jail использует `logpath=/var/log/asterisk/messages.log` и реально работает. Общее правило: при задании нового jail всегда явно указывать backend, не полагаться на глобальный дефолт из дистрибутивных `jail.d/*.conf`.

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
