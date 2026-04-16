# BACKLOG — Невыполненные задачи

## P0 — Срочно

- [x] ~~**VOICE_YANDEX_MIGRATION_v1**~~ — выполнено 16.04: LLM→YandexGPT 5 Pro, TTS→Yandex Alena, cached greeting (0ms TTFB), anti-hallucination filter. A/B 4 моделей — Pro победил (LLM 638ms, user pause 860ms). TTS TTFB 177ms (было 1100ms). Dead branches сохранены для rollback.
- [x] ~~**RIZALTA промпт v3 + barge-in fix**~~ — выполнено 16.04: двухчастный питч без представления, логика мессенджеров (Ватсап/Макс/Телеграм), вход 15 млн, Совкомбанк/Сбер ипотека. Cached greeting регенерирован. Barge-in cooldown 500ms + MIN_SPEECH_BYTES 10240 задеплоены. Живой звонок UUID 21b96626 подтвердил: cooldown сработал 2×, MIN_BYTES 3×, логика мессенджеров дошла. Коммит `ef2888ae`.
- [ ] **🔴 Barge-in buffer reset вместо re-feed** — 16.04 живой звонок выявил: 13120-байтовый barge-in буфер (0.82с, прошёл MIN_BYTES порог 10240) попал в STT → garbled «Со стороны» → LLM-фолбэк «плохо слышно» из блока «Не расслышала». Фикс: в `_process_turn` finally **не** переносить barge-in buffer в `_speech_buffer`, а просто очищать. После cooldown VAD начинает слушать свежую речь клиента с нуля. Файл: `voice_asterisk.py`. Эффорт: 0.5 дня.
- [ ] **🔴 Silero VAD замена energy-based RMS** — замена `compute_rms() > VAD_ENERGY_THRESHOLD` на ONNX Silero VAD (1.8MB, <1ms CPU, 8kHz natively). Drop-in замена, 30 строк кода. Gain: +90% precision на шумах (убирает STT «Эротика»/«Зависят облака»), можно снизить `VAD_SILENCE_THRESHOLD` 300ms→150-200ms без false-early-end. Итого −100-150ms latency. Подробности: `docs/VOICE_RESEARCH_2026_04_16.md` идея #4.
- [ ] **🔴 fail2ban/UFW на VPS 185.207.66.201** — SIP-сканеры (193.46.255.104 + 172.110.223.135) раздувают Asterisk full.log ~8G/сутки. Диск вырос с 15% до 45% за сутки после вчерашней чистки. logrotate починен (daily rotate 7), но при ~8G/день ротация не спасёт — нужна блокировка источника. Переведён из P2 в P0.
- [ ] **ATLANTIS_ADDON_INFRA_PORTBACK** — в PROD отсутствует механизм чтения `prompt_addon`: в `config/source_objects.py` Атлантис-объект закрывается сразу после `greeting` (ключа `prompt_addon` нет), в `core/pipeline.py` нет ветки `if obj_config.get("prompt_addon")`. Весь Atlantis-addon-механизм — DEV-only фича, никогда не был в PROD. Sofia в PROD Atlantis-flow не получает специальных правил, включая давнее «не запрашивай контакты, клиент уже из формы» и новые safety-триггеры (СВО/политика/дискриминация/мошенничество). 400+ строк разницы между PROD и DEV `core/pipeline.py`. Требуется отдельный спринт: полный diff pipeline.py PROD vs DEV, классификация расхождений, план порта по частям, контролируемый деплой с разведкой. Блокер для работы всех Atlantis-specific правил в production.
- [ ] **Git-sanity scan prod vs dev** — пройтись по всем логическим файлам (core/, config/, *_server.py, *_gateway.py), сравнить md5 HEAD в prod и dev, найти расхождения. Уже известно: `core/pipeline.py` (400+ строк разницы, см. ATLANTIS_ADDON_INFRA_PORTBACK), `config/source_objects.py` (black-drift на `detect_source`/`load_object_context` + отсутствие `prompt_addon`). Могут быть другие. Мини-спринт на 15-20 мин после ATLANTIS_ADDON_INFRA_PORTBACK.
- [x] ~~**B1: Filler звуки**~~ — закрыто 16.04: не актуально после миграции на Yandex. TTS TTFB 177ms (было 700-900ms ElevenLabs v3), fillers не нужны при такой латентности.
- [x] ~~**A3: Sentence-level TTS streaming**~~ — закрыто 16.04: не актуально. Yandex TTS v1 REST TTFB 177ms быстрее чем ElevenLabs streaming был. Gain минимален.
- [ ] **Ударения Yandex Alena** — проверить ударения на ключевых словах (Белокуриха, РИЗАЛТА, эскроу). Yandex SpeechKit лучше ElevenLabs на русском (~99% vs ~80%), но нужна проверка.
- [ ] **Proxy monitoring** — алерт если 8095 упал (теперь менее критично — голос не использует proxy, только текстовые каналы)

## P1 — Следующая итерация

- [ ] **Yandex STT v3 gRPC streaming** — заменить REST v1 на bidirectional gRPC stream (`Recognizer/RecognizeStreaming`), partial+final результаты, EOU от сервера. Proto в `yandex_proto/` уже есть. Gain: −150-300ms (убирает REST TLS handshake + VAD 300ms timeout), меньше false-cut фраз. Эффорт: 1-2 дня. Подробности: `docs/VOICE_RESEARCH_2026_04_16.md` идея #1. Поднято из P2 16.04.
- [ ] **Sentence-level LLM streaming → TTS pipelining** — YandexGPT 5 Pro поддерживает `stream=True` SSE. Код сейчас ждёт `full_text = resp.choices[0].message.content` полностью. Переписать на async iterator: как только готово первое предложение — в TTS streaming, начинать играть, параллельно синтезировать второе. Нужен sentence splitter стойкий к «10 млн.» и anti-hallucination stop-sequence на partial. Gain: −200-350ms медиана на репликах >1 предложения. Эффорт: 2 дня. Идея #3.
- [ ] **TTS cache canonical phrases + backchannel fillers** — расширить механизм `greeting_rizalta.pcm` на весь каноничный питч и типовые ответы («Понимаю», «Хорошего дня», «Простите, плохо слышно»). Плюс 5-10 pre-rendered filler-PCM («Так…», «Секундочку») с intent-classifier. Гейт: проигрывать filler при ожидаемом LLM >500ms. Gain: cache hit → 5ms TTS, перцептивная пауза → <100ms. Эффорт: 1.5 дня. Идеи #6+#7.
- [ ] **Sprint 2: Sofia-GPT текстовый стек миграция на Yandex** — Extractor+Analyzer→YandexGPT Lite (дёшево, быстро для NLU), Generator→Qwen3-235B или Alice AI LLM (качество важнее скорости для текста), Embeddings→Yandex. A/B через promptfoo. Мотивация: после голосовой миграции 16.04 текстовый стек остался на OpenAI (gpt-5.2) — единая платформа снижает зависимости и стоимость.
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

- [ ] **Alice AI LLM для голоса** — попробовать Alice AI с max_tokens=80 и жёстким промптом "15 слов". В A/B 16.04 показала лучшее качество ответов, но многословна (user pause 2160ms). С ограничением длины может стать конкурентоспособной по скорости.
- [x] ~~**Добавить IP 72.56.64.91 в белый список Телфин**~~ — закрыто 08.04: Телфин не меняет GeoIP, двухсерверная архитектура — постоянное решение
- [x] ~~**fail2ban или UFW whitelist против SIP-сканеров**~~ — переведено в P0 (16.04), см. выше
- [ ] **UFW на VPS 185.207.66.201** — сейчас неактивен, SSH и Asterisk открыты в мир
- [ ] **Проверить STT pipeline voice_asterisk.py** — логи говорят "Whisper STT", CLAUDE.md говорит "Yandex SpeechKit". Привести документацию в соответствие с реальным кодом
- [x] ~~**Yandex STT gRPC v3 streaming**~~ — поднято в P1 16.04 (после voice research)
- [ ] **Per-turn JSON metrics baseline** — завести JSONL-лог `turn_metrics.jsonl` по одной строке на turn: `{call_uuid, turn_idx, stt_ms, llm_ms, tts_first_byte_ms, tts_total_ms, user_text_len, asst_text_len, barge_in_count, stage}`. Модуль `metrics.py`, инжект в `_process_turn`. Gain: p50/p95/p99 dashboard, обязательно ДО остальных latency-оптимизаций чтобы мерить эффект. Эффорт: 1 день. Идея #15.
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
