# BACKLOG — Невыполненные задачи

## P0 — Срочно

- [ ] **Ссылка в Тильде** — success URL: `https://t.me/humanAINeural_bot?start=ATL`
- [ ] **Retell Boosted Keywords** — нужен RETELL_API_KEY или ручная настройка в dashboard. Список: инвестиция, рассрочка, ипотека, Сочи, Туапсе, Анапа, Крым, Архыз, Алтай, миллион, бюджет, стройка, аренда, апартаменты, доходность, Оазис, созвон, эксперт
- [ ] **Живой тест промпта V4** — проверить фиксы: доходность 8-15%, [END] на "пришлите варианты", anti-looping
- [x] ~~Фикс дедупликации транскриптов~~ — 3-уровневая: exact + prefix + word overlap 85% (338bd94f)
- [x] ~~Budget парсинг~~ — _parse_budget_from_text(), дефис, "от-до", без "миллион" (338bd94f)

## P1 — Следующая итерация

- [ ] **Groq платный план** — бесплатный throttled 70% запросов в A/B тесте. Нужен paid tier
- [ ] **Retell begin_message** — убрать или настроить тот же голос что в ответах
- [ ] **Retell Transcription Mode** — accuracy vs speed тест
- [ ] **Post-Call Data Extraction** — goal, budget, payment_type, meeting_agreed
- [ ] **Битрикс в radist_gateway.py** — подключить core/bitrix.py к Radist каналу
- [ ] **deploy.sh** — скрипт деплоя

## P2 — Улучшения Voice

- [ ] **Yandex TTS gRPC v3 + unsafe_mode** — правильные ударения для русского
- [ ] **Yandex STT + turn detection** — модуль работает, нужна интеграция с pipecat
- [ ] **Задарма SIP** — реальные звонки через Vapi/LiveKit/Pipecat
- [ ] **WebRTC кнопка в веб-виджете** — голосовой звонок в браузере
- [ ] **Yandex AI Studio (Alice AI / Qwen3-235B)** — серверы в РФ, лучший русский. Нужен тест streaming TTFT
- [ ] **OpenAI Realtime API** — Voice V3, нативный voice-to-voice
- [ ] **Retell high_priority_pool** — включить в dashboard (-50-150ms)

## P3 — Техдолг

- [ ] **Чистка мусора в prod** — лишние файлы
- [ ] **core/channel.py, core/observer.py** — рефакторинг каналов
- [ ] **BUG-004 EN-раскладка** — обработка латиницы в сообщениях

## Завершено (28.03.2026)

- [x] Voice pipeline v4: Groq llama-4-scout primary (TTFT 99ms), OpenAI fallback
- [x] A/B тест: 3 модели, 12 кейсов single-turn + 4 сценария multi-turn
- [x] Промпт V4: ФАКТЫ, [END] правила, anti-looping, finish_reason
- [x] Дедупликация транскриптов Retell (3-уровневая)
- [x] Budget парсинг (дефис, "от-до", числительные)
- [x] Исследование LLM: Groq, YandexGPT, Fireworks, Together, DeepSeek
