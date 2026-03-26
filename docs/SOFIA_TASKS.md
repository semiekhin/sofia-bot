# Задачи Sofia-GPT

📅 Обновлено: 26.03.2026

## 🚀 P0 — Ближайшие

- [x] **Битрикс: ASSIGNED_BY_ID=428 (Sofia AI)** — ЗАДЕПЛОЕНО 26.03.2026
- [x] **Деплой bot_server.py + web_api.py + core/bitrix.py в прод** — ЗАДЕПЛОЕНО 26.03.2026
- [x] **Битрикс только для source-сессий (ATL)** — _is_bitrix_session()
- [ ] **Ссылка в Тильде** — URL успеха: `https://t.me/humanAINeural_bot?start=ATL`
- [x] **Баг Retell: двойной ответ** — is_responding флаг в voice_api.py (26.03.2026)

## 🎙️ Голосовой агент

### Исследование ✅ ЗАВЕРШЕНО (25.03.2026)
- [x] Полное исследование: 8 направлений, 50+ решений → `docs/VOICE_RESEARCH_2026.md`
- [x] Целевой стек определён

### Вариант 1 — Retell AI ✅ РАБОТАЕТ
- [x] voice_api.py — WebSocket адаптер
- [x] gpt-4.1-mini, async Extractor, полный RAG
- [x] VOICE_PROMPT_ADDON (9 правил, включая запрет латиницы)
- [x] Баг двойного ответа починен (is_responding флаг)

### Вариант 2 — Pipecat + Daily ✅ РАБОТАЕТ
- [x] Pipecat 0.0.107, Daily WebRTC, sofia-oazis.daily.co
- [x] **ElevenLabs блокер решён** — причина: бесплатный план (402) + таймауты pipecat
- [x] Пропатчен AUDIO_CONTEXT_TIMEOUT=15.0 в pipecat
- [x] **core/pipeline.py подключён** — SofiaPipelineProcessor (ловит LLMContextFrame)
- [x] LLM буфер (полный ответ → TTS одним куском)
- [x] sanitize_for_tts() — латиница → кириллица, удаление URL/email
- [x] yandex_tts.py — кастомный Yandex TTS процессор (REST v1)
- [x] yandex_stt.py — кастомный Yandex STT процессор (gRPC v3)
- [x] VAD оптимизация: stop_secs=0.3, промпт 212 токенов, max_tokens=200

### Протестированные TTS
- [x] OpenAI TTS nova — работает, акцент на русском
- [x] ElevenLabs Nastya flash_v2_5 — TTFB 0.11с, ударения средние
- [x] ElevenLabs Nastya multilingual_v2 — TTFB 0.4-1.1с, ударения лучше
- [x] Yandex TTS alena neutral (REST v1) — нативный русский, ломается на латинице

### Нетестированные варианты (Voice)
- [ ] **Yandex TTS gRPC v3 + unsafe_mode** — лучшая просодия, правильные ударения
- [ ] **Yandex TTS Premium через gRPC v3** — marina, lera, dasha (через REST было роботично)
- [ ] **ElevenLabs streaming по клаузам** — 15-40 символов вместо целой фразы
- [ ] **ElevenLabs multilingual_v2 + клаузный буфер** — лучшие ударения + скорость
- [ ] **Cartesia Sonic 3** — TTFB 40ms, русский заявлен но не проверен
- [ ] **Fish Audio S2 Pro** — кастомный голос "Софии", self-hosted, Apache 2.0
- [ ] **Yandex STT + turn detection** — модуль работает, нужна интеграция с pipecat
- [ ] **Deepgram Nova-3 русский** — встроен в pipecat, не тестировали отдельно
- [ ] **Soniox** — WER 6.2% русский, $0.002/мин
- [ ] **gpt-5-nano reasoning_effort=minimal** — TTFT 0.56с, 157 tok/s
- [ ] **gpt-5-mini** — новая модель, не тестировали для голоса
- [ ] **Groq + Qwen3-32B для Generator** — TTFT 0.1-0.3с
- [ ] **Vapi** — managed платформа, $0.05/мин, Custom LLM webhook
- [ ] **Vapi + Задарма** — реальные телефонные звонки
- [ ] **LiveKit Agents** — нативный SIP bridge, лучший turn detection
- [ ] **Pipecat + LiveKit транспорт** — self-hosted WebRTC без Daily
- [ ] **Задарма SIP** — через Vapi, LiveKit или Pipecat
- [ ] **WebRTC кнопка в веб-виджете** — голосовой звонок в браузере
- [ ] **Параллельный Extractor + RAG** — -200-400ms
- [ ] **Предиктивный контекст** — RAG по partial transcript
- [ ] **Каскадная генерация** — быстрая модель → полная модель
- [ ] **Ресемплинг 48→24kHz** — портит Yandex TTS, нужен нативный rate

## ⚙️ Единое ядро ✅ ЗАДЕПЛОЕНО

- [x] core/pipeline.py — Analyzer → RAG → Generator
- [x] core/bitrix.py — Битрикс CRM + ASSIGNED_BY_ID=428
- [x] stream_voice_response() — voice (gpt-4.1-mini, RAG, async Extractor)
- [x] Деплой в прод — 21.03.2026 (core/), 26.03.2026 (bitrix + bot_server)

## 🔥 Технический долг

- [x] SOFIA_PATH баг — ПОЧИНЕН 21.03.2026
- [x] Bitrix в bot_server.py — ЗАДЕПЛОЕН 26.03.2026
- [x] Bitrix: ASSIGNED_BY_ID=428 — ЗАДЕПЛОЕН 26.03.2026
- [ ] Bitrix в radist_gateway.py — P1
- [ ] deploy.sh
- [ ] Очистка мусора в проде
- [ ] BUG-004 EN-раскладка
- [ ] core/channel.py, core/observer.py
