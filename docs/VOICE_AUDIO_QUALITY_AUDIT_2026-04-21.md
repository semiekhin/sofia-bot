# Voice Audio Quality Audit — 2026-04-21

Read-only аудит голосового pipeline на предмет источников «склеек» (шероховатость на стыках слогов). Код не изменён.

---

## Слой 1 — TTS синтез (Yandex API)

**Вердикт: SUSPECT**

**Файл:** `voice_asterisk.py:312-361` (`synthesize_tts_yandex()`)

Параметры запроса к Yandex TTS REST v1:
| Параметр | Значение | Строка |
|----------|----------|--------|
| format | lpcm | :330 |
| sampleRateHertz | **8000** | :331 |
| voice | alena | :328 (.env) |
| emotion | neutral | :329 (.env) |
| speed | **1.1** | :116, :329 |

Текст отправляется целиком одним запросом (без разбиения на чанки). SSML `<break time="300ms"/>` вставляется между предложениями (до 2 штук, `add_ssml_breaks()` :292-309).

### Гипотезы:

**1a. Нативный 8kHz синтез (PRIMARY SUSPECT)**
Yandex TTS REST v1 принимает `sampleRateHertz` из набора {8000, 16000, 48000}. При запросе 8kHz сервер может использовать:
- Нативный 8kHz вокодер (ниже качество, грубее фонемные переходы)
- Или синтез на 48kHz → внутренний даунсемплинг (качество зависит от фильтра)

Мы не знаем какой путь выбирает Yandex, но **DEV-стек (yandex_tts.py для Pipecat) запрашивает 48kHz** (`YANDEX_SAMPLE_RATE = 48000`), а VPS-стек — 8kHz. Если артефакты воспроизводятся только в Asterisk-звонках и отсутствуют в Pipecat — это улика в пользу 8kHz-синтеза как источника.

**1b. Speed 1.1x**
Ускорение синтеза на 10% может создавать микро-артефакты на стыках фонем (pitch-shift + time-stretch). При 8kHz Найквист-частота всего 4kHz — высокочастотные детали переходов между звуками обрезаны, шероховатость заметнее.

---

## Слой 2 — PCM chunking и отправка

**Вердикт: CLEAN**

**Файл:** `voice_asterisk.py:1046-1139` (`_speak()`) и `voice_asterisk.py:1003-1044` (`_speak_pcm()`)

| Параметр | Значение | Строка |
|----------|----------|--------|
| frame_size | 320 bytes (20ms @ 8kHz slin16) | :1060, :1007 |
| sleep _speak | 0.019s | :1090 |
| sleep _speak_pcm | 0.020s | :1032 |
| last frame padding | zero-pad до 320 bytes | :1082, :1022 |

Механика:
1. PCM буфер от TTS нарезается по 320 байт
2. Каждый фрейм отправляется через `_send_audio()` (:1189-1198) → `struct.pack(">BH", audio_type, len(audio_data))` + payload
3. Последний фрейм: если < 320 байт → `frame + b"\x00" * (frame_size - len(frame))`

Zero-padding последнего фрейма создаёт щелчок только в самом конце utterance (переход PCM → тишина). Это НЕ «склейки внутри слов» — артефакт на границе речи, не между слогами.

Pacing 0.019/0.020 — после фикса 20.04 (коммит `8f3eeaf0`) dropouts устранены (correlation 0.987). Jitter event loop не создаёт перцептивных артефактов при текущей нагрузке (load 0.07).

---

## Слой 3 — Multi-chunk TTS (склейка нескольких TTS-вызовов)

**Вердикт: CLEAN (отсутствует)**

**Ключевой ответ:** voice_asterisk.py **НЕ разбивает текст на части** для TTS. Весь очищенный текст идёт одним запросом в `synthesize_tts_yandex()`.

Логика с чанками по 250 символов (`_split_text()`, `YANDEX_MAX_CHARS = 250`) существует **только в `yandex_tts.py`** — это модуль для Pipecat/Daily (voice_pipecat_daily.py), **не для Asterisk-стека**.

В Asterisk-стеке:
```
_speak() → sanitize_for_tts() → add_ssml_breaks() → synthesize_tts_yandex(clean_text)
```
Один вызов → один непрерывный PCM буфер → нарезка на фреймы.

**Следствие:** артефакты «склейки» НЕ являются результатом конкатенации нескольких TTS-ответов. PCM буфер непрерывен внутри каждого ответа.

---

## Слой 4 — Event loop и параллельная нагрузка

**Вердикт: CLEAN**

**Файл:** `voice_asterisk.py` — весь файл, single asyncio event loop.

Корутины, работающие параллельно с `_speak`:
| Корутина | Файл:строка | Влияние |
|----------|-------------|---------|
| `_stream_audio_to_grpc` | :765-785 | gRPC send_audio — I/O bound, не блокирует |
| `_detect_barge_in` | :849-897 | Silero VAD inference ~1-2ms, GIL released by onnxruntime |
| `_on_grpc_partial/final/eou` | :787-838 | Callbacks — filtered by `_tts_playing` flag |
| TCP read loop (`run`) | :572-596 | `readexactly(3)` + `readexactly(msg_len)` — I/O |

GIL contention минимальна:
- Silero ONNX: `intra_op_num_threads=1`, `inter_op_num_threads=1` (:186-187), GIL released during `session.run()`
- numpy: releases GIL for C-level operations
- httpx: async I/O, no GIL

Sleep 0.019s в `_speak` даёт ~1ms headroom для event loop scheduling. При load average 0.07 на 2 vCPU — scheduling jitter negligible.

---

## Слой 5 — Asterisk кодеки и транскодирование

**Вердикт: SUSPECT**

**Файлы:** `/etc/asterisk/pjsip.conf`, `/etc/asterisk/rtp.conf`

### Кодеки:
```
pjsip.conf: disallow=all / allow=alaw / allow=ulaw
Endpoint allow: (alaw|ulaw)
```

### Путь аудио и транскодирования:

```
Sofia voice_asterisk.py
  → slin8 (8kHz 16-bit PCM, тип 0x10) 
    → [AudioSocket app] 
      → Asterisk internal (slin8)
        → [transcoding: slin8 → alaw] 
          → RTP/SIP (G.711 a-law, 64kbit/s)
            → Telphin SIP proxy
              → клиентский телефон
```

**Количество транскодирований: 1** (slin8 → alaw). Это стандартный минимум для SIP-телефонии.

Translation table показывает slin8 → alaw: 6000μs/sec (6ms на секунду аудио) — быстро, встроенный кодек.

### Гипотеза:

alaw encoding (8-bit μ/A-law companding) — lossy, SNR ~48dB. Сам по себе это стандарт телефонии и НЕ создаёт «склейки». Но в комбинации с 8kHz TTS (слой 1) — если TTS уже генерирует грубые переходы на 4kHz Найквисте, alaw quantization noise может их усилить.

### rtp.conf:
- `rtpstart=10000`, `rtpend=20000` — стандартный диапазон
- **Нет настроек jitter buffer** — используется Asterisk default (adaptive jitter buffer включён по умолчанию для res_rtp_asterisk)
- `strictrtp=yes` (default) — OK, защита от RTP injection

---

## Слой 6 — MixMonitor (запись)

**Вердикт: CLEAN**

**Файл:** `/etc/asterisk/extensions.conf`

Dialplan порядок:
```
Answer() → Wait(0.5) → Set(CALL_UUID) → mkdir → MixMonitor(...) → AudioSocket(...)
```

MixMonitor запускается **ДО** AudioSocket. Пишет в WAV (PCM, без сжатия). Работает в отдельном thread Asterisk, не в audio path. Запись происходит **после** bridging — MixMonitor подписывается на audio frames, но не блокирует их доставку.

Влияние на latency основного потока: нет (отдельный thread, write buffered).

---

## Слой 7 — Cached greeting

**Вердикт: CLEAN (minor)**

**Файлы:** `/opt/sofia-voice/greeting_rizalta.pcm`, `/opt/sofia-voice/greeting_atlantis.pcm`

| Файл | Размер | mod 320 | Фреймы | Длительность |
|------|--------|---------|--------|-------------|
| greeting_rizalta.pcm | 198318 | **238** | 619 + хвост | 12.39s |
| greeting_atlantis.pcm | 95036 | **316** | 296 + хвост | 5.94s |

Оба файла **НЕ кратны 320 байтам**. Последний фрейм zero-padded (`_speak_pcm` :1021-1022). Это создаёт микро-щелчок в самом конце greeting (238→320 = 82 байта тишины в rizalta, 316→320 = 4 байта в atlantis).

**Не является причиной «склеек внутри слов»** — артефакт только в последнем фрейме. Greeting генерирован одним вызовом TTS → внутренне непрерывен.

---

## Слой 8 — Общая картина

**Вердикт: INFO**

### Ресурсы VPS:
| Параметр | Значение |
|----------|----------|
| vCPU | 2 |
| RAM | 3.8 GB (used 529 MB) |
| Load | 0.07 |
| Uptime | 9h 21m |
| sofia-voice CPU | 688ms total |
| sofia-voice RAM | 62.4 MB |

Ресурсов более чем достаточно. Нет конкуренции за CPU/RAM.

### .env (voice-related):
| Ключ | Значение |
|------|----------|
| VOICE_PROVIDER | yandex |
| VOICE_TTS_PROVIDER | yandex |
| YANDEX_TTS_VOICE | alena |
| YANDEX_TTS_EMOTION | neutral |
| YANDEX_TTS_SPEED | 1.1 (default в коде :116) |
| STT_MODE | grpc |
| YANDEX_STT_EOU_MODE | high |
| YANDEX_MAX_PAUSE_HINT_MS | 700 |
| VOICE_VAD_PROVIDER | silero |
| AUTO_HANGUP_ENABLED | true |
| VOICE_PROMPT_MODE | rizalta |

---

## Сводная таблица

| # | Слой | Вердикт | Ключевая находка |
|---|------|---------|-----------------|
| 1 | TTS синтез (Yandex) | **SUSPECT** | 8kHz нативный запрос (vs 48kHz в Pipecat). Speed 1.1x. Вероятный основной источник «склеек» |
| 2 | PCM chunking | CLEAN | Zero-pad последнего фрейма — только на конце utterance, не между слогами |
| 3 | Multi-chunk TTS | CLEAN | Текст идёт одним запросом. Конкатенации PCM буферов нет |
| 4 | Event loop | CLEAN | Jitter negligible, GIL contention minimal, load 0.07 |
| 5 | Asterisk кодеки | **SUSPECT** | 1x transcoding slin8→alaw (стандарт). Может усиливать артефакты из слоя 1 |
| 6 | MixMonitor | CLEAN | Отдельный thread, не влияет на audio path |
| 7 | Cached greeting | CLEAN | mod320≠0 → micro-click на конце, не между слогами |
| 8 | Общая картина | CLEAN | Ресурсов достаточно, конфигурация корректна |

---

## Главная гипотеза

**«Склейки внутри слов» — артефакт Yandex TTS при синтезе напрямую в 8kHz** (слой 1).

Цепочка аргументов:
1. Multi-chunk конкатенации нет (слой 3 исключён)
2. Pacing-dropouts устранены (слой 2 исключён, correlation 0.987)
3. Event loop jitter negligible (слой 4 исключён)
4. Единственный слой, создающий новый аудио-контент — TTS (слой 1)
5. TTS запрашивает **8kHz напрямую**, при этом Pipecat-стек запрашивает **48kHz** — разные пути синтеза внутри Yandex

**Эксперимент для верификации:** запросить TTS на 48kHz → даунсемплировать до 8kHz с помощью soxr/ffmpeg → сравнить с текущим 8kHz-запросом. Если артефакты исчезают — подтверждение гипотезы. Это и есть те A/B файлы на Mac (`call_8ad55f5b_reply{5,8}_{baseline,48k,jane}.wav`).

**Вторичный фактор:** speed=1.1x может усиливать артефакты (ускорение → stretching фонемных переходов).

---

## Обнаруженные побочные проблемы

1. **greeting PCM не кратны 320 байтам** — rizalta: 198318 mod 320 = 238, atlantis: 95036 mod 320 = 316. Не влияет на «склейки», но создаёт микро-щелчок в конце greeting. Фикс тривиальный: обрезать или дополнить при генерации.

2. **YANDEX_TTS_SPEED не в .env** — hardcoded default 1.1 в коде (:116). Для A/B тестов speed нужно будет вынести в .env (или менять в коде). Это не баг, но отмечено для удобства экспериментов.

3. **add_ssml_breaks() добавляет SSML теги для ElevenLabs** (комментарий :293 "ElevenLabs Flash v2.5 artifacts") **но используется и для Yandex TTS**. Yandex REST v1 поддерживает `<break>` в `<speak>` wrapper (:334-335), но поведение может отличаться от ElevenLabs. Не является вероятным источником артефактов, но стоит проверить — отключить breaks для Yandex и сравнить.
