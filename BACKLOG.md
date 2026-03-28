# BACKLOG — Невыполненные задачи

## P0 — Срочно

- [ ] **Ссылка в Тильде** — success URL: `https://t.me/humanAINeural_bot?start=ATL`
- [ ] **Фикс дедупликации транскриптов** — точные совпадения не ловятся, только prefix match
- [ ] **Budget парсинг** — "десять-пятнадцать" через дефис не парсится
- [ ] **Retell Boosted Keywords** — инвестиция, рассрочка, ипотека, Сочи, Туапсе, Анапа, Крым, Архыз, Алтай, миллион, бюджет, стройка, аренда

## P1 — Следующая итерация

- [ ] **Retell begin_message** — убрать или настроить тот же голос что в ответах
- [ ] **Retell Transcription Mode** — accuracy vs speed тест
- [ ] **Post-Call Data Extraction** — goal, budget, payment_type, meeting_agreed
- [ ] **Битрикс в radist_gateway.py** — подключить core/bitrix.py к Radist каналу
- [ ] **deploy.sh** — скрипт деплоя

## P2 — Улучшения Voice

- [ ] **Yandex TTS gRPC v3 + unsafe_mode** (#1, #2) — правильные ударения для русского
- [ ] **Yandex STT + turn detection** (#7) — модуль работает, нужна интеграция с pipecat (минус 0.5-1с на паузу)
- [ ] **Задарма SIP** (#17) — реальные звонки через Vapi/LiveKit/Pipecat
- [ ] **WebRTC кнопка в веб-виджете** — голосовой звонок в браузере
- [ ] **Groq + Llama/Qwen для Generator** — TTFT 54-146ms, качество русского под вопросом
- [ ] **OpenAI Realtime API** — Voice V3, нативный voice-to-voice
- [ ] **Cartesia Sonic 3** — TTFB 40ms, русский заявлен но не тестирован
- [ ] **Retell high_priority_pool** — включить в dashboard (-50-150ms)

## P3 — Техдолг

- [ ] **Чистка мусора в prod** — лишние файлы
- [ ] **core/channel.py, core/observer.py** — рефакторинг каналов
- [ ] **BUG-004 EN-раскладка** — обработка латиницы в сообщениях
