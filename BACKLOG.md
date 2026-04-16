# BACKLOG — Невыполненные задачи

## P0 — Срочно

- [ ] **🔴 VOICE_FIX: замена Groq-модели + OpenAI fallback proxy** — `moonshotai/kimi-k2-instruct` убрана из Groq (404 model_not_found), OpenAI fallback идёт напрямую без proxy (403 GeoIP). Голосовой канал полностью мёртв с неизвестной даты (между 10-16.04). Fix: (1) VOICE_MODEL_GROQ=`meta-llama/llama-4-scout-17b-16e-instruct` в .env, (2) OPENAI_BASE_URL=`http://72.56.64.91:8095/openai/v1` в .env, (3) проверить voice_asterisk.py использует OPENAI_BASE_URL, (4) restart + тестовый звонок. После стабилизации: A/B тест llama-4-scout vs qwen/qwen3-32b.
- [ ] **🔴 fail2ban/UFW на VPS 185.207.66.201** — SIP-сканеры (193.46.255.104 + 172.110.223.135) раздувают Asterisk full.log ~8G/сутки. Диск вырос с 15% до 45% за сутки после вчерашней чистки. logrotate починен (daily rotate 7), но при ~8G/день ротация не спасёт — нужна блокировка источника. Переведён из P2 в P0.
- [ ] **ATLANTIS_ADDON_INFRA_PORTBACK** — в PROD отсутствует механизм чтения `prompt_addon`: в `config/source_objects.py` Атлантис-объект закрывается сразу после `greeting` (ключа `prompt_addon` нет), в `core/pipeline.py` нет ветки `if obj_config.get("prompt_addon")`. Весь Atlantis-addon-механизм — DEV-only фича, никогда не был в PROD. Sofia в PROD Atlantis-flow не получает специальных правил, включая давнее «не запрашивай контакты, клиент уже из формы» и новые safety-триггеры (СВО/политика/дискриминация/мошенничество). 400+ строк разницы между PROD и DEV `core/pipeline.py`. Требуется отдельный спринт: полный diff pipeline.py PROD vs DEV, классификация расхождений, план порта по частям, контролируемый деплой с разведкой. Блокер для работы всех Atlantis-specific правил в production.
- [ ] **Git-sanity scan prod vs dev** — пройтись по всем логическим файлам (core/, config/, *_server.py, *_gateway.py), сравнить md5 HEAD в prod и dev, найти расхождения. Уже известно: `core/pipeline.py` (400+ строк разницы, см. ATLANTIS_ADDON_INFRA_PORTBACK), `config/source_objects.py` (black-drift на `detect_source`/`load_object_context` + отсутствие `prompt_addon`). Могут быть другие. Мини-спринт на 15-20 мин после ATLANTIS_ADDON_INFRA_PORTBACK.
- [ ] **B1: Filler звуки** — записать через ElevenLabs v3 Nastya: "Угу", "Так", "Понятно", "Хорошо". Кешировать как 8kHz PCM, проигрывать сразу после VAD trigger. Маскировка ~200-250ms латентности v3. Sprint Contract готов.
- [ ] **A3: Sentence-level TTS streaming** — Groq стримит → первое предложение → ElevenLabs v3 сразу. Gain: -100-200ms. Делать ПОСЛЕ fillers.
- [ ] **Ударения: ручной словарь** — STRESS_DICT с фонетическими заменами для проблемных слов (Белокуриха, РИЗАЛТА, эскроу). Research завершён: ruaccent отклонён (388ms, 75%), U+0301 не документирован в ElevenLabs.
- [ ] **Proxy monitoring** — алерт если 8095 упал

## P1 — Следующая итерация

- [ ] **Рефакторинг find_recent_atlantis_lead()** → универсальный `find_recent_lead_by_source(source_id)` — сейчас хардкод на SOURCE_ID=397, блокер для масштабирования на новые ЖК
- [ ] **Вынести хардкоды в env/config** — SOFIA_AI_USER_ID (428), BITRIX_ATLANTIS_SOURCE_ID (397) → в .env или source_objects.py
- [ ] **Спринт 3: возврат виджета в новом формате** — slide-out side tab на invest-apartmens.online/atlantis (заменяет старый круглый bubble). Требует: новая вёрстка (side tab вместо bubble, брендинг Атлантиса сохранить), URL-based source_object detection (по page_url а не по ключевым словам в тексте), разделение prompt_addon по каналам: Telegram — не спрашивать контакты, виджет — обязательно спрашивать телефон, таймаут финализации для виджет-сессий (или покрытие Bitrix-роботом), Bitrix-интеграция: source_id, attention к ASSIGNED=428 flow. **БЛОКЕР:** ждёт verification что 20-минутный Bitrix-робот реально работает — без safety-net виджет утопит CRM зависшими лидами.
- [ ] **Safety-net verification** — после того как админ добьёт 20-минутный робот в Bitrix: проверить что робот ловит Тильда-лидов с ASSIGNED=428 старше 20 мин и корректно передаёт менеджеру через БП 152. Тест-кейсы: лид #264518 (Роман) и аналогичные. Если робот не покрывает — план Б: cron внутри Sofia.
- [ ] **source_objects.py prompt_addon разделение по каналам** — сейчас DEV имеет незакоммиченный prompt_addon "не запрашивай контакты", который применяется ко всем Атлантис-сессиям включая виджет (где логика должна быть обратной). Нужно разделение: Telegram наследует prompt_addon, виджет — нет. Связано со Спринтом 3.
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
- [ ] **fail2ban или UFW whitelist против SIP-сканеров** — 193.46.255.104 и подобные раздувают Asterisk-логи на VPS 185.207.66.201
- [ ] **UFW на VPS 185.207.66.201** — сейчас неактивен, SSH и Asterisk открыты в мир
- [ ] **Проверить STT pipeline voice_asterisk.py** — логи говорят "Whisper STT", CLAUDE.md говорит "Yandex SpeechKit". Привести документацию в соответствие с реальным кодом
- [ ] **Yandex STT gRPC v3 streaming** — вместо REST, параллельно с речью клиента (-200ms). Proto файлы уже в yandex_proto/. Gain: -150-200ms
- [ ] **Architecture A: Hybrid Brain** — async gpt-5.2+RAG «мозг» после каждого хода → stage_directive для kimi-k2. Качество текстовой Софии + скорость голосовой
- [ ] **Architecture B: Pre-recorded Bank** — 60 WAV-фраз покрывают 70% реплик, LLM-роутер выбирает код фразы. Gain: 350ms на 70% ходов
- [ ] **WebRTC кнопка в веб-виджете** — голосовой звонок в браузере
- [ ] **OpenAI Realtime API** — Voice V3, нативный voice-to-voice
- [ ] **journalctl --vacuum-time vs --vacuum-size** — на disk-rescue 15.04 использовали `--vacuum-size=200M`, что снесло логи sofia-voice целиком. На будущее предпочтительнее `--vacuum-time=Nd` для предсказуемого окна (хранить всё за последние N дней)
- [ ] **chore(format): run black on prompt files** — `sofia_prompt_v2.py` содержит pre-existing долг в `format_state_summary` (несжатые словари, trailing whitespace, mixed quotes), `black --check` не проходит и в DEV, и в PROD после split-deploy 15.04. Запустить black одним проходом, снять явное разрешение на `--no-verify` для будущих правок этого файла
- [ ] **chore(format): backport black on source_objects.py from dev to prod** — DEV имеет black-форматирование `detect_source()` и `load_object_context()` (multi-line re.sub, double quotes), PROD — старый single-line single-quoted формат. Ожидает отдельного коммита-портбэка в PROD, не блокер
- [ ] **Sofia в PROD web-канале не устанавливает source_object** — grep по web_api.py даёт 0 совпадений по `source_object`/`detect_source`. Значит даже после ATLANTIS_ADDON_INFRA_PORTBACK web-канал не будет активировать Atlantis-addon, пока не добавить вызов `detect_source()` + `state.source_object = 'atlantis'` при создании сессии с page_url содержащим `/atlantis` или при первом сообщении с ключевыми словами. Блокер для Sprint 3 «возврат виджета»
- [ ] **Analyzer классифицирует СВО как OBJECTION** — в DEV smoke 15.04 Analyzer отнёс СВО к stage=OBJECTION и затянул 10 RAG-примеров возражений, LLM пошёл по паттерну contrarg+next question вместо передачи менеджеру. Даже если Atlantis-addon попадёт в промпт (после ATLANTIS_ADDON_INFRA_PORTBACK) — новый триггер проиграет RAG-примерам в приоритете. Решение: либо hard-gate в pipeline по regex до Analyzer, либо перенести блок запретов из хвоста промпта в начало (CLAUDE.md «V6 прoмпт» пункт 1 — «жёсткие запреты в начале»)

## P3 — Техдолг / Стратегия

- [ ] **Очистить legacy на VPS** — /root/dnstt, /root/microsocks, /root/go, /root/slowdns — от предыдущего владельца, безопасно удалить
- [ ] **AI-ассистент руководителя над Битрикс/amoCRM** — Telegram-бот, function calling (20-30 целевых функций: crm.deal.list, tasks.list, user.list), запросы натуральным языком ("у кого провал по сделкам", "кто не дорабатывает"). Потенциально отдельный продукт, переиспользует архитектуру Sofia. Начинать после стабилизации голосовой Sofia + RIZALTA

- [ ] **Логирование бота в stdout** — сейчас bot_server.py пишет в файл через print(), не видно в journalctl
- [ ] **Чистка мусора в prod** — лишние файлы
- [ ] **core/channel.py, core/observer.py** — рефакторинг каналов
- [ ] **BUG-004 EN-раскладка** — обработка латиницы в сообщениях
- [ ] **Обновить userMemories оркестратора** — устарели на сутки, упоминают V5 промпт, llama-4-scout, Flash v2.5 (давно kimi-k2 и eleven_v3), нет упоминаний ATLANTIS_ADDON_INFRA_PORTBACK, SPRINT_TEMPLATE_v2, виджета, safety-rules. Не блокер пока есть Gitpull, но создаёт противоречия в первый момент сессии. Делает оркестратор сам через memory_user_edits в начале следующей сессии, 10 минут.

## Завершено (15.04.2026)

- [x] **DISK_RESCUE_v2** — VPS 185.207.66.201 диск 100% → 15%, корневая причина (сломанный с 2022 logrotate-конфиг) найдена и починена. Освобождено 25 GB. Asterisk + sofia-voice не пострадали, mtime configs не изменился. Бэкап старого конфига в `/etc/logrotate.d/asterisk.broken.20260415`
- [x] **CONTEXT_RECONCILIATION_v1** — сверка модели Claude Code с реальностью по 7 пунктам. Sprint 2 verified в production (лид 265712, @pordiregrwe → UF_CRM_TELEGRAM заполнен, БП 152 отработал)
- [x] **ORCHESTRATOR_RULES.md** — отдельный документ с правилами работы оркестратора, зафиксированы уроки 10-15.04
- [x] **logrotate для Asterisk** — починен корневой баг конфига (был в P1 как "настроить logrotate")
- [x] **UPDATE_GITPULL_DOCS** — блок «Gitpull» в CLAUDE.md дополнен 4-й scp-командой для `docs/ORCHESTRATOR_RULES.md` + `mkdir docs/`. Блок «Session End» обновлён. Локальный `start-session.sh` Сергей обновил синхронно. Коммит 5fee930c.
- [x] **ATLANTIS_CHAT_WIDGET_v1** — `widgets/atlantis_chat_widget.html` (15.9 KB), самодостаточный HTML-блок для Tilda T123. Десктоп: круг 72×72 с pulse-ring. Мобильный: плашка снизу с аватаркой. Ведёт в @SofiaOazis через вторую Telegram Business Link. Круг зелёный по фидбеку Сергея. Коммит 3de1fbf9.
- [x] **SPRINT_TEMPLATE_v2** — `docs/SPRINT_TEMPLATE_v2.md` (13.3 KB) на XML-структуре по гайду Anthropic. 9 обязательных секций + 4 опциональных + 2 встроенных блока (anti_overengineering, investigate_before_answering) + filling example. Коммит 057b6811.
- [x] **TEMPLATE_V2_WIRING** — шаблон проведён в ORCHESTRATOR_RULES.md (правило «новые контракты строить по SPRINT_TEMPLATE_v2.md») и в Gitpull блок CLAUDE.md. Коммит 71103849.
- [x] **SAFETY_RULES_v1 (DEV)** — блок «ЧЕГО SOFIA НЕ ДЕЛАЕТ» в `sofia_prompt_v2.py` (универсальные запреты: паспорт/реквизиты/коды/гарантии/доходность/бронь) и блок «ПЕРЕДАЁТ ДИАЛОГ МЕНЕДЖЕРУ» в Atlantis-addon (политика/юр-фин компании/СВО/дискриминация/незаконные схемы/мошенничество). DEV smoke #2 подтвердил работу общего ядра. Коммит 772cbe6e `--no-verify` (pre-existing долг в format_state_summary).
- [x] **SAFETY_RULES_DEPLOY_PROD (split, core only)** — портировано в PROD **только** `sofia_prompt_v2.py` (блок «ЧЕГО SOFIA НЕ ДЕЛАЕТ», работает во всех трёх PROD-каналах). Atlantis-addon часть отложена до ATLANTIS_ADDON_INFRA_PORTBACK (в PROD отсутствует механизм чтения prompt_addon целиком). PROD smoke с СМС-триггером подтвердил работу. Все три сервиса active, 0 ошибок за 5-мин мониторинг. PROD коммит d60e9b0b, без push.
- [x] **GAPS_CLOSE_BEFORE_NEXT_SESSION** — закрыты 3 пробела перед следующей сессией: (1) стилистические правила Сергея («lf»=да, запрет ритуальных оборотов, короткое признание ошибок, один шаг=одно сообщение, «человеческим языком») добавлены пунктами 6-10 в ORCHESTRATOR_RULES.md «Стиль ответов»; (2) 4 критичных memory-файла добавлены в Gitpull блок CLAUDE.md (project_prod_dev_drift, user_sergey, project_voice_sprint_next, project_voice_vps); (3) в P3 заведён пункт на обновление userMemories оркестратора. Коммит 3081ea0e.

## Завершено (11.04.2026)

- [x] **Деплой Radist username→Bitrix в PROD** — sofia_radist_gateway.py + core/bitrix.py скопированы в PROD, sofia-radist.service перезапущен, логи чистые. PROD коммит 1146ea2c. (11.04)

## Завершено (10.04.2026)

- [x] **Аудит Атлантиса** — docs/AUDIT_ATLANTIS_2026-04-10.md, 8 секций, зафиксирован переход на @SofiaOazis, 5 открытых проблем с приоритетами
- [x] **Спринт 1: merge bot_server.py** — Observer portback из PROD в DEV (6 блоков, 86 строк), единственное различие осталось — env-default OBSERVER_CHAT_ID. DEV стал deploy-ready. Коммит 75b779a5.
- [x] **Спринт 2: Radist username → Bitrix** — chat.username из webhook → UF_CRM_TELEGRAM + COMMENTS. DEV коммит 8b504869, PROD деплой 11.04 коммит 1146ea2c.
- [x] **Фаза 4: systemd + health check** — sofia-voice.service на VPS, Restart=on-failure, auto-restart протестирован. Голосовой канал защищён от ребутов.
- [x] **TTS A/B тест: v3 locked** — live A/B: v3 > MLv2 > Flash v2.5. Eleven v3 = production TTS (10.04)
- [x] **Stress Research** — ruaccent 75%/388ms отклонён, U+0301 не документирован → ручной словарь (10.04)
- [x] **ElevenLabs v3 Research** — model_id, streaming, TTFB, PVC compatibility, pricing (10.04)
- [x] **Sync DEV от VPS** — voice_asterisk.py + core/pipeline.py синхронизированы, коммиты 8d468477 + 04d9a710 (10.04)

## Завершено (09.04.2026)

- [x] **Radist dedup fix** — save_message+notify_observer вынесены из цикла queue, одна запись на пачку сообщений (DEV+PROD)
- [x] **Voice Research Sprint** — 54 аудиосемпла, 9 LLM, 16 TTS, 7 STT, отчёт RESEARCH_REPORT_VOICE_AGENT_v1.md
- [x] **Voice Stack Tuning v2** — kimi-k2 LLM, Flash v2.5 → v3 TTS, новые VoiceSettings, VAD 300ms, SSML breaks
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
