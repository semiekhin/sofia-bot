# Исследование: голосовой помощник Sofia (16.04.2026)

## Контекст и baseline

Текущая цепочка на VPS 185.207.66.201 в России: AudioSocket TCP → energy-based VAD (RMS 200, 300ms silence) → Yandex STT REST v1 (~200ms) → YandexGPT 5 Pro (~638ms) → Yandex TTS Alena v1 REST 8kHz LPCM (~177ms). User-perceived pause ~860ms медиана. Barge-in с cooldown 500ms, MIN_SPEECH_BYTES_FOR_STT=10240 (0.64s), anti-hallucination regex. Канальная специфика: 8kHz G.711 через AudioSocket (slin16 конвертацией Asterisk) — тонкая точка для качества. TTS запрашивается одним non-streaming REST POST после получения ПОЛНОГО ответа LLM (`full_text` из `resp.choices[0].message.content`), т.е. никакого sentence-streaming нет.

Три главных незадействованных рычага обнаружены сразу:
1. Yandex предлагает **gRPC streaming** и для STT (v3 с `partial_results`), и для TTS v3 — текущий код использует REST v1 для обоих.
2. LLM возвращает весь ответ одним куском, TTS ждёт целиком — sentence-level streaming не сделан, хотя стоит 1 ночь работы и режет 300-500ms.
3. VAD примитивный энерджи-детектор без семантики и без Silero, из-за чего поставлены довольно агрессивные пороги (200 RMS, 300ms silence, 640ms минимум) — либо рубит хвосты фраз, либо добавляет задержку.

---

## Идеи улучшения

### 1. Yandex SpeechKit v3 gRPC streaming для STT с partial results
- **Что:** заменить текущий REST v1 на gRPC v3 bidirectional streaming (`yandex.cloud.ai.stt.v3.Recognizer/RecognizeStreaming`). Аудио идёт чанками по мере получения от AudioSocket (20ms фреймы), Yandex отдаёт `partial` и `final` эвенты. Можно начинать готовить prompt для LLM уже на `partial` result. EOU детектится сервером (встроенный VAD), не энерджи-порогом.
- **Gain:** убирает VAD-таймаут 300ms (EOU от сервера приходит сразу после реальной паузы, обычно 150-200ms), убирает REST round-trip (~100ms). В v3 partials `REAL_TIME` режим "sends partials and final responses as soon as possible". Итого: **-150-300ms к time-to-first-token LLM**.
- **Effort:** 1-2 дня. Протоки есть в `yandex_proto/` (уже используются). Нужно переписать `transcribe_audio()` на `async def stream_transcribe(...)` и дёргать из `_process_audio_vad`.
- **Риски:** TCP connection к Yandex может просесть — нужен reconnect loop. Ложные `final` на фоновых шумах — придётся докрутить `partial_results` confidence.
- **Приоритет:** **P0**
- **Источники:** [Yandex STT streaming v3 docs](https://github.com/yandex-cloud/docs/blob/master/en/speechkit/stt/streaming.md), [recognizeStreaming reference](https://github.com/yandex-cloud/docs/blob/master/en/speechkit/stt-v3/api-ref/grpc/Recognizer/recognizeStreaming.md)

### 2. Yandex TTS v3 gRPC streaming с sentence-level pipelining
- **Что:** заменить REST v1 на gRPC `Synthesizer/StreamSynthesis` (bidirectional) или `UtteranceSynthesis` (server streaming). В ответе приходят PCM-чанки по мере синтеза, а не весь файл. Лимит 250 символов/24 сек на один запрос = естественное деление на предложения.
- **Gain:** TTFB TTS падает с 177ms (REST) до ~80-120ms (gRPC streaming первый чанк). Но главное — комбинируется с идеей #3: начинаем проигрывать первое предложение пока синтезируется второе. **Экономия 200-400ms на репликах >1 предложения.**
- **Effort:** 1 день. Proto-файлы уже есть, `synthesize_tts_yandex()` в `voice_asterisk.py` переписать на async generator с `yield chunk`.
- **Риски:** Лимит 250 символов — если реплика длиннее, нужно резать по предложениям и склеивать. Для текущего промпта RIZALTA (1-2 фразы) почти не актуально.
- **Приоритет:** **P1**
- **Источники:** [Yandex TTS v3 gRPC](https://github.com/yandex-cloud/docs/blob/master/en/speechkit/tts-v3/api-ref/grpc/index.md), [TTS v3 Python example](https://github.com/yandex-cloud/docs/blob/master/ru/speechkit/tts/api/tts-examples-v3.md)

### 3. Sentence-level LLM streaming + параллельный TTS
- **Что:** YandexGPT 5 Pro поддерживает streaming (OpenAI-compatible `stream=True` через SSE). Код сейчас ждёт `full_text = resp.choices[0].message.content` — заменить на async iterator. Как только получили первое завершённое предложение (по regex `[.!?]\s`), сразу отправляем в TTS streaming (см. #2) и начинаем играть в AudioSocket. Параллельно продолжаем принимать токены и синтезировать второе предложение.
- **Gain:** time-to-first-audio падает с `LLM_full + TTS_first_byte` до `LLM_first_sentence + TTS_first_byte`. Для 2-фразного ответа RIZALTA первое предложение готово через ~300-400ms, а не 638ms. **-200-350ms медиана**, на длинных репликах ещё больше.
- **Effort:** 2 дня. Нужен sentence splitter устойчивый к сокращениям (эксперт, т.к. Yandex возвращает, например, «10 млн.» как потенциальный конец предложения). Нужна очередь `asyncio.Queue[Sentence]` между LLM-consumer и TTS-producer.
- **Риски:** если TTS отстаёт от LLM — нужен буфер в памяти. Если [END] ловится в последнем предложении — нельзя выпустить первое предложение пока не прочитали ответ полностью (но это не релевантно большинству реплик). Если anti-hallucination filter обрезал часть — надо заново отрендерить с новым «обрубленным» состоянием: сейчас обрезается ПОСЛЕ полной генерации. В streaming надо ловить "Пользователь:" как stop-sequence прямо на уровне partial чанков.
- **Приоритет:** **P0**
- **Источники:** [arxiv.org/html/2508.04721v1 — streaming LLM voice agents](https://arxiv.org/html/2508.04721v1), [LiveKit agent speech](https://docs.livekit.io/agents/multimodality/audio/)

### 4. Silero VAD вместо энерджи-детектора
- **Что:** ONNX модель (1.8MB), 30ms чанк <1ms CPU, поддерживает 8kHz натив, zero external deps. Интегрировать в `_process_audio_vad` как замену `compute_rms() > VAD_ENERGY_THRESHOLD`. Дополнительно Silero выдаёт вероятность речи (0.0-1.0), что позволяет снизить ложные срабатывания на шумах/кашле (у нас сейчас это падает в STT → pipeline → «Эротика», «Зависят облака» из логов).
- **Gain:** качество detection: 90%+ precision на шумах против ~60% у энерджи. Можно безопасно снизить `VAD_SILENCE_THRESHOLD` с 300ms до 150-200ms без false-early-end. **-100-150ms** и резкое снижение мусорных STT вызовов. Плюс при комбинации с LiveKit Turn Detector (см. #5) — ещё лучше.
- **Effort:** 0.5 дня. `pip install silero-vad` или ONNX runtime, 30 строк кода.
- **Риски:** +5-10MB RAM на worker, +1ms CPU на фрейм — на VPS незаметно. Русская речь: модель тренирована multilingual, проверена многими production-платформами (Pipecat, LiveKit) включая русский.
- **Приоритет:** **P0**
- **Источники:** [snakers4/silero-vad](https://github.com/snakers4/silero-vad), [Silero VAD в LiveKit](https://docs.livekit.io/agents/logic/turns/vad/), [Silero VAD в Pipecat](https://docs.pipecat.ai/server/utilities/audio/silero-vad-analyzer)

### 5. Семантический turn detector (EOU) на STT interim
- **Что:** LiveKit опубликовали open-source **EOU transformer** (135M params, SmolLM v2 fine-tune) который предсказывает «клиент договорил» по тексту partial STT. Пример: «Хочу инвестировать, но…» — VAD сказал бы "end", EOU говорит «ждём, фраза не закончена». Модель open-weights, запускается на CPU (или на дешёвом GPU на VPS). Для русского прямого EOU нет, но модель работает на токенах и fine-tune поверх русских диалогов возможен за пару дней на 1000+ диалогов из Telegram-канала Sofia.
- **Gain:** сейчас Sofia режет паузы клиента между словами (медианный клиент думает 500-800ms между мыслями; VAD считает это endpoint). EOU вернёт реплики «да… ну в общем… скажем, десять миллионов» целиком вместо трёх. **+качество UX заметно, меньше «Простите, повторите?»**.
- **Effort:** 3-4 дня (скачать model, интегрировать в pipeline, опционально fine-tune). Без fine-tune — тестить базовую модель, возможно уже неплохо.
- **Риски:** добавляет ~100-200ms inference на каждый `partial` (можно каждый 3-й). Модель не локализована — может хуже работать на коротких русских репликах.
- **Приоритет:** **P1**
- **Источники:** [LiveKit turn detector blog](https://blog.livekit.io/using-a-transformer-to-improve-end-of-turn-detection), [livekit/turn-detector HF](https://huggingface.co/livekit/turn-detector), [LiveKit turn detection article](https://livekit.com/blog/turn-detection-voice-agents-vad-endpointing-model-based-detection)

### 6. Backchannel filler-фразы и prosodic bridging
- **Что:** перед тем как LLM сформулировал ответ (особенно при долгих «Подскажите, что по оплате…» — это ~700ms), проигрывать заранее синтезированный short filler: «Так…», «Секундочку», «Хм, поняла», «Давайте посмотрим». Выбор filler по классификатору intent (быстрое правило на первых 3 словах STT). Хранить 5-10 pre-rendered PCM-файлов рядом с `greeting_rizalta.pcm`. Запускать playback по событию STT `final`, а не после LLM.
- **Gain:** субъективно ощущаемая пауза падает с 860ms до <100ms (первый звук). Реальная latency та же, но UX становится человечный — как живой оператор «секундочку, посмотрю».
- **Effort:** 1 день. Сгенерировать 10 PCM, добавить intent-классификатор (простой keyword-match), вставить в `_process_turn` перед LLM.
- **Риски:** при злоупотреблении — раздражает. Нужно применять только когда LLM ожидается >500ms (не каждую реплику). Filler не должен накладываться на ответ Sofia — таймаут отмены 400ms.
- **Приоритет:** **P0**
- **Источники:** [Ultravox latency](https://www.ultravox.ai/voice-ai/understanding-latency-in-voice-ai-systems), [Azure interim responses](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/how-to-voice-live-interim-response), [Pipecat TTS cache](https://github.com/omChauhanDev/pipecat-tts-cache), [Remi Etien voice AI latency post](https://dev.to/remi_etien/i-built-a-voice-ai-with-sub-500ms-latency-heres-the-echo-cancellation-problem-nobody-talks-about-14la)

### 7. TTS cache для частых фраз
- **Что:** приветствие уже cached в `greeting_rizalta.pcm` (умно!). Расширить на весь каноничный питч RIZALTA («У меня для вас важная новость. Стартовали продажи апартаментов на Алтае...») и типовые ответы («Понимаю», «Этих деталей под рукой нет», «Хорошего дня!»). Хранить sha256(text) → pcm путь. Cache hit = 0ms TTS.
- **Gain:** Pipecat TTS cache даёт <5ms hit latency и режет 100% TTS при cache hit. Для RIZALTA с его каноничным питчем — **при cache hit latency падает с 177ms до ~5ms**. Также экономит Yandex quotas.
- **Effort:** 0.5 дня. Мини-функция `cache_or_synthesize(text) → pcm_bytes`. Warm-up скрипт для генерации canonical phrases.
- **Риски:** голос может измениться между cached и live фразами если Yandex обновит Alena — надо invalidate по voice_id+model_version. Минимум.
- **Приоритет:** **P0**
- **Источники:** [Pipecat tts-cache](https://github.com/omChauhanDev/pipecat-tts-cache), [GitHub issue Pipecat #2629](https://github.com/pipecat-ai/pipecat/issues/2629)

### 8. Connection prewarm для Yandex API
- **Что:** держать постоянный TCP+TLS+gRPC channel к `stt.api.cloud.yandex.net:443` и `tts.api.cloud.yandex.net:443`. Сейчас каждая реплика = новый `httpx.AsyncClient` = новый TLS handshake (~50-100ms). Создать singleton `YandexChannels` на старте сервера, держать keepalive пинг раз в 30 сек.
- **Gain:** **-50-100ms на каждый STT и каждый TTS вызов** (не тратим на TLS). Итого -100-200ms total. LiveKit docs явно называют это «can add up to ~2 seconds (DNS, SSL roundtrips)» если не сделано.
- **Effort:** 0.5 дня. Module-level `async_client` с reuse.
- **Риски:** connection stale через NAT timeout. Решается keepalive. Yandex может не любить очень долгие idle — проверить по логам после недели.
- **Приоритет:** **P0**
- **Источники:** [LiveKit prewarm issue #3240](https://github.com/livekit/agents/issues/3240), [DupDub TTS latency](https://www.dupdub.com/blog/tts-latency-optimization)

### 9. STT context biasing / hotwords для доменного словаря
- **Что:** Yandex v3 STT поддерживает **custom dictionary через training** (не online-hotwords в запросе, а отдельно тренируемая модель). RIZALTA-домен: «Белокуриха», «Зонт Хотэл», «Корэ Икспи», «эскроу», «апарт-отель» — эти слова сейчас регулярно распознаются как фонетический мусор. Альтернатива: local post-processing — фонетический rescore по `SequenceMatcher.ratio()` против словаря доменных терминов.
- **Gain:** повышение WER на доменных словах с ~70% до ~95%. LLM получает чистый текст, не «Эскра-то» или «Корэ Эксби» → лучше отвечает. Особенно критично для отвечающих клиентов, переспрашивающих названия.
- **Effort:** 1 день для post-processing (быстрый путь). 1 неделя + обучение если идти через Yandex custom model.
- **Риски:** post-processing может «исправить» правильно распознанное слово. Решается threshold + явный whitelist домена.
- **Приоритет:** **P2**
- **Источники:** [Yandex STT custom vocabulary](https://github.com/yandex-cloud/docs/blob/master/en/speechkit/stt/models.md)

### 10. Echo cancellation с WebRTC AEC или speexdsp-python
- **Что:** сейчас barge-in сделан через повышенный энерджи-порог (`VAD_ENERGY_THRESHOLD * 1.5`) + cooldown 500ms — компенсация за то что микрофон клиента слышит собственный TTS Sofia (line echo через SIP). AEC (Acoustic Echo Cancellation) берёт на вход far-end (наш TTS стрим) и near-end (микрофон) → вычитает echo. Python-библиотека `speexdsp-python` + Speex AEC algorithm работает на 8kHz, C-реализация, ~0.5ms CPU на фрейм.
- **Gain:** можно снизить `BARGE_IN_COOLDOWN` с 500ms до 100ms (нет эха = нет каскада), снизить `VAD_ENERGY_THRESHOLD * 1.5` до `*1.0` → barge-in детектится на 300-400ms раньше, меньше «Sofia продолжает говорить после перебивания». Реальный UX-win при агрессивных перебиваниях клиента.
- **Effort:** 2 дня. Подключить speexdsp, передавать last 200ms TTS-буфера как far-end reference в AEC перед передачей микрофона в VAD.
- **Риски:** AEC чувствителен к синхронизации far/near. Телфин может добавить свою линию задержки. Хрупкость на edge cases.
- **Приоритет:** **P2**
- **Источники:** [speexdsp-python](https://github.com/xiongyihui/speexdsp-python), [PJSIP AEC docs](https://docs.pjsip.org/en/latest/specific-guides/audio/aec.html), [WebRTC AEC](https://webrtc.github.io/webrtc-org/blog/2011/07/11/webrtc-improvement-optimized-aec-acoustic-echo-cancellation.html)

### 11. YandexGPT 5 Pro function calling для structured output вместо regex
- **Что:** текущий код делает rule-based extraction (`_extract_state_from_context`) и anti-hallucination regex post-factum. YandexGPT 5 Pro поддерживает tool calling (OpenAI-compatible). Определить tool `update_lead_state(goal, budget, payment_type, meeting_time)` → LLM сам заполняет slots, а не мы парсим русский текст. Промпт становится короче (можно убрать «[END] ставь только когда...»), ответ детерминированнее.
- **Gain:** +качество slot filling (сейчас rule-based видит «десять миллионов» но пропускает «около десятки»). +короче промпт = -30-50ms LLM latency. +проще state machine, меньше edge cases. Anti-hallucination становится built-in (LLM не выдаёт `update_lead_state(phone="+7123")` если не было номера).
- **Effort:** 2-3 дня. Переработать `stream_voice_response` под tool-calling loop. Нужен тест-сет минимум 50 диалогов для регрессии.
- **Риски:** tool calling может не поддерживать streaming — тогда конфликт с #3. YandexGPT 5 Pro возможно не поддерживает tools в том же запросе что и streaming — проверить. Неочевидный риск: модель может вызвать tool когда «не нужно».
- **Приоритет:** **P2**
- **Источники:** [YandexGPT 5](https://yandex.cloud/en/services/yandexgpt), [Grokipedia YandexGPT](https://grokipedia.com/page/yandexgpt), [YandexGPT_to_OpenAI adapter](https://github.com/sazonovanton/YandexGPT_to_OpenAI)

### 12. Few-shot промпт с golden examples + compact system prompt
- **Что:** текущий RIZALTA промпт = ~2000 символов (500 токенов). YandexGPT считается по input tokens. Compact prompt (500 chars = ~125 токенов) + вынос всех примеров в 6-8 few-shot ассистентских реплик в history. Также: явная инструкция «выведи ТОЛЬКО свою реплику, без маркера» становится не нужна — в few-shot нет маркеров, модель подражает.
- **Gain:** **-30-80ms LLM latency** (меньше prefill). Лучше соблюдение стиля (few-shot работает сильнее чем инструкция). Меньше «[END]»-галлюцинаций.
- **Effort:** 0.5 дня + тест-прогон 50 диалогов.
- **Риски:** few-shot занимает context window. Для 8k YandexGPT 5 Pro — не проблема.
- **Приоритет:** **P1**
- **Источники:** [VoiceInfra prompt engineering](https://voiceinfra.ai/blog/voice-ai-prompt-engineering-complete-guide)

### 13. TTS prosody и SSML tuning для Alena
- **Что:** сейчас `add_ssml_breaks()` вставляет `<break time="300ms"/>`. Yandex v3 TTS поддерживает больше: `<prosody rate="slow">`, `<emphasis level="strong">`, ё-замены. Для холодного обзвона ключевое — **замедление на числах** («десять миллионов», «два с половиной»). Также: Yandex v3 поддерживает контроль ударения через `+` (например `ко+рпус`). Для RIZALTA терминов «Белокури+ха», «эскро+у», «Корэ+ Икспи+». Встроить ruaccent (MIT, открытая) перед TTS.
- **Gain:** субъективное качество синтеза сильно выше. Для инвест-клиента слушание неправильно ударенного «Белокури́ха» (правильно «Белоку́риха») — моментальный триггер «это робот».
- **Effort:** 1 день. `pip install ruaccent`, обёртка в `sanitize_for_tts` + SSML-шаблон для чисел.
- **Риски:** ruaccent сам иногда ошибается (0.96 accuracy на homographs). Можно точечно добавить manual override для топ-20 домена (все термины RIZALTA).
- **Приоритет:** **P1**
- **Источники:** [RUAccent paper ACL Anthology](https://aclanthology.org/2025.coling-main.444.pdf), [GitHub Koziev StressModel](https://github.com/Koziev/StressModel), [Yandex SpeechKit voices](https://cloud.yandex.com/en-ru/docs/speechkit/tts/voices)

### 14. Переход на 16kHz audio path
- **Что:** сейчас весь pipeline жёстко 8kHz (G.711 из Телфин). Asterisk может транскодить к slin16 (16kHz PCM) — AudioSocket Type 0x12 уже обработан (`AS_TYPE_AUDIO_16K = 0x12`). STT на 16kHz заметно точнее (больше частотных деталей для согласных ш/щ/ч/с — особо критично для русского). TTS Alena на 16kHz звучит человечнее.
- **Gain:** WER STT улучшается на 10-15% относительных единиц на 16kHz vs 8kHz (общее место в ASR research). TTS v3 at 16kHz ≈ MOS 4.3, 8kHz ≈ MOS 3.8.
- **Effort:** 0.5 дня конфигурации Asterisk + 0.5 дня правок (`SAMPLE_RATE_IN=16000`, `frame_size=640` для 20ms, `sampleRateHertz="16000"` в Yandex params).
- **Риски:** Asterisk транскодит G.711→slin16 дешёвой линейной интерполяцией — апсемпл не добавит качества. Реальный gain минимален пока upstream физически 8kHz. Но TTS downpath выиграет если идти ElevenLabs-style (синтез 16kHz, downsample 8kHz на выдаче) — так меньше артефактов.
- **Приоритет:** **P3** (низкий gain при текущем G.711 upstream)
- **Источники:** [Asterisk AudioSocket slin16](https://community.asterisk.org/t/asterisk-audiosocket-unable-to-do-transcode-opus-slin16/110078)

### 15. Observability: per-turn JSON logs + Prometheus metrics
- **Что:** сейчас timings логируются строками (`Turn timings: STT=X, LLM=Y, TTS=Z`). Парсить сложно. Завести JSONL лог `turn_metrics.jsonl` по одной строке на turn: `{call_uuid, turn_idx, stt_ms, llm_ms, tts_first_byte_ms, tts_total_ms, user_text_len, asst_text_len, barge_in_count, stt_confidence, stage}`. Дополнительно: раз в минуту экспортировать в Prometheus/Telegraf для graph в Grafana.
- **Gain:** не улучшает latency, но даёт feedback loop — видно p50/p95/p99 по каждой стадии, сколько turns в сессии, процент barge-in, процент STT мусора. Без этого любая оптимизация — гадание.
- **Effort:** 1 день. Модуль `metrics.py`, инжектится в `_process_turn`.
- **Риски:** минимум. Дисковый IO — negligible.
- **Приоритет:** **P0** (нужно ДО остальных оптимизаций, чтобы мерить)
- **Источники:** [Speechmatics STT metrics](https://www.speechmatics.com/company/articles-and-news/speed-you-can-trust-the-stt-metrics-that-matter-for-voice-agents)

### 16. Speculative generation на interim STT
- **Что:** пока клиент ещё говорит (interim partial из STT v3 streaming), спекулятивно запустить LLM на текущем partial тексте. Если финальный STT совпал с последним spec partial — ответ уже готов (0ms LLM), проиграть. Если не совпал — отбросить, запустить снова.
- **Gain:** на коротких чётких репликах («да, удобно», «не сейчас», «скиньте») — LLM всегда «угадывает» и **LLM latency становится 0ms**. На длинных — лишний compute, но без штрафа к latency.
- **Effort:** 3 дня. Требует отменяемые LLM requests (YandexGPT не факт что умеет cancel) и дедуплицирующую логику.
- **Риски:** x2-x3 стоимость LLM токенов (каждый partial = новый request). При низкой стоимости YandexGPT 5 Pro — окупаемо. Скорее всего API не поддерживает cancellation → нужны таймауты на стороне клиента.
- **Приоритет:** **P2**
- **Источники:** [LTS-VoiceAgent speculative execution arxiv](https://arxiv.org/html/2601.19952), [streaming voice agents survey arxiv](https://arxiv.org/html/2508.04721v1)

### 17. T-one opensource ASR как fallback / primary для телефонии
- **Что:** T-one (Apache 2.0, от Tinkoff voicekit team) — Conformer streaming ASR **специально обученный на русской телефонии**, 300ms chunk. WER 6.20% на телефонии против WER ~9-11% у Yandex на тех же данных (по их бенчмаркам). Self-hosted, без cloud зависимости.
- **Gain:** (а) качество STT на телефонном канале лучше на 30%+, (б) не зависит от внешнего API → 0 network latency, (в) бесплатно. Можно ставить на тот же VPS 185.207.66.201 как Docker, обращаться к localhost.
- **Effort:** 2-3 дня. Docker deploy, интеграция в pipeline через HTTP/gRPC localhost, burn-in тест на 100 реальных звонках параллельно с Yandex (shadow mode).
- **Риски:** GPU на VPS 185.207.66.201 — скорее всего нет. CPU-режим T-one — медленнее (возможно >200ms chunk). Надо проверить spec VPS. Альтернатива — отдельный инференс-сервер за proxy (как сейчас для Groq).
- **Приоритет:** **P1** (если VPS тянет) / **P3** (если нет GPU)
- **Источники:** [voicekit-team/T-one GitHub](https://github.com/voicekit-team/T-one)

### 18. GigaAM v3 self-hosted как research track
- **Что:** Sber выпустил GigaAM v3 (MIT), 220M params, state-of-the-art на русском ASR, win 70:30 vs Whisper-large-v3. Streaming mode встроен. ONNX/TRT deployment. Варианты e2e_ctc + e2e_rnnt с нативной пунктуацией и нормализацией чисел («десять миллионов» → «10 000 000»).
- **Gain:** лучшее качество русского ASR в opensource. Нативная нормализация → можно убрать значительную часть `_extract_state_from_context` regex.
- **Effort:** 4-5 дней (ONNX export, Triton deploy, интеграция).
- **Риски:** требует GPU или мощный CPU. Для CPU-only VPS — возможно не real-time.
- **Приоритет:** **P3** (долгий экспериментальный трек)
- **Источники:** [salute-developers/GigaAM](https://github.com/salute-developers/GigaAM), [ai-sage/GigaAM-v3 HF](https://huggingface.co/ai-sage/GigaAM-v3), [GigaAM arxiv paper](https://arxiv.org/abs/2506.01192)

### 19. Jitter buffer и packet loss concealment в AudioSocket layer
- **Что:** сейчас AudioSocket читает фреймы строго sequential через `readexactly(3)` + payload. Телфин SIP может перепутать порядок фреймов (RTP jitter) или потерять. Asterisk ставит jitter buffer перед AudioSocket, но его настройки часто default (50ms fixed). Для воспроизведения TTS обратно — нет PLC, при packet loss будут щелчки.
- **Что делать:** в `pjsip.conf` выставить `use_avpf=yes` + adaptive jitter buffer (maxjitterbuffer=200). На выходной сторонe использовать Opus PLC (но AudioSocket = slin, не Opus — так что PLC делает Asterisk сам, нужна проверка настроек).
- **Gain:** +качество аудио на плохих каналах (мобильные клиенты, 3G). Меньше «подрывов» в STT → меньше мусорных транскрипций. Хрипы от TTS при 2-3% packet loss пропадают.
- **Effort:** 1 день конфигурации + инструментальный тест (artificial packet loss via tc netem).
- **Риски:** большой jitter buffer = добавленная латенси. Балансировать — 100-150ms discretion.
- **Приоритет:** **P2**
- **Источники:** [Asterisk codecs VoIP-Info](https://www.voip-info.org/asterisk-codecs/), [Giacomo Vacca Opus/G.711](https://www.giacomovacca.com/2016/10/opusg711-transcoding-for-practical-man.html)

### 20. Adaptive silence threshold по истории turn
- **Что:** сейчас `VAD_SILENCE_THRESHOLD=0.3` константа. Добавить adaptive: если в предыдущем turn клиент говорил >2 сек или сделал паузу внутри («эээ… десять миллионов») → повысить threshold до 500ms. Если реплики короткие и чёткие («да», «нет») → снизить до 200ms. Состояние `client_speech_pattern` в call state.
- **Gain:** персонализация под конкретного клиента. Для болтливых клиентов больше не режем паузы в середине мысли. Для лаконичных — быстрее отвечаем.
- **Effort:** 1 день. Простая скользящая статистика по 3 последним turns.
- **Риски:** лёгкое усложнение логики. Метрика для a/b тест — latency и "Простите, повторите?" rate.
- **Приоритет:** **P2**
- **Источники:** [AssemblyAI turn detection](https://www.assemblyai.com/blog/turn-detection-endpointing-voice-agent)

---

## Топ-5 по gain/effort

| # | Идея | Gain | Effort | Rationale |
|---|------|------|--------|-----------|
| 1 | **Silero VAD (#4)** | -100-150ms + убирает мусор STT | 0.5 дня | Самый быстрый win. Drop-in замена. Нулевой риск. |
| 2 | **Yandex STT v3 gRPC streaming (#1)** | -150-300ms | 1-2 дня | Убирает REST round-trip и VAD таймаут. Фундамент для #3 и #16. |
| 3 | **Sentence-level LLM streaming + TTS pipelining (#3)** | -200-350ms медиана | 2 дня | Самый большой рычаг. Требует #2 для полной выгоды. |
| 4 | **TTS cache + backchannel fillers (#6+#7)** | перцептивная пауза → 0ms | 1.5 дня | Кардинально меняет UX, минимум кода. |
| 5 | **Per-turn JSON metrics (#15)** | observability | 1 день | Нужен ДО остальных работ — чтобы мерить effect. |

**Суммарный эффект топ-5:** с 860ms median user-perceived pause → ожидаемо **300-450ms** + маскировка через filler до <100ms субъективной. Суммарный effort ~7 дней чистой работы.

---

## Что делают лучшие в мире

### Vapi (The Open Orchestrator)
Абстрактный фреймворк для сборки стека ASR+LLM+TTS. Developer управляет выбором каждого компонента. Streaming media pipeline с поддержкой barge-in, prompt injection, call transfer через exposed events. Архитектурно — close к тому что уже есть у Sofia: proxy-подобный оркестратор между Asterisk и AI-провайдерами. Что заимствовать: **session events model** (call_started, user_started_speaking, agent_started_speaking, tool_called) — полезно для observability (#15) и UI-отладки.
[Vapi speech config](https://docs.vapi.ai/customization/speech-configuration)

### Retell AI (The Closed Garden)
Закрытая proprietary система. Ключевая фича — **Turn Taking Engine**: proprietary tuning LLM wrapper чтобы barge-in обрабатывался <700ms sub-instant. Бьёт почти всех в 2026. Как достигается — не раскрывают, но по сигналам: (а) не отменяют TTS а fade-out с crossfade 50ms, (б) держат параллельный "speculative listen" LLM который параллельно с TTS проверяет нужно ли продолжать. Что заимствовать для Sofia: **fade-out TTS вместо hard cancel** — сейчас в `_speak` при `cancel_playback=True` делается `break` → резкий обрыв. Добавить плавный 30-50ms fade → звучит естественнее.
[Retell vs Vapi 2026](https://ranksquire.com/2026/01/31/retell-ai-vs-vapi-review/), [Retell AI Vapi review](https://www.retellai.com/blog/vapi-ai-review)

### LiveKit Agents
Open-source framework (SDK на Python/JS). Две уникальные фичи: (1) **Turn Detector transformer** — opensource 135M трансформер который предсказывает EOU по семантике; (2) **prewarm hooks** для LLM/STT/TTS чтобы убрать TLS-setup latency. Архитектура — processor pipeline (похожа на Pipecat): каждый блок передаёт frames. Что заимствовать: **prewarm connections (#8)** + turn detector (#5) — оба open для интеграции, русский требует доработки но модель уже published.
[LiveKit blog turn detection](https://blog.livekit.io/using-a-transformer-to-improve-end-of-turn-detection), [LiveKit docs](https://docs.livekit.io/agents/multimodality/audio/)

### Pipecat (open-source, нейтральный)
Процессорный фреймворк с готовыми интеграциями (Deepgram, Whisper, Cartesia, ElevenLabs, Yandex). Что заимствовать: **SileroVADAnalyzer** (проверенная ONNX интеграция, #4) + **TTS cache mixin** (#7). Для Sofia прямой switch на Pipecat не оправдан — текущий код работает и заточен под AudioSocket/Asterisk/Телфин. Но отдельные модули (SileroVADAnalyzer, TTS cache) можно скопировать/переиспользовать.
[Pipecat repo](https://github.com/pipecat-ai/pipecat), [Pipecat SileroVAD](https://docs.pipecat.ai/server/utilities/audio/silero-vad-analyzer)

### ElevenLabs Conversational (vs Cartesia)
Их уникальное — **очень низкий TTS TTFB (~75-150ms)** благодаря GPU keepalive (предотвращают даунклок) и MP3 streaming с самого первого кадра. Также есть filler injection («one moment please») встроенно. Что заимствовать: (а) подход «не останавливать GPU» — для Yandex не актуально (cloud), (б) **концепция filler phrases на уровне framework** (#6) — ElevenLabs их называет "audio interjections" и они pre-generated.

---

## Что готового есть в России

### Yandex SpeechKit — primary pick, уже используется
- **STT**: v1 REST (сейчас) и v3 gRPC streaming. Модель `general:rc` улучшается каждый месяц, поддержка partial results, REAL_TIME режим. Серверы в РФ (Москва, Владимир) → 2-5ms network latency. Цена ~$0.008/мин.
- **TTS**: v1 REST (сейчас) и v3 gRPC streaming. Голоса: alena, jane, omazh (ru female), filipp, zahar, ermil (ru male). Лимит v3: 250 chars / 24 sec на request. Поддержка SSML (`<break>`, `<prosody>`, `<emphasis>`, ударения через `+`). Цена ~$3-5/1M chars.
- **LLM (YandexGPT 5 Pro)**: OpenAI-compatible API (через AI Studio), поддержка streaming + tool calling + structured output. TTFT ~300-600ms. Цена ~$0.5-2/1M tokens. Open-source версия **YandexGPT 5 Lite 8B** (MIT-like license) для self-hosted.
- **Плюсы:** лучшее качество русского, один провайдер всего стека, РФ-серверы, дёшево. **Минусы:** зависимость от Yandex Cloud. Для Sofia — оптимальный primary.

### Sber SaluteSpeech
- **STT**: gRPC streaming + REST, поддержка русского + английского + казахского. Automatic endpointing, intermediate results. Серверы в РФ. Цена ~$0.01/мин.
- **TTS**: gRPC streaming synthesis. Голоса: Kira, Natalia, Taras. Используется BERT pre-trained на русском для prosody. Цена ~$10/1M chars.
- **On-premise версия** доступна (gRPC channel, инсталлируется у клиента).
- **Используем как fallback к Yandex** если Yandex API падает.

### Tinkoff VoiceKit
- **STT gRPC streaming** (endpoint `api.tinkoff.ai:443`), LINEAR16 / Opus-in-Protobuf. Модель `stream-enhanced-ru-RU` оптимизирована под телефонию.
- **Готовый Asterisk модуль**: `Tinkoff/asterisk-voicekit-modules` (C++ native, non-blocking). Это интересный трек — можно использовать как альтернативу AudioSocket + Python STT.

### T-one (opensource, Tinkoff VoiceKit team)
- **Self-hosted streaming ASR**, Apache 2.0, Conformer, 300ms chunks. Для русской телефонии: WER 6.20% vs Yandex ~9-11%. Docker deploy.
- **Производительность**: H100 GPU = 57344 rps. CPU — медленнее, но применимо.

### GigaAM v3 (Sber opensource)
- **Self-hosted ASR**, MIT license. 220-240M params. SOTA на русском (win vs Whisper-large-v3). ONNX/TRT export + Triton deploy. Native punctuation + normalization.

### Silero TTS v5 (opensource)
- CPU-only TTS, MIT license. MOS 4.18-4.54. Русский: `v5_ru` с автоматическим ударением. Хороший fallback к Yandex TTS.

### Сводная таблица

| Сервис | STT | TTS | LLM | РФ-серверы | Streaming gRPC | Opensource | Цена/мин |
|--------|-----|-----|-----|------------|----------------|-----------|----------|
| Yandex SpeechKit + YandexGPT 5 | Отлично | Отлично | Хорошо | Да | Оба | Нет | $0.008 STT |
| Sber SaluteSpeech + GigaChat | Отлично | Хорошо | Хорошо | Да | Оба | GigaChat Lite | $0.01 STT |
| Tinkoff VoiceKit | Отлично (тел.) | Хорошо | Нет | Да | Да | Клиент да | ~$0.008 |
| T-one (Tinkoff OSS) | SOTA телефония | Нет | Нет | self-host | Да | MIT | Free |
| GigaAM v3 (Sber OSS) | SOTA | Нет | Нет | self-host | Да | MIT | Free |
| Silero | Нет | Хорошо (CPU) | Нет | self-host | No | Да | Free |

---

## Рекомендованный roadmap

Целевое сокращение медианного user-perceived pause: **860ms → 300-400ms + субъективно <100ms через filler маскирование.**

### Шаг 0 (0.5-1 день): метрики ДО оптимизации
Реализовать идею #15 — JSONL per-turn metrics. Запустить на 2-3 дня в проде, собрать baseline: p50/p95/p99 по stt_ms, llm_ms, tts_first_byte_ms, total_ms, + процент barge-in, + частота "Простите, повторите?". Без этого каждая следующая оптимизация — на веру.

### Шаг 1 (1 день): быстрые win'ы
- #4 Silero VAD — 0.5 дня
- #7 TTS cache для canonical RIZALTA phrases — 0.5 дня
- #8 Yandex connection prewarm (singleton http/grpc client) — 0.5 дня

Ожидаемый gain: -100-200ms latency + -50-100ms на keepalive + cache hit 0ms на canonical питче.

### Шаг 2 (2 дня): streaming STT
- #1 Yandex SpeechKit v3 gRPC streaming STT (REST → gRPC, partial results, EOU server-side).

Ожидаемый gain: -150-300ms latency, лучшее EOU, меньше false-cut фраз.

### Шаг 3 (2 дня): streaming LLM + sentence-level TTS
- #3 Sentence-level LLM streaming + TTS pipelining.
- #2 Yandex TTS v3 gRPC streaming.

Ожидаемый gain: -200-350ms latency на реплики >1 предложения.

### Шаг 4 (1 день): perceived-latency маскировка
- #6 Backchannel fillers с intent-классификатором.

Ожидаемый gain: субъективная пауза → <100ms.

### Шаг 5 (параллельный research track, 3-4 дня)
- #13 RUAccent + SSML tuning для RIZALTA-терминов.
- #12 Few-shot промпт compaction.
- #5 LiveKit EOU semantic turn detector (shadow mode).

### Backlog (P2/P3)
- #9 Custom STT vocabulary (когда появится data 100+ звонков).
- #10 Echo cancellation (если barge-in всё ещё проблемен после Silero).
- #11 YandexGPT function calling (когда промпт стабилизируется).
- #16 Speculative generation.
- #17 T-one / #18 GigaAM (если решим self-hosted и будет GPU).
- #19 Jitter buffer.
- #20 Adaptive silence threshold.

---

## Ключевые наблюдения по текущему коду

- **`voice_asterisk.py:125-162`** — `transcribe_audio` синхронный блокирующий REST. Идея #1 переписывает на async gRPC stream.
- **`voice_asterisk.py:190-239`** — `synthesize_tts_yandex` аналогично синхронный REST, один `response.content`. Идея #2.
- **`core/pipeline.py:870-904`** — `full_text = resp.choices[0].message.content` — блокирующий wait до конца ответа. Идея #3.
- **`voice_asterisk.py:534-576`** — energy VAD threshold 200. Идея #4: заменить на Silero VAD score > 0.5.
- **`voice_asterisk.py:66` `BARGE_IN_COOLDOWN = 0.5`** — избыточный cooldown из-за отсутствия AEC. Идея #10 снижает до 0.1-0.15.
- **`voice_asterisk.py:522-527`** — cache механизм для greeting уже есть. Идея #7 расширяет на canonical phrases.
