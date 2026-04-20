# Voice Tech Stack — полный технический путь байта звука

Исчерпывающая техническая документация голосового канала Sofia от SIP-сигнала на стороне оператора до звука в трубке клиента и обратно. Цель — single source of truth для поиска места проглатывания слогов и для онбординга нового инженера.

**Целевая аудитория:** product owner + backend-инженер с техническим пониманием.
**Связанные документы:** `docs/VOICE_ARCHITECTURE.md` (краткий hot-reference), `docs/LESSONS_LEARNED.md` (прецедентные уроки). Этот документ **углубляет**, не дублирует.

**Дата:** 2026-04-20. Отражает состояние VPS sofia-voice после апгрейда 1→2 vCPU (19.04 вечер) и инструментации `_speak` per-chunk timing (20.04 ночь).

---

## Раздел 1. Общий обзор — путь одного разговорного turn'а

```
═══════════════════════════════════════════════════════════════════════════════
                    ВХОДЯЩИЙ ЗВОНОК — КЛИЕНТ → SOFIA
═══════════════════════════════════════════════════════════════════════════════

  Клиент (мобильный PSTN)
      │
      │ набирает +79310091644
      ▼
  ┌──────────────────────────────────────────────────────────────────────┐
  │  Telfin (оператор IP-телефонии, sipproxy.telphin.ru:5068)            │
  │  Транскодирует PSTN → SIP, шлёт INVITE на наш VPS                    │
  └──────────────────────────────────────────────────────────────────────┘
      │ SIP INVITE с IP 46.229.221.93 → 185.207.66.201:5090/udp
      │ RTP G.711 alaw/ulaw 20ms пакеты, порты 10000-20000/udp
      ▼
  ┌──────────── VPS 185.207.66.201 (Timeweb, 2 vCPU 4 GB) ───────────────┐
  │                                                                         │
  │  UFW firewall: whitelist 46.229.221.93:5090/udp + 10000-20000/udp      │
  │      │                                                                 │
  │      ▼                                                                 │
  │  Asterisk 20 PJSIP endpoint [telphin-endpoint] context=from-telphin    │
  │      │                                                                 │
  │      ▼ dialplan [from-telphin]:                                        │
  │         Answer → Wait(0.5) → Set(CALL_UUID) → MixMonitor(WAV)          │
  │         → AudioSocket(UUID, 127.0.0.1:9090) → Hangup()                 │
  │      │                                                                 │
  │      │ AudioSocket TCP localhost:9090 — binary protocol                │
  │      │ [1B type][2B len BE][payload], frame 320B = 20ms slin16 8kHz    │
  │      ▼                                                                 │
  │  voice_asterisk.py (systemd unit sofia-voice.service)                  │
  │      │                                                                 │
  │      ├─ UUID handshake → call_id_to_user_id() → StateManager init     │
  │      │                                                                 │
  │      ├─ _send_greeting() → _speak_pcm(greeting_rizalta.pcm, 12.4s)    │
  │      │                                                                 │
  │      ├─ ПАРАЛЛЕЛЬНО: _open_grpc_stream() (TLS handshake)              │
  │      │                                                                 │
  │      │     ┌─ Клиент говорит → 320B frame каждые 20ms ────────────┐   │
  │      │     │                                                       │   │
  │      │     ▼                                                       │   │
  │      │   Silero VAD v4 ONNX (барge-in detection при _tts_playing) │   │
  │      │     │                                                       │   │
  │      │     ▼                                                       │   │
  │      │   yandex_stt_grpc.py: LINEAR16_PCM 8kHz → gRPC stream      │   │
  │      │     стримит на stt.api.cloud.yandex.net:443                │   │
  │      │     partial → final → eou_update                           │   │
  │      │     EOU sensitivity=HIGH, max_pause_hint=700ms             │   │
  │      │     └─────────────────────────────────────────────────────┘   │
  │      │                                                                 │
  │      ▼ _on_grpc_eou → _process_turn(text_override=text)               │
  │   core/pipeline.py:stream_voice_response()                             │
  │      │   POST YandexGPT 5 Pro (AI Studio OpenAI-compat endpoint)      │
  │      │   model gpt://b1.../yandexgpt/latest, max_tokens=400, no RAG   │
  │      ▼ response text                                                   │
  │   anti-hallucination regex + sanitize_for_tts + add_ssml_breaks       │
  │      │                                                                 │
  │      ▼                                                                 │
  │   synthesize_tts_yandex(): POST tts.api.cloud.yandex.net              │
  │      voice=alena, speed=1.1, lpcm 8kHz → raw PCM bytes                │
  │      ▼                                                                 │
  │   _speak(): pcm_data.chunks(320B)                                     │
  │      loop: _send_audio(chunk) + asyncio.sleep(0.019)                  │
  │      ▼ AudioSocket 0x10 frame → Asterisk                              │
  │   Asterisk packs slin16 → G.711 alaw/ulaw → RTP                       │
  │      ▼                                                                 │
  │  Asterisk → Telfin через UDP (RTP port range 10000-20000)             │
  └───────────────────────────────────────────────────────────────────────┘
      │
      ▼ Telfin транскодирует SIP/RTP → PSTN
  Клиент слышит Sofia
```

---

## Раздел 2. Пошаговый путь входящего звонка

### Шаг 1. Клиент набирает +79310091644 → Telfin

| Параметр | Значение |
|----------|----------|
| Оператор | Telfin |
| SIP-proxy | `sipproxy.telphin.ru:5068/udp` |
| Аккаунт | `15400*101` |
| Номер | `+79310091644` |
| IP Telfin | `46.229.221.93` (единственный в UFW whitelist, также `213.170.84.105` добавлен для RTP) |
| Маршрут | PSTN от оператора клиента → межоператорский транзит → Telfin → SIP INVITE в VPS |

Telfin **блокирует SIP-трафик по IP origin** — запросы с нашего `185.207.66.201` проходят только потому что этот IP в их whitelist. Без whitelist: `403 Forbidden Ip`. Это одна из причин двухсерверной архитектуры (VPS отдельно от main server).

### Шаг 2. SIP INVITE доходит до Asterisk

- Источник: `sipproxy.telphin.ru:5068` (UDP)
- Назначение: `185.207.66.201:5090/udp` (нестандартный порт; 5060 и 4569 закрыты для блокировки SIP-сканеров)
- UFW правило: `ufw allow from 46.229.221.93 to any port 5090 proto udp`

Asterisk endpoint `[telphin-endpoint]` (см. `/etc/asterisk/pjsip.conf:37-53`):
```ini
type=endpoint
transport=transport-udp
context=from-telphin
disallow=all
allow=alaw
allow=ulaw              ; G.711 A-law + μ-law — только эти кодеки
outbound_auth=telphin-auth
aors=telphin-aor
from_user=15400*101
from_domain=sipproxy.telphin.ru
rtp_symmetric=yes       ; RTP уходит в тот же IP:port откуда пришёл — нужно за NAT'ом
force_rport=yes         ; SIP ответы отправляются в source port клиента
rewrite_contact=yes     ; Contact header перезаписывается под NAT
direct_media=no         ; Media всегда через Asterisk (нельзя peer-to-peer)
ice_support=no          ; ICE выключен — SIP trunk, не WebRTC
media_encryption=no     ; Нет SRTP/DTLS (Telfin не поддерживает)
```

Identify блок `[telphin-identify]` (строки 56-59): определяет входящий SIP по `match=sipproxy.telphin.ru` — не по учётке, а по IP источника.

### Шаг 3. Asterisk выполняет dialplan `[from-telphin]`

`/etc/asterisk/extensions.conf:8-16`:
```
exten => s,1,NoOp(=== Incoming call: ${CALLERID(num)} ===)
 same => n,Answer()                                    ; 200 OK клиенту
 same => n,Wait(0.5)                                   ; 500ms пауза до первого фрейма
 same => n,Set(CALL_UUID=${SHELL(cat /proc/sys/kernel/random/uuid)})
 same => n,System(mkdir -p /var/lib/asterisk/recordings/${STRFTIME(${EPOCH},,%Y-%m-%d)})
 same => n,MixMonitor(/var/lib/asterisk/recordings/.../${CALL_UUID}.wav)
 same => n,AudioSocket(${CALL_UUID},127.0.0.1:9090)   ; Блокирующий вызов на весь звонок
 same => n,Hangup()
```

- **Answer()** — отправляет SIP `200 OK`, клиент слышит «алло-тишина»
- **Wait(0.5)** — 500ms пауза чтобы медиа-поток установился до Sofia начинает говорить
- **MixMonitor** — параллельно пишет WAV 8kHz mono (оба направления микшированы в один файл). Запись идёт в `/var/lib/asterisk/recordings/<YYYY-MM-DD>/<UUID>.wav`, ротация через cron 03:00 (WAV→Opus 32kbps >72h) и 03:30 (удаление >30 дней)
- **AudioSocket(UUID, 127.0.0.1:9090)** — блокирующий Asterisk application, открывает TCP-соединение на `voice_asterisk.py`, гоняет медиа туда-обратно до Hangup
- **Hangup()** — выполняется когда AudioSocket вернёт управление (либо peer закрыл, либо Asterisk timeout)

### Шаг 4. AudioSocket TCP handshake

`voice_asterisk.py:1265-1268` слушает `127.0.0.1:9090`. Asterisk app открывает TCP-соединение. Используется бинарный фреймовый протокол:

```
Packet format: [1 byte type] [2 bytes length BE] [payload]

AS_TYPE_HANGUP    = 0x00   -- 0-byte payload
AS_TYPE_UUID      = 0x01   -- 16-byte binary UUID
AS_TYPE_AUDIO     = 0x10   -- slin16 8kHz (320 bytes = 20ms)
AS_TYPE_AUDIO_16K = 0x12   -- slin16 16kHz (не используется здесь)
AS_TYPE_ERROR     = 0xFF   -- UTF-8 error text
```

Первый пакет от Asterisk — `AS_TYPE_UUID` с 16-байтным бинарным UUID (тем что `Set(CALL_UUID=...)` сгенерил). `voice_asterisk.py:599-609` парсит UUID, вычисляет `user_id`:

```python
user_id = 9_500_000 + (int(md5(uuid)[:8], 16) % 1_000_000)
# пример: UUID 8ad55f5b... → user_id 9718799
```

Дальше каждые ~20ms Asterisk шлёт `AS_TYPE_AUDIO` с 320-байтовыми фреймами (slin16 = signed linear 16-bit little-endian, 8000 samples/sec, mono → 16000 bytes/s → 320 bytes per 20ms). Обратно `voice_asterisk.py` шлёт такие же пакеты.

### Шаг 5. voice_asterisk.py получает аудио от клиента

`AudioSocketCall.run()` (строка 572) читает пакеты в цикле. Каждый audio-пакет → `_handle_packet` → dispatch:

```python
if not self._is_responding:
    await self._process_audio(payload)   # normal: VAD + STT
elif self._tts_playing:
    await self._detect_barge_in(payload) # Sofia говорит — ищем прерывание
# else: ignore (LLM/STT фаза — клиент договаривает свою реплику)
```

`_process_audio` — это method pointer. При `STT_MODE=grpc` (текущий) указывает на `_stream_audio_to_grpc`. При `STT_MODE=rest` — на `_process_audio_vad` (accumulate → REST STT). Bifurcate через `AudioSocketCall.__init__:567-570`.

---

## Раздел 3. Пошаговый путь обработки речи клиента (VAD → STT)

### Шаг 6. Silero VAD

Используется двумя независимыми потребителями:
1. **Barge-in detection** когда Sofia говорит (`_tts_playing=True`)
2. **EOU-резерв** для REST-ветки (при gRPC не используется — Yandex сам определяет EOU)

Параметры модели (`voice_asterisk.py:171-199`):

| Параметр | Значение |
|----------|----------|
| Модель | Silero VAD **v4** (8kHz) |
| Файл | `/opt/sofia-voice/silero_vad.onnx` |
| Размер | 1.8 MB |
| md5 | `03da8de2fec4108a089b39f1b4abefef` |
| Runtime | `onnxruntime 1.24.4`, CPU provider |
| Threads | `intra_op_num_threads=1`, `inter_op_num_threads=1` (один GIL thread) |
| Chunk size | 256 samples (32ms) = 512 bytes int16 |
| LSTM state | `h`, `c` shape `[2, 1, 64]` float32 — сохраняется между чанками per-call |
| Threshold (normal) | 0.5 (speech probability) |
| Threshold (barge-in) | 0.5 (понижено с 0.6 17.04 — barge-in не пробивался на TTS-echo mix) |

**Важное:** фрейм AudioSocket = 320 байт (20ms), а Silero ждёт 512 байт (32ms). Отсюда **chunking mismatch** — `SileroVAD.is_speech()` накапливает байты в буфер и запускает инференс только когда накопилось ≥512. На фрейме AudioSocket получаем True/False, но Silero может обработать 0, 1 или 2 чанка за вызов. Это причина `BARGE_IN_SILENCE_RESET=0.3s` — без него Silero «мигает» True/False на непрерывной речи и barge-in buffer чистится преждевременно.

v5 **не подошла** для 8kHz (benchmark: 13% recall vs 73% у v4). v5 сохранена как `silero_vad_v5.onnx.legacy`.

### Шаг 7. Отправка в Yandex STT v3 gRPC streaming

Реализация: `yandex_stt_grpc.py`.

| Параметр | Значение | Источник |
|----------|----------|----------|
| Endpoint | `stt.api.cloud.yandex.net:443` (TLS gRPC) | `yandex_stt_grpc.py:34` |
| Модель | `general:rc` (release candidate) | `.env` default |
| Язык | `ru-RU` (WHITELIST restriction) | |
| Audio format | `LINEAR16_PCM`, `sample_rate_hertz=8000`, mono | |
| Audio processing | `REAL_TIME` | `stt_pb2.RecognitionModelOptions.REAL_TIME` |
| EOU classifier | `DefaultEouClassifier`, sensitivity `HIGH` | `YANDEX_STT_EOU_MODE=high` |
| Max pause hint | `700ms` (Phase 1 VLAT-07, 18.04) | `YANDEX_MAX_PAUSE_HINT_MS=700` |
| Auth | `Api-Key` в metadata | |
| TLS handshake | Запускается в параллель с greeting (12.4s кэшированных PCM — достаточно времени) | `voice_asterisk.py:616-617` |

Поток:
1. `start()` открывает gRPC-канал, отправляет `session_options` (одно protobuf-сообщение)
2. Все аудио-фреймы от AudioSocket идут в `asyncio.Queue` → `_request_iterator` → gRPC stream
3. `_receive_loop` диспатчит события:
   - `partial` → `_on_grpc_partial` (logging only, решения не принимаются)
   - `final` → `_on_grpc_final` (копится в `_grpc_final_buffer`)
   - `eou_update` → `_on_grpc_eou` (триггерит turn)

### Шаг 8. Yandex вернул EOU — запускаем turn

`_on_grpc_eou` (`voice_asterisk.py:812`):
1. Guard: `if _tts_playing and not _cancel_playback: return` (TTS-echo protection)
2. Guard: `if not _grpc_final_buffer or _is_responding: return`
3. Лог: `🗣️ STT (grpc): "<text>" (<stream_dur>ms, N partials, M finals)`
4. Reset per-turn counters
5. `asyncio.create_task(self._process_turn(None, text_override=text))`

**EOU instrumentation** (добавлена 18.04, `d2f875d1`): каждое `eou_update` пишет `EOU_WAIT uuid=... turn=N eou_wait_ms=M text_len=K`. Phantom EOU rate ~54% — Yandex дублирует `eou_update` (харamless noise, все идемпотентны через `_grpc_final_buffer` check).

---

## Раздел 4. Пошаговый путь генерации ответа (текст → PCM)

### Шаг 9. Сохранение транскрипта и запуск turn

`_process_turn` (`voice_asterisk.py:899`):
1. `if _is_responding or _closed: return` — re-entrancy guard
2. `_is_responding = True`, reset barge-in state
3. Если `text_override` (gRPC путь) — пропускаем REST STT
4. `logger.info(f'🎤 USER: "{text}"')`
5. `save_message(chat_id, user_id, "user", text)` — запись в SQLite `/opt/sofia-voice/sofia_voice.db`, таблица `messages (chat_id, user_id, role, content, timestamp, stage)`

### Шаг 10. LLM — YandexGPT 5 Pro

`history = get_history(chat_id, limit=20)` — последние 20 сообщений из SQLite.

Вызов: `stream_voice_response()` из `core/pipeline.py`. Детали ядра (`/opt/sofia-voice/core/pipeline.py`):

| Параметр | Значение |
|----------|----------|
| Endpoint | AI Studio OpenAI-compatible (`ya-models.cloud.yandex.net/...` через OpenAI SDK) |
| Модель | `gpt://b1giu7d61rvmondibc51/yandexgpt/latest` |
| max_tokens | 400 (short replies для voice) |
| RAG | ВЫКЛЮЧЕН в voice (скорость > качество) |
| Analyzer (stage/rag_query) | ВЫКЛЮЧЕН в voice |
| Extractor (NLU) | **включен** — rule-based перед LLM (goal/budget/payment_type/meeting_agreed) |
| System prompt | `VOICE_SYSTEM_PROMPT_RIZALTA` v4.2 (18.04) — секции ЧЕЛОВЕЧНОСТЬ / ФАКТЫ-ДОСЛОВНО / МОЖНО ВАРЬИРОВАТЬ, инструкция `[END]` в прощальной реплике |
| Streaming | Да, async chunks |

Turn timing log: `⏱️ Turn timings: STT=Xms, LLM=Yms, TTS=Zms, TOTAL=Wms`.

Типичные цифры (после Phase 1, 18.04):
- **STT stream duration:** ~1036ms median (EOU_WAIT после последней partial-change)
- **LLM:** ~620-640ms median
- **TTS (полный _speak):** зависит от длины ответа — 2-12 секунд wall time для 100-300 символов

### Шаг 11. Пост-обработка ответа LLM

Порядок операций (`core/pipeline.py stream_voice_response`, затем `_speak` в `voice_asterisk.py`):

1. **Anti-hallucination regex** — обрезает ответ на маркерах `Пользователь:` / `Клиент:` / `Ассистент:` (YandexGPT иногда генерирует продолжение диалога)
2. **[END] check** — `answer_text.rstrip().endswith("[END]")` → `state.dialog_finished = True`, маркер убирается из текста (fix 18.04 `19102904` — раньше был substring match, срабатывал на hallucinated tail)
3. В `_speak(text)`:
   - `sanitize_for_tts(text)` — убирает латиницу, URL, email, @mentions
   - `add_ssml_breaks(text)` — вставляет `<break time="300ms"/>` между предложениями (макс 2 break'а на реплику; 300ms integer — Yandex требует integer ms)

### Шаг 12. Yandex TTS REST v1 — синтез речи

`synthesize_tts_yandex(text)` (`voice_asterisk.py:313-362`):

| Параметр | Значение |
|----------|----------|
| Endpoint | `https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize` |
| HTTP method | POST (application/x-www-form-urlencoded) |
| Auth | `Authorization: Api-Key ${YC_API_KEY}` |
| voice | `alena` (default) |
| emotion | `neutral` |
| speed | `1.1` |
| format | `lpcm` |
| sampleRateHertz | `8000` |
| folderId | из env `YC_FOLDER_ID` |
| ssml | `<speak>...</speak>` если в тексте есть `<break`, иначе `text=...` |
| timeout | 10.0s |
| Response | Raw LPCM bytes, signed 16-bit little-endian, mono, 8kHz |

**TTFB (time to first byte):** ~150-185ms медиана. Single POST, весь PCM одним ответом (не streaming).

### Шаг 13. Получение PCM — размеры

Для реплики длиной 100-300 символов Yandex возвращает:
- Минимум: ~32 000 байт (2s audio)
- Типично: ~170 000 байт (10.6s audio)
- Максимум (в последнем звонке): ~204 000 байт (12.75s audio)

Формула: `byte_count / (8000 * 2) = seconds`.

Cached greeting: `greeting_rizalta.pcm` = 198 318 байт = 12.4s (регенерирован 16.04 под RIZALTA v3).

---

## Раздел 5. Пошаговый путь отправки звука клиенту

### Шаг 14. `_speak` — разбиение PCM на чанки

`voice_asterisk.py:1046-1147` (после инструментации 20.04):

```python
frame_size = 320  # 20ms @ 8kHz slin16
offset = 0
speak_t0_ns = time.perf_counter_ns()
chunk_idx = 0
while offset < len(pcm_data):
    if self._closed or self._cancel_playback:
        break
    end = min(offset + frame_size, len(pcm_data))
    frame = pcm_data[offset:end]
    if len(frame) < frame_size:
        frame = frame + b"\x00" * (frame_size - len(frame))  # zero-pad last
    # ... _tts_playing flag ...
    t_before_send_ns = time.perf_counter_ns()
    await self._send_audio(frame, self._audio_type)
    t_after_send_ns = time.perf_counter_ns()
    # ... first_audio_time log ...
    offset += frame_size
    await asyncio.sleep(0.019)       # ← pacing gap (19ms for _speak, 20ms for _speak_pcm)
```

> **Pacing final values (20.04 fix):** `_speak_pcm` уходит `sleep(0.020)` — без параллельной нагрузки greeting попадает в 20ms audio rate идеально. `_speak` уходит `sleep(0.019)` — компенсирует ~1ms event loop overhead от параллельных gRPC STT + Silero inference. Per-chunk wall time в обеих функциях ≈ **20.0ms ровно**. Подробности — раздел 10, пункт «Pacing overflow».

**Критические параметры:**

| Параметр | Значение | Почему |
|----------|----------|--------|
| `frame_size` | 320 bytes | Точно 20ms аудио @ 8kHz slin16 (одно значение в AudioSocket) |
| `asyncio.sleep` | 0.019 в `_speak`, 0.020 в `_speak_pcm` | Pacing gap: цель = 20ms wall per chunk = audio rate. 18ms создавал overflow → Asterisk дропал фреймы (fix 20.04). Асимметрия из-за разного event loop overhead: в `_speak` параллельно идёт gRPC STT + Silero, ~1ms overhead; в `_speak_pcm` нагрузки нет |
| zero-pad last chunk | `\x00` | Если последний чанк <320B, добираем тишиной. **Источник щелчка на границе реплики** |
| `_cancel_playback` | flag | Прерывается мгновенно при barge-in |

**Per-chunk timing data из звонка 20.04 (UUID `8ad55f5b`, 4373 чанков, 11 реплик):**

| Метрика | sleep_overrun_us | send_dur_us |
|---------|-----------------|--------------|
| median | 947 (~1ms) | 75 (~0.08ms) |
| p95 | 2 013 (~2ms) | 194 |
| max | 3 510 (~3.5ms) | 458 |
| >10ms | **0** | 0 |

Вывод первого анализа: inter-chunk jitter стабилен (median ~1ms overrun). Но **систематический сдвиг 18ms vs 20ms audio rate** создавал overflow на 10% — ~1.2s excess за 12s реплики, Asterisk сбрасывал лишние фреймы. Fix 20.04: `_speak` → 0.019, `_speak_pcm` → 0.020. См. раздел 10.

### Шаг 15. `_send_audio` — запись в AudioSocket

`voice_asterisk.py:1213-1222`:
```python
async def _send_audio(self, audio_data: bytes, audio_type: int = AS_TYPE_AUDIO):
    if self._closed:
        return
    try:
        header = struct.pack(">BH", audio_type, len(audio_data))
        self.writer.write(header + audio_data)
        await self.writer.drain()
    except (ConnectionResetError, BrokenPipeError):
        self._closed = True
```

- `writer.write` в asyncio StreamWriter — буферизирует, возвращает мгновенно
- `drain()` — ждёт пока буфер не опустится до low-water mark (backpressure)
- Заголовок 3 байта: `BH` = `uint8 type` + `uint16 len` (big-endian)
- Payload 320 байт → один пакет = 323 байта на localhost TCP
- Time cost: 75μs медиана, макс 458μs — локальный TCP, без копирования

### Шаг 16. AudioSocket получает slin16 на стороне Asterisk

Asterisk app `AudioSocket()` (запущен в Шаге 3) получает `0x10` пакет с 320 байтами slin16. Внутренний формат Asterisk для этого канала — тоже slin16 (после декодирования G.711 входящего). Сконвертированные в slin16 байты уходят в исходящий media pipeline канала.

### Шаг 17. Asterisk кодирует slin16 → G.711

Согласованный кодек (см. PJSIP `allow=alaw` / `allow=ulaw`) — G.711 A-law или μ-law (что договорился в SDP при INVITE). Обычно для России — A-law. 8kHz slin16 → 8kHz G.711 8-bit = **50% компрессия** с минимальными потерями (логарифмическое кодирование амплитуды).

G.711 — lossless для человеческой речи на уровне восприятия, но теоретически отбрасывает ~7 бит квантования. Потенциальное место искажений: переходы между quiet и loud семплами в пределах 20ms пакета. Маловероятный источник «проглатываний».

### Шаг 18. RTP upstream

Кодированные 20ms пакеты идут через UDP в `sipproxy.telphin.ru`:
- Source: `185.207.66.201` порт из диапазона `10000-20000/udp` (см. `/etc/asterisk/rtp.conf`)
- Destination: Telfin RTP port (из SDP negotiation)
- Ptime: 20ms (совпадает с AudioSocket frame size — нет re-packetization)
- Payload type: dynamic (обычно PT=8 для alaw, PT=0 для ulaw)
- Jitter buffer: Asterisk default (adaptive, 40-120ms outbound на нашей стороне)

UFW правило: `ufw allow 10000:20000/udp`. Без этого исходящий RTP ушёл бы, но обратный не пришёл (UFW stateful правила для UDP работают через conntrack).

### Шаг 19. Telfin → PSTN → клиент

Telfin декодирует RTP G.711, транскодирует в PSTN формат оператора клиента (обычно тоже G.711 через SS7 transit). Клиент слышит Sofia.

**Весь путь от `_send_audio` до динамика клиента:** localhost TCP (<1ms) → Asterisk G.711 encode (~0.1ms) → RTP UDP VPS→Telfin (~30-50ms трансатлантический jitter) → Telfin transcode → PSTN (~100-200ms до динамика мобильника). **Итого 130-250ms one-way latency**, видно клиенту как задержка ответа.

---

## Раздел 6. Параллельные процессы (что работает одновременно)

Во время разговора на VPS **одновременно** крутятся:

| # | Процесс | Поток/тип | Нагрузка |
|---|---------|-----------|----------|
| 1 | Asterisk main thread | C, nativethread | Низкая — в основном проксирование медиа |
| 2 | Asterisk MixMonitor | C child thread | I/O на диск ~16 KB/s → `/var/lib/asterisk/recordings/.../<UUID>.wav` |
| 3 | `voice_asterisk.py` main event loop | Python asyncio single thread (GIL) | Основная работа |
| 4 | Silero VAD ONNX inference | synchronous в main loop (одноthreaded ort session) | ~2-5ms per chunk, блокирует loop |
| 5 | YandexSTTStream gRPC channel | grpc.aio thread pool | Continuous stream, TLS overhead |
| 6 | `_stream_audio_to_grpc` for every frame | В main loop (queue put) | Мгновенно |
| 7 | `_detect_barge_in` when `_tts_playing` | В main loop | Silero inference |
| 8 | `_speak` loop | В main loop | 50 iterations/sec для одной реплики |
| 9 | `save_message`/`get_history` | Sync SQLite (sqlite3 module) | Блокирует event loop на write fsync |
| 10 | `StateManager` reads | Sync SQLite | Аналогично |
| 11 | HTTP client к Yandex (TTS POST) | httpx AsyncClient | Неблокирующий |
| 12 | `_delayed_hangup` task | asyncio background | 100ms poll |

**Критично** для real-time: всё кроме Asterisk main thread и gRPC pool живёт **в одном Python asyncio loop под GIL**. Если Silero inference + SQLite write + JSON parsing попадают в один event loop tick — tick растягивается до 5-10ms, и `asyncio.sleep` в `_speak` может взять больше чем нужно. Именно поэтому `_speak` использует `sleep(0.019)` (а не 0.020 как `_speak_pcm`) — компенсация ~1ms параллельной нагрузки.

Это объясняет 19.04-наблюдение: отключение MixMonitor улучшило на слух. **MixMonitor и `voice_asterisk.py` не делят Python GIL** (Asterisk в C), но делят **дисковый I/O** и **CPU** (был 1 vCPU, стало 2). После апгрейда 2 vCPU отключение MixMonitor не должно больше помогать — если помогает, значит bottleneck не в CPU, а в disk или в Asterisk internals.

---

## Раздел 7. Критичные параметры производительности

Все параметры с источником — либо строка кода, либо env.

| Параметр | Значение | Где | Влияние |
|----------|----------|-----|---------|
| `SAMPLE_RATE_IN` / `SAMPLE_RATE_OUT` | 8000 Hz | `voice_asterisk.py:57-58` | Общий sample rate pipeline'а. 8kHz = мужской голос +/-, Yandex модели заточены под это |
| `frame_size` (AudioSocket) | 320 bytes | `voice_asterisk.py:1007,1062` | 20ms @ 8kHz slin16. Фиксирован AudioSocket-протоколом |
| `asyncio.sleep` в `_speak`/`_speak_pcm` | 0.019 / 0.020 (fix 20.04) | `voice_asterisk.py:1090,1032` | Target wall_per_chunk = 20ms = audio rate. `_speak_pcm` sleep(0.020): без параллельной нагрузки — попадает в 20ms. `_speak` sleep(0.019): +1ms event loop overhead от gRPC+Silero даёт те же 20ms. До 20.04 было 0.018 → overflow → drops |
| `VAD_SILENCE_THRESHOLD` | 0.5s | `voice_asterisk.py:66` | Silence для REST-ветки EOU. В gRPC не используется |
| `VAD_MIN_SPEECH_DURATION` | 0.3s | `voice_asterisk.py:69` | Минимум речи для STT |
| `MIN_SPEECH_BYTES_FOR_STT` | 10240 bytes (0.64s) | `voice_asterisk.py:76-78` | REST-ветка: короче → noise skip |
| `BARGE_IN_COOLDOWN` | 0.5s | `voice_asterisk.py:73-75` | После TTS cancel — игнорируем VAD (echo cascade protection) |
| `BARGE_IN_SILENCE_RESET` | 0.3s | `voice_asterisk.py:86` | Sustained silence до buffer clear (Silero chunking mismatch fix) |
| `SILERO_VAD_THRESHOLD` | 0.5 | `voice_asterisk.py:82` | Normal VAD speech probability |
| `SILERO_VAD_THRESHOLD_BARGE_IN` | 0.5 | `voice_asterisk.py:83-85` | Раньше 0.6 — не пробивал TTS echo mix |
| `SILERO_CHUNK_SAMPLES_8K` | 256 (32ms) | `voice_asterisk.py:175` | Silero inference unit |
| `SILERO_LSTM_DIM` | 64 (v4) | `voice_asterisk.py:177` | v5 был 128, не подошёл для 8kHz |
| `intra_op_num_threads` / `inter_op_num_threads` | 1 / 1 | `voice_asterisk.py:187-188` | ONNX single-threaded — не блокирует GIL threads, но блокирует event loop на inference |
| `confirm_frames` barge-in | 10 (Silero) / 5 (energy) | `voice_asterisk.py:869` | Sustained speech перед cancel TTS. 10 = ~200ms (с chunking mismatch) |
| `YANDEX_STT_EOU_MODE` | `high` | env | Sensitivity HIGH = быстрый EOU |
| `YANDEX_MAX_PAUSE_HINT_MS` | 700 | env (Phase 1, 18.04) | Hint для DefaultEouClassifier — median EOU_WAIT 1778 → 1036ms |
| `YANDEX_TTS_VOICE` | `alena` | env | Russian female voice, Yandex Alena v1 |
| `YANDEX_TTS_SPEED` | 1.1 | env | 10% быстрее neutral |
| `YANDEX_TTS_EMOTION` | `neutral` | env | Alena также поддерживает good/evil |
| `SSML break time` | 300ms | `voice_asterisk.py:306` | Max 2 на реплику, integer ms only (Yandex требование) |
| `max_tokens` LLM | 400 | `core/pipeline.py` | Короткие voice-ответы |
| `AUTO_HANGUP_DELAY_SEC` | 1.5s | `voice_asterisk.py:135` | Polite pause после farewell → hangup |
| RTP port range | 10000-20000/udp | `rtp.conf:10-11` | 10k портов для одновременных звонков |
| `Wait(0.5)` в dialplan | 500ms | `extensions.conf:11` | Пауза до первого фрейма — media setup grace |

---

## Раздел 8. Файлы и их назначение

| Путь (на VPS sofia-voice) | Назначение |
|---------------------------|------------|
| `/etc/asterisk/asterisk.conf` | Общие настройки Asterisk |
| `/etc/asterisk/pjsip.conf` | PJSIP trunk к Telfin (транспорт, registration, endpoint, identify) |
| `/etc/asterisk/extensions.conf` | Dialplan: `[from-telphin]` (входящий), `[outbound-audiosocket]` (dial.py outbound) |
| `/etc/asterisk/rtp.conf` | RTP порт-диапазон 10000-20000 |
| `/etc/asterisk/logger.conf` | Уровни логирования Asterisk |
| `/etc/systemd/system/sofia-voice.service` | systemd unit — `Restart=on-failure`, `EnvironmentFile=/opt/sofia-voice/.env`, `LOGURU_COLORIZE=false` |
| `/etc/cron.d/sofia-voice-recordings` | 03:00 WAV→Opus >72h, 03:30 delete Opus >30 дней |
| `/opt/sofia-voice/voice_asterisk.py` | Главный процесс — AudioSocket server, VAD, orchestration |
| `/opt/sofia-voice/yandex_stt_grpc.py` | Yandex STT v3 gRPC streaming wrapper |
| `/opt/sofia-voice/yandex_proto/` | Auto-generated protobuf Python bindings (stt_pb2, stt_service_pb2_grpc) |
| `/opt/sofia-voice/core/pipeline.py` | Скопирован из основного проекта — `stream_voice_response()`, промпты, anti-hallucination |
| `/opt/sofia-voice/state_manager.py` | SQLite-backed состояние клиента (goal/budget/meeting_agreed/etc) |
| `/opt/sofia-voice/sofia_prompt_v2.py` | System prompts (RIZALTA + Atlantis варианты) |
| `/opt/sofia-voice/rag_module.py` | RAG код (ВЫКЛЮЧЕН в voice — скорость) |
| `/opt/sofia-voice/pipeline.py` | Local copy (возможен дрейф с main repo) |
| `/opt/sofia-voice/silero_vad.onnx` | Silero VAD v4 ONNX (1.8 MB) |
| `/opt/sofia-voice/silero_vad_v5.onnx.legacy` | v5 сохранена для future re-test |
| `/opt/sofia-voice/greeting_rizalta.pcm` | Cached greeting, 198 318 bytes = 12.4s |
| `/opt/sofia-voice/greeting_atlantis.pcm` | Cached greeting для Atlantis mode |
| `/opt/sofia-voice/sofia_voice.db` | SQLite — messages + client_state (voice-local, НЕ синхронизирован с main server) |
| `/opt/sofia-voice/.env` | Env vars — API keys, model selectors, `VOICE_PROMPT_MODE`, `YANDEX_MAX_PAUSE_HINT_MS`, etc |
| `/opt/sofia-voice/venv/` | Python 3.12 venv (onnxruntime, grpcio, httpx, loguru, openai SDK) |
| `/opt/sofia-voice/dial.py` | Manual outbound calls (originate + realtime transcript stream) |
| `/opt/sofia-voice/bin/rotate_recordings.sh` | Cron script — WAV→Opus |
| `/var/lib/asterisk/recordings/<YYYY-MM-DD>/<UUID>.wav` | MixMonitor output |
| `/var/log/asterisk/full.log` | Asterisk internal log (сильно рос до UFW — 44 KB/s сканеры) |
| `/var/log/sofia-voice/recordings_rotate.log` | Cron rotation log |

Environment variables (см. `.env` на VPS — ключи маскированы):

```
VOICE_PROMPT_MODE=rizalta
VOICE_TTS_PROVIDER=yandex
VOICE_VAD_PROVIDER=silero
STT_MODE=grpc
YANDEX_STT_EOU_MODE=high
YANDEX_MAX_PAUSE_HINT_MS=700
YANDEX_TTS_VOICE=alena
YANDEX_TTS_EMOTION=neutral
AUTO_HANGUP_ENABLED=true
VOICE_MODEL_YANDEX=gpt://<folder>/yandexgpt/latest
YC_FOLDER_ID=<folder-id>
YC_API_KEY=<маскировано>
YANDEX_SPEECHKIT_API_KEY=<маскировано>
ELEVENLABS_API_KEY=<маскировано, dead branch>
ELEVENLABS_VOICE_ID=YjESejviApN7SHrbfnA2 (Nastya, legacy)
LLM_PROXY_BASE=http://72.56.64.91:8095 (legacy, только для ElevenLabs rollback)
DB_PATH=sofia_voice.db
SOFIA_PATH=/opt/sofia-voice
```

---

## Раздел 9. Временная диаграмма типичного turn'а

От момента «клиент замолчал» до момента «Sofia начинает звучать у клиента».

```
T=0ms        Клиент произнёс последний слог
│
│  ┌─ Yandex STT обнаруживает EOU ──────────────────────────────────┐
│  │  - последний partial-change ts зафиксирован сервером           │
│  │  - DefaultEouClassifier с sensitivity=HIGH + max_pause=700ms   │
│  │  - eou_update → _on_grpc_eou на VPS                            │
│  └────────────────────────────────────────────────────────────────┘
│
T≈1036ms     EOU_WAIT median (Phase 1 VLAT-07, 18.04)
│            p95=1446ms, до Phase 1 было 1778/2148ms
│
│            _process_turn запускается (asyncio.create_task)
│
│  ┌─ LLM (YandexGPT 5 Pro) ────────────────────────────────────────┐
│  │  - history из SQLite (до 20 msgs)                              │
│  │  - POST → AI Studio, streaming response                        │
│  │  - anti-hallucination regex на tail                            │
│  │  - [END] marker extraction                                     │
│  │  - sanitize_for_tts + add_ssml_breaks                          │
│  └────────────────────────────────────────────────────────────────┘
│
T≈1674ms     LLM response complete (~638ms LLM)
│
│  ┌─ TTS (Yandex Alena v1) ────────────────────────────────────────┐
│  │  - single POST к tts.api.cloud.yandex.net                      │
│  │  - lpcm 8kHz, voice=alena, speed=1.1                           │
│  │  - Response = весь PCM одним ответом                           │
│  └────────────────────────────────────────────────────────────────┘
│
T≈1851ms     TTS first (и единственный) byte (~177ms TTFB)
│
│            _speak() начинает loop
│            первый _send_audio → AudioSocket → Asterisk
│
T≈1852ms     Asterisk получил первый slin16 frame
│            Asterisk кодирует в G.711 → RTP → UDP
│
T≈1855-1900ms Telfin получил первый RTP пакет (30-50ms transit)
│              Telfin транскодирует → PSTN
│
T≈2000-2100ms Первый звук достигает динамика клиента
              (~150-250ms one-way PSTN latency)

ИТОГО: ~2 секунды от конца речи клиента до первого звука Sofia.
       Видимая клиенту пауза: ~1.0-1.2 секунды (до первого слышимого звука)
       т.к. ~700-900ms уходит на SIP/RTP/PSTN transit (клиент этот latency
       воспринимает как «телефон, ну нормально»).
```

**Greeting** (в начале звонка) — особый случай:
- Cached PCM файл `greeting_rizalta.pcm` прочитан с диска (`_speak_pcm`, без TTS запроса)
- TTFB от `Wait(0.5)` завершения до первого AudioSocket пакета: **~0ms** (instant)
- Greeting длится ~12.4 секунды (198 318 bytes / 16000 bytes/s)

---

## Раздел 10. Known bottlenecks и открытые гипотезы

### Проверено (подтверждено или опровергнуто)

| Гипотеза | Статус | Источник |
|----------|--------|----------|
| CPU bottleneck на 1 vCPU | **Подтверждено ранее, опровергнуто после апгрейда** | Апгрейд на 2 vCPU 4 GB 19.04 вечер. Проглатывания остались |
| `asyncio.sleep` точность | **Опровергнуто** | Per-chunk timing 20.04: median overrun 1ms, max 3.5ms, 0 overrun >10ms. 4373 чанков замерено |
| **Pacing overflow 18ms vs 20ms audio rate** | **Подтверждено + решено (20.04)** | На `sleep(0.018)`: wall_per_chunk 19.1ms vs playback 20ms → 4.5% opережение → Asterisk buffer overflow → 209 dropout-окон в 12s greeting. Fix: `_speak_pcm`=0.020, `_speak`=0.019 (асимметрия компенсирует +1ms event loop overhead от gRPC STT + Silero inference в активном разговоре). После фикса: correlation greeting PCM vs MixMonitor = 0.987 (было 0.034), 0 dropouts. Per-reply excess −1.6 … −25 ms на репликах до 23s (идеальное совпадение с audio rate). Snapshots: `/tmp/voice_asterisk.py.before_instr_20260420_041752`, `before_cleanup_20260420_071727` |
| `_send_audio` блокировка socket.send | **Опровергнуто** | send_dur median 75us, max 458us, 0 случаев >1ms |
| Overrun группируется по позиции в реплике | **Опровергнуто** | first_5 avg 905us, mid 955us, last_5 1039us — равномерно |
| Один-из-11 реплик выделяется overrun'ами | **Опровергнуто** | max overrun per-reply 2.13-3.51ms, разница <1.5ms |

### Открыто (требует проверки)

| Гипотеза | Как проверить |
|----------|---------------|
| **MixMonitor I/O contention** | Отключить MixMonitor (закомментировать в `extensions.conf:14`), сделать звонок, сравнить на слух |
| **Asterisk jitter buffer** настроен неоптимально | `rtp set debug on` в Asterisk CLI, поймать одну реплику, смотреть RTP timestamps |
| **Silero VAD GIL contention** в event loop | Во время _speak логировать время между chunk'ами в `_handle_packet` — если растягивается когда VAD inference, корреляция нашлась |
| **SQLite write fsync** в середине turn'а | Профайлинг `save_message` — sync commit может блокировать 2-10ms при нагрузке. Перевести в `PRAGMA synchronous=NORMAL` или асинхронный write queue |
| **Yandex TTS границы PCM** (артефакты на phrase boundaries) | Скачать 2-3 реплики через curl с теми же параметрами, сравнить на слух с живым звонком. Проверить SSML break влияние |
| **Asterisk slin16→G.711 encoding** | Записать pre-encode (MixMonitor захватывает уже slin16) и post-encode (tcpdump RTP → pcap → sox play) — сравнить |
| **RTP jitter от Telfin** | Grafana/Asterisk CDR extra, пакетная потеря >0.1% на interface к Telfin |
| **PJSIP media buffer underrun** | `pjsip set logger on` — watch для `underflow`/`discard` messages в логах |

### Заведомо известные неоптимальности (побочные проблемы)

1. **CLAUDE.md устарел**: в блоке yandex_tts написано «PCM 48kHz», реальность — 8kHz (`voice_asterisk.py:331`). Поправить при Session End.
2. **Silero chunking mismatch**: 320B frame vs 512B chunk → альтернация True/False. Исправлено частично через `BARGE_IN_SILENCE_RESET=0.3s`, но могло бы быть чище если AudioSocket отдавал бы 512B сразу (требует патча Asterisk AudioSocket app).
3. **pipeline.py дубль**: `/opt/sofia-voice/pipeline.py` И `/opt/sofia-voice/core/pipeline.py`. Возможен дрейф — один из них не используется. Требует проверки.
4. **Instrumentation `[CHUNK]` logs**: на 2-минутный звонок ~4000 строк. На 10-часовой day-load = 1M строк/день, ~300 MB. Перед PROD — либо снизить до DEBUG level, либо добавить sampling (каждый 10-й chunk).
5. **dead branch ElevenLabs + Groq + OpenAI** в `voice_asterisk.py`: ~200 строк неактивного кода. Rollback-fidelity vs читаемость — tradeoff.
6. **gRPC stream close race**: при `_cleanup` закрываем gRPC и writer одновременно через try/except — в логах иногда `CANCELLED` которое игнорируется фильтром. Неблокирующий, но шумный.

---

## Приложение A. Быстрая навигация по коду `voice_asterisk.py`

| Строка | Что |
|--------|-----|
| 1-42 | Docstring + imports + config load |
| 43-147 | Constants (AudioSocket, VAD, TTS, proxy, DB) |
| 150-162 | `compute_rms` (energy VAD, dead branch) |
| 165-240 | Silero VAD singleton + per-call `SileroVAD` class |
| 248-285 | `transcribe_audio` (REST STT Yandex) |
| 293-310 | `add_ssml_breaks` |
| 313-362 | `synthesize_tts_yandex` (REST TTS) |
| 365-458 | `stream_tts_audio` (ElevenLabs legacy) |
| 468-500 | SQLite helpers (`_ensure_tables`, `save_message`, `get_history`) |
| 508-570 | `AudioSocketCall.__init__` + state fields + dispatch setup |
| 572-596 | `run()` main packet loop |
| 598-648 | `_handle_packet` + routing |
| 650-688 | `_send_greeting` + cached PCM logic |
| 690-740 | `_process_audio_vad` (REST path) |
| 742-763 | `_open_grpc_stream` |
| 765-785 | `_stream_audio_to_grpc` (gRPC path) |
| 787-838 | `_on_grpc_partial` / `_on_grpc_final` / `_on_grpc_eou` callbacks |
| 840-847 | `_fallback_to_rest` |
| 849-897 | `_detect_barge_in` |
| 899-1001 | `_process_turn` — главная оркестрация STT→LLM→TTS |
| 1003-1044 | `_speak_pcm` — cached PCM playback |
| 1046-1147 | `_speak` — TTS + per-chunk instrumented loop |
| 1149-1188 | `_should_hangup` + `_delayed_hangup` |
| 1202-1222 | `_send_hangup` + `_send_audio` |
| 1224-1242 | `_cleanup` |
| 1250-1295 | `main()` + server startup |

---

## Приложение B. Как проверить текущее состояние — список команд

```bash
# Сервис и версия
ssh sofia-voice 'systemctl is-active sofia-voice'
ssh sofia-voice 'systemctl status sofia-voice --no-pager | head -20'

# Последние 50 строк журнала
ssh sofia-voice 'journalctl -u sofia-voice -n 50 --no-pager'

# Последний звонок
ssh sofia-voice 'journalctl -u sofia-voice --since "2 hours ago" --no-pager | grep -E "New AudioSocket|Call UUID|Call ended"'

# Turn timings за последний час
ssh sofia-voice 'journalctl -u sofia-voice --since "1 hour ago" --no-pager | grep "Turn timings"'

# EOU_WAIT статистика
ssh sofia-voice 'journalctl -u sofia-voice --since "1 hour ago" --no-pager | grep EOU_WAIT'

# Per-chunk stats (после инструментации 20.04)
ssh sofia-voice 'journalctl -u sofia-voice --since "1 hour ago" --no-pager | grep "\[CHUNK\]" | wc -l'

# Записи звонков
ssh sofia-voice 'ls -la /var/lib/asterisk/recordings/$(date -u +%Y-%m-%d)/ | tail'

# UFW
ssh sofia-voice 'ufw status numbered | head -20'

# Asterisk PJSIP registration
ssh sofia-voice 'asterisk -rx "pjsip show registrations"'
ssh sofia-voice 'asterisk -rx "pjsip show endpoints"'

# Сервер resources
ssh sofia-voice 'uptime && free -h && df -h /var/lib/asterisk'
```

---

**Конец документа.**
