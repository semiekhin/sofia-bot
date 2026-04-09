# BACKLOG — Невыполненные задачи

## P0 — Срочно

- [ ] **Ударения ElevenLabs** — Flash v2.5 ~80% точность на русском. Варианты: (a) pronunciation dictionary (нужен Scale план $99/мес), (b) предобработка текста через RUAccent/silero-stress, (c) Yandex SpeechKit gRPC v3 как TTS (99% ударений, но нет voice cloning)
- [ ] **Паузы между фразами** — `add_ssml_breaks()` работает, но `<break>` в больших количествах вызывает артефакты. Нужен тюнинг: оптимальное время паузы, максимум breaks, может ли быть лучше через post-processing аудио
- [ ] **B1: Filler звуки** — записать через ElevenLabs Nastya: "Угу...", "Так...", "Секундочку...". Кешировать как PCM, проигрывать сразу после VAD trigger. Даёт ~500ms «бесплатной» маскировки латентности
- [ ] **A3: Sentence-level TTS streaming** — Groq стримит → по предложениям → ElevenLabs. Ожидаемый gain: -100-200ms
- [ ] **Фаза 4: systemd + health check** — sofia-voice-asterisk.service, Restart=always
- [ ] **Proxy monitoring** — алерт если 8095 упал

## P1 — Следующая итерация

- [ ] **Рефакторинг find_recent_atlantis_lead()** → универсальный `find_recent_lead_by_source(source_id)` — сейчас хардкод на SOURCE_ID=397, блокер для масштабирования на новые ЖК
- [ ] **Вынести хардкоды в env/config** — SOFIA_AI_USER_ID (428), BITRIX_ATLANTIS_SOURCE_ID (397) → в .env или source_objects.py
- [ ] **Таймаут для web-виджета** — сейчас web-сессии не финализируются по таймауту, только по [END] от LLM
- [ ] **Лиды без бот-диалога** — клиенты из Тильды, не перешедшие в TG, не проходят квалификацию Софией. Варианты: CRM-робот с таймаутом или принять как нормальный путь
- [x] ~~**Битрикс в radist_gateway.py**~~ — выполнено 08.04: radist_leads таблица, привязка ATL-лидов, таймауты 15/60/15
- [ ] **Groq платный план** — бесплатный throttled 70% запросов в A/B тесте
- [ ] **Retell begin_message** — убрать или настроить тот же голос что в ответах
- [ ] **Retell Transcription Mode** — accuracy vs speed тест
- [ ] **Post-Call Data Extraction** — goal, budget, payment_type, meeting_agreed
- [ ] **deploy.sh** — скрипт деплоя (сейчас ручной cp + restart)

## P2 — Улучшения Voice

- [x] ~~**Добавить IP 72.56.64.91 в белый список Телфин**~~ — закрыто 08.04: Телфин не меняет GeoIP, двухсерверная архитектура — постоянное решение
- [ ] **Yandex STT gRPC v3 streaming** — вместо REST, параллельно с речью клиента (-200ms). Proto файлы уже в yandex_proto/. Gain: -150-200ms
- [ ] **Architecture A: Hybrid Brain** — async gpt-5.2+RAG «мозг» после каждого хода → stage_directive для kimi-k2. Качество текстовой Софии + скорость голосовой
- [ ] **Architecture B: Pre-recorded Bank** — 60 WAV-фраз покрывают 70% реплик, LLM-роутер выбирает код фразы. Gain: 350ms на 70% ходов
- [ ] **WebRTC кнопка в веб-виджете** — голосовой звонок в браузере
- [ ] **OpenAI Realtime API** — Voice V3, нативный voice-to-voice

## P3 — Техдолг / Стратегия

- [ ] **AI-ассистент руководителя над Битрикс/amoCRM** — Telegram-бот, function calling (20-30 целевых функций: crm.deal.list, tasks.list, user.list), запросы натуральным языком ("у кого провал по сделкам", "кто не дорабатывает"). Потенциально отдельный продукт, переиспользует архитектуру Sofia. Начинать после стабилизации голосовой Sofia + RIZALTA

- [ ] **Логирование бота в stdout** — сейчас bot_server.py пишет в файл через print(), не видно в journalctl
- [ ] **Чистка мусора в prod** — лишние файлы
- [ ] **core/channel.py, core/observer.py** — рефакторинг каналов
- [ ] **BUG-004 EN-раскладка** — обработка латиницы в сообщениях

## Завершено (09.04.2026)

- [x] **Radist dedup fix** — save_message+notify_observer вынесены из цикла queue, одна запись на пачку сообщений (DEV+PROD)
- [x] **Voice Research Sprint** — 54 аудиосемпла, 9 LLM, 16 TTS, 7 STT, отчёт RESEARCH_REPORT_VOICE_AGENT_v1.md
- [x] **Voice Stack Tuning v2** — kimi-k2 LLM, Flash v2.5 TTS, новые VoiceSettings, VAD 300ms, SSML breaks
- [x] **RIZALTA Prompt v2** — канонический питч, «всегда вопрос», Софья→София, 6 примеров диалогов
- [x] **Groq платный план** — решено через kimi-k2 (throttling не наблюдается)

## Завершено (28.03–06.04.2026)

- [x] **Фикс SOFIA_PATH в prod .env** — prod бот писал в dev БД, повтор бага 21.03 (05.04)
- [x] **Фикс логирования bitrix.py** — logging.basicConfig в bot_server.py, логи [BITRIX] видны в journalctl (05.04)
- [x] **Диагностика лидов 264270/264264/264260/264252** — все распределены, клиенты не заходили в бот (05.04)
- [x] **Деплой Bitrix-интеграции в PROD** — finalize_lead, start_distribution_bp, дедупликация по телефону (04.04)
- [x] **Фикс ASSIGNED_BY_ID=24932 перед БП** — БП 152 требует конкретного ответственного (04.04)
- [x] **Фикс manager_active в state_manager** — краш таймаута "no such column" (04.04)
- [x] **Новый webhook-токен с bizproc** — uviwr0b350u3m6gf (04.04)
- [x] **Фикс redirect Тильды** — был dev-бот, заменён на prod (04.04)
- [x] **E2E тест БП раздачи** — форма → лид → TG → 15 мин → BP 152 → раздача (04.04)
- [x] **docs/LEAD_LIFECYCLE.md** — архитектура CRM-интеграции (04.04)
- [x] **docs/NEW_CLIENT_ONBOARDING.md** — инструкция подключения нового ЖК (04.04)
- [x] **Голосовой стек Телфин → Asterisk → AudioSocket → STT/LLM/TTS** — полный pipeline на VPS (06.04)
- [x] **Asterisk + SIP trunk Телфин** — PJSIP, порт 5090, Registered (06.04)
- [x] **AudioSocket сервер** — voice_asterisk.py, TCP протокол, двусторонний аудио (06.04)
- [x] **Nginx LLM proxy** — 72.56.64.91:8095 для Groq/OpenAI/ElevenLabs из России (06.04)
- [x] **TTS streaming ElevenLabs** — first audio ~400-500ms вместо 5-8 сек (06.04)
- [x] **VAD 0.7s + barge-in** — перебивание останавливает TTS, контекст сохраняется (06.04)
- [x] **Фикс промпта "Повторите" на "Завтра"** — добавлен пример для дат/времени (06.04)
- [x] **A1: VAD threshold 0.4s** — снижено с 0.7s, -300ms ощущаемой паузы (07.04)
- [x] **ElevenLabs voice tuning** — stability=0.35, similarity=0.79, speed=1.19 (07.04)
- [x] **Research Qwen3-TTS** — 30 аудиофайлов, WaveSpeed API, отчёт готов (07.04)
- [x] **TASK_DUMP_SOFIA_PROMPTS.md** — полный дамп всех 9 промптов системы (07.04)
- [x] **Bitrix в Radist gateway** — radist_leads, ATL-привязка, таймауты 15/60/15, manager_active (08.04)
- [x] **Окно матчинга 60 сек** — find_recent_atlantis_lead фильтр >=DATE_CREATE (08.04)
- [x] **RIZALTA промпт v1** — VOICE_SYSTEM_PROMPT_RIZALTA + VOICE_PROMPT_MODE switch (08.04)
- [x] **Git recovery после краша** — DEV 3 коммита, PROD 5 коммитов по каналам (08.04)
- [x] **ElevenLabs multilingual_v2** — switch для PVC голоса Nastya (08.04)
- [x] Промпт V5-V5.2: persona, few-shot, позитивные инструкции (b34e5ffc → 8e0a7738)
- [x] Barge-in pending: замена debounce, склейка фраз (f83631ae)
- [x] meeting_agreed context check (e9b47719)
- [x] Voice pipeline v4: Groq llama-4-scout primary (TTFT 99ms)
- [x] Битрикс: БП раздачи (template 152) — finalize_lead() (c1987ff5)
- [x] Дедупликация транскриптов Retell (3-уровневая)
- [x] Budget парсинг (дефис, "от-до", числительные)
- [x] Исследование LLM: Groq, YandexGPT, Fireworks, Together, DeepSeek
