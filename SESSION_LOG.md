# SESSION_LOG — Последние сессии

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
