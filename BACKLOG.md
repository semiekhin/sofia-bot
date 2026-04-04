# BACKLOG — Невыполненные задачи

## P0 — Срочно

- [ ] **Живой тест промпта V5.2 + barge-in** — проверить few-shot, barge-in pending, context return
- [ ] **Retell Boosted Keywords** — нужен RETELL_API_KEY или ручная настройка в dashboard. Список: инвестиция, рассрочка, ипотека, Сочи, Туапсе, Анапа, Крым, Архыз, Алтай, миллион, бюджет, стройка, аренда, апартаменты, доходность, Оазис, созвон, эксперт

## P1 — Следующая итерация

- [ ] **Рефакторинг find_recent_atlantis_lead()** → универсальный `find_recent_lead_by_source(source_id)` — сейчас хардкод на SOURCE_ID=397, блокер для масштабирования на новые ЖК
- [ ] **Вынести хардкоды в env/config** — SOFIA_AI_USER_ID (428), BITRIX_ATLANTIS_SOURCE_ID (397) → в .env или source_objects.py
- [ ] **Таймаут для web-виджета** — сейчас web-сессии не финализируются по таймауту, только по [END] от LLM
- [ ] **Битрикс в radist_gateway.py** — подключить core/bitrix.py к Radist каналу (лиды из WhatsApp/Max не уходят в раздачу)
- [ ] **Groq платный план** — бесплатный throttled 70% запросов в A/B тесте
- [ ] **Retell begin_message** — убрать или настроить тот же голос что в ответах
- [ ] **Retell Transcription Mode** — accuracy vs speed тест
- [ ] **Post-Call Data Extraction** — goal, budget, payment_type, meeting_agreed
- [ ] **deploy.sh** — скрипт деплоя (сейчас ручной cp + restart)

## P2 — Улучшения Voice

- [ ] **Yandex TTS gRPC v3 + unsafe_mode** — правильные ударения для русского
- [ ] **Yandex STT + turn detection** — модуль работает, нужна интеграция с pipecat
- [ ] **Задарма SIP** — реальные звонки через Vapi/LiveKit/Pipecat
- [ ] **WebRTC кнопка в веб-виджете** — голосовой звонок в браузере
- [ ] **Yandex AI Studio (Alice AI / Qwen3-235B)** — серверы в РФ, лучший русский
- [ ] **OpenAI Realtime API** — Voice V3, нативный voice-to-voice
- [ ] **Retell high_priority_pool** — включить в dashboard (-50-150ms)

## P3 — Техдолг

- [ ] **Логирование бота в stdout** — сейчас bot_server.py пишет в файл через print(), не видно в journalctl
- [ ] **Чистка мусора в prod** — лишние файлы
- [ ] **core/channel.py, core/observer.py** — рефакторинг каналов
- [ ] **BUG-004 EN-раскладка** — обработка латиницы в сообщениях

## Завершено (28.03–04.04.2026)

- [x] **Деплой Bitrix-интеграции в PROD** — finalize_lead, start_distribution_bp, дедупликация по телефону (04.04)
- [x] **Фикс ASSIGNED_BY_ID=24932 перед БП** — БП 152 требует конкретного ответственного (04.04)
- [x] **Фикс manager_active в state_manager** — краш таймаута "no such column" (04.04)
- [x] **Новый webhook-токен с bizproc** — uviwr0b350u3m6gf (04.04)
- [x] **Фикс redirect Тильды** — был dev-бот, заменён на prod (04.04)
- [x] **E2E тест БП раздачи** — форма → лид → TG → 15 мин → BP 152 → раздача (04.04)
- [x] **docs/LEAD_LIFECYCLE.md** — архитектура CRM-интеграции (04.04)
- [x] **docs/NEW_CLIENT_ONBOARDING.md** — инструкция подключения нового ЖК (04.04)
- [x] Промпт V5-V5.2: persona, few-shot, позитивные инструкции (b34e5ffc → 8e0a7738)
- [x] Barge-in pending: замена debounce, склейка фраз (f83631ae)
- [x] meeting_agreed context check (e9b47719)
- [x] Voice pipeline v4: Groq llama-4-scout primary (TTFT 99ms)
- [x] Битрикс: БП раздачи (template 152) — finalize_lead() (c1987ff5)
- [x] Дедупликация транскриптов Retell (3-уровневая)
- [x] Budget парсинг (дефис, "от-до", числительные)
- [x] Исследование LLM: Groq, YandexGPT, Fireworks, Together, DeepSeek
