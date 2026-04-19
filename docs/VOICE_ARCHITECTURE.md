# Voice Architecture — Sofia-GPT

Архитектура голосового стека RIZALTA на VPS sofia-voice (185.207.66.201).
Вынесено из CLAUDE.md (17.04 разгрузка). Hot-reference для voice-инженера.

## Голосовой стек Asterisk (voice_asterisk.py)

**Архитектура (2 сервера):**

```
Клиент звонит +79310091644
    │
    ▼
Телфин SIP (sipproxy.telphin.ru:5068)
    │
    ▼
┌─────────────── VPS 185.207.66.201 (ssh sofia-voice) ───────────────┐
│ Asterisk 20 (PJSIP, порт 5090)                                     │
│    │                                                                 │
│    ▼ AudioSocket (TCP localhost:9090)                                │
│ voice_asterisk.py:                                                   │
│    ├─ VAD: Silero VAD v4 ONNX (0.5s silence threshold, 17.04)       │
│    ├─ Barge-in: 10-frame confirm Silero / 5-frame energy            │
│    ├─ Cooldown 500ms + sliding-silence reset 300ms                  │
│    ├─ _tts_playing флаг (barge-in только при active TTS)            │
│    ├─ STT: Yandex SpeechKit REST v1 (~290ms) ──── напрямую          │
│    ├─ LLM: YandexGPT 5 Pro (~620ms) ─────────────── напрямую        │
│    └─ TTS: Yandex SpeechKit Alena v1 LPCM (~155ms) напрямую         │
└─────────────────────────────────────────────────────────────────────┘
                  ▲
          UFW firewall (17.04):
          22/tcp + 46.229.221.93:5090/udp + 10000-20000/udp
          default deny incoming — SIP-сканеры отрезаны на SYN

┌─────────────── Основной сервер 72.56.64.91 ────────────────────────┐
│ nginx proxy :8095 (UFW: only 185.207.66.201) — только для ТЕКСТА   │
│    ├─ /openai/   → https://api.openai.com/  (text: gpt-5.2)        │
│    └─ (legacy: /groq/, /elevenlabs/ — мёртвые ветки голоса)        │
└────────────────────────────────────────────────────────────────────┘
```

**Архитектурное решение (16.04.2026):** После миграции голосового стека на Yandex Cloud (все API доступны из России напрямую) — proxy на 72.56.64.91 **больше не участвует в голосовом пути**. Остаётся для текстового стека (OpenAI gpt-5.2). Двухсерверная архитектура сохраняется: Телфин блокирует SIP по IP (403 Forbidden Ip) — VPS в белом списке.

**AudioSocket протокол (TCP):**
- Пакет: `[1 byte type][2 bytes length BE][payload]`
- UUID=0x01 (16 bytes binary), Audio=0x10 (slin 8kHz, 320 bytes/20ms), Hangup=0x00, Error=0xFF
- Телфин отправляет INVITE на extension 's'

**Тайминги (конец речи → первый звук ответа, обновлено 17.04):**
- VAD silence: 500ms (поднято с 300ms на звонке e177d7ad — резало фразы на микропаузах)
- STT (Yandex REST v1): ~290ms
- LLM (YandexGPT 5 Pro напрямую): ~620ms медиана
- TTS first byte (Yandex Alena v1 LPCM напрямую): ~155ms
- **Итого: ~1.0с ощущаемая пауза** (чуть выше чем 860ms после 16.04 из-за более длинного silence threshold — цена за целые фразы)
- Greeting TTFB: **0ms** (cached PCM), 1ms до первого фрейма

**Silero VAD v4 (17.04):**
- Модель: `/opt/sofia-voice/silero_vad.onnx`, 1.8MB, md5 `03da8de2fec4108a089b39f1b4abefef`
- Singleton ONNX session (eager-load в `main()`, лог «Silero VAD loaded: ... (v4, 8kHz, md5=...)»)
- Per-call `SileroVAD` instance: `_h`, `_c` LSTM states `[2, 1, 64]`, buffer до 512B chunks (256 samples @ 8kHz = 32ms)
- Threshold 0.5 одинаково для normal VAD и barge-in (было 0.6 для barge-in — не пробивалось)
- Inputs: `input` float32 [1, N], `sr` int64 scalar, `h`/`c` state tensors
- **v5 не подошла для 8kHz** (13% detection на чистой речи, оптимизирована под 16kHz). v5 сохранена как `silero_vad_v5.onnx.legacy`
- Python deps: `onnxruntime 1.24.4`, `numpy 2.4.4` (numpy подтянулся с onnxruntime)

**Barge-in логика (17.04, итоговая):**
- Константы: `BARGE_IN_COOLDOWN=0.5` (отбрасывание VAD-фреймов после TTS cancel против echo cascade), `MIN_SPEECH_BYTES_FOR_STT=10240` (0.64с), `BARGE_IN_SILENCE_RESET=0.3`
- Флаги: `_is_responding` (весь STT→LLM→TTS) vs `_tts_playing` (только реальное TTS output). Barge-in detection **только** при `_tts_playing=True` — иначе pre-TTS race (клиент договаривает свою реплику в фазе LLM → cancel_playback=True до первого chunk → 0s played)
- Confirm frames: 10 для Silero (~200ms sustained speech с учётом chunking), 5 для energy (100ms, 1:1 frame→RMS). Bifurcate через `confirm_frames = 10 if self._vad is not None else 5` — energy-ветка сохраняет rollback fidelity для `VOICE_VAD_PROVIDER=energy`
- Sliding-silence reset: `_last_barge_in_speech_ts` отслеживает последний is_speech=True; buffer clear только после 300ms sustained silence (защита от Silero chunking альтернации True/False)
- После cancel TTS `_process_turn` finally **очищает** barge-in buffer (без re-feed в VAD — иначе cascade на polluted fragment >MIN_BYTES)
- Dispatch `_handle_packet`:
  ```
  if not _is_responding:  → _process_audio_vad (normal turn)
  elif _tts_playing:      → _detect_barge_in
  else:                   → ignore (STT/LLM фаза, клиент договаривает свою реплику)
  ```

**UFW firewall (17.04):**
- Whitelist: 22/tcp (SSH), 46.229.221.93:5090/udp (Telfin SIP /32), 10000-20000/udp (RTP media)
- Default deny incoming / allow outgoing
- Закрыты наружу: UDP 5060 (chan_sip legacy), UDP 4569 (IAX2) — только сканеры ими пользовались
- Эффект: рост `/var/log/asterisk/full.log` **44 KB/s → 0 B/s** (SIP-сканеры блокируются на SYN, Asterisk их не видит)
- fail2ban: P1 backlog, не развёрнут (UFW даёт 100%). Контракт для fail2ban готов

**SIP данные Телфин:**
- Сервер: sipproxy.telphin.ru:5068
- Добавочный: 15400*101, пароль: jAJk6585e
- Кодеки: alaw, ulaw (G.711)
- Номер: +79310091644

**Файлы голосового стека:**
- `voice_asterisk.py` — AudioSocket сервер + VAD + STT/LLM/TTS pipeline
- `asterisk/pjsip.conf` — PJSIP trunk к Телфин
- `asterisk/extensions.conf` — dialplan (входящий → AudioSocket)
- `asterisk/logger.conf` — логирование Asterisk
- `/etc/nginx/sites-available/llm-proxy` — nginx proxy config
- VPS: `/opt/sofia-voice/` — рабочая директория, venv, .env, sofia_voice.db

**Деплой голосового стека:**
```bash
# Скопировать код на VPS
scp voice_asterisk.py sofia-voice:/opt/sofia-voice/
scp core/pipeline.py sofia-voice:/opt/sofia-voice/core/
# Перезапустить через systemd (НЕ nohup!)
ssh sofia-voice "systemctl restart sofia-voice"
# Проверить статус и логи
ssh sofia-voice "systemctl status sofia-voice"
ssh sofia-voice "journalctl -u sofia-voice -n 50 --no-pager"
```

**systemd unit (создан 10.04):** `/etc/systemd/system/sofia-voice.service` — Type=simple, Restart=on-failure, RestartSec=3, EnvironmentFile=/opt/sofia-voice/.env, LOGURU_COLORIZE=false. Автостарт при ребуте включён (enabled).

**VOICE_PROMPT_MODE (08.04):**
- env-переменная `VOICE_PROMPT_MODE`: `atlantis` (default) или `rizalta`
- Переключает greeting в `voice_asterisk.py` (`_send_greeting()`) и system prompt в `core/pipeline.py` (`stream_voice_response()`)
- На VPS `.env`: `VOICE_PROMPT_MODE=rizalta`
- `VOICE_SYSTEM_PROMPT` — Atlantis (входящая квалификация), НЕ ТРОГАТЬ
- `VOICE_SYSTEM_PROMPT_RIZALTA` — RIZALTA v4.2 (18.04): секции ЧЕЛОВЕЧНОСТЬ + ФАКТЫ-ДОСЛОВНО + МОЖНО ВАРЬИРОВАТЬ (variant pools для pitch-2 closer / offer / messenger / farewell), инструкция `[END]` в конце прощальной реплики (feeds auto-hangup). Без представления, двухчастный каноничный питч, логика мессенджеров, вход 15 млн, Совкомбанк/Сбер ипотека. Коммиты: `ffcde20e` (v4), `ab90940b` (v4.1), `110a6a3c` (v4.2)

**Phase 1 VLAT-07 — `max_pause_between_words_hint_ms=700` (18.04, `393eb062`):**
- Env `YANDEX_MAX_PAUSE_HINT_MS=700` в .env на VPS. 0 = Yandex internal default (rollback).
- Hint в `DefaultEouClassifier` передаётся через `yandex_stt_grpc.py:120-125`.
- EOU_WAIT median **1778 → 1036мс (−742мс, −42 %)**, p95 **2148 → 1446мс**.
- Per-category: short 1924→1011, medium 1790→1145, long 1662→1076.
- L0 rollback: `sed -i 's/=700/=0/' /opt/sofia-voice/.env && systemctl restart sofia-voice`.

**EOU instrumentation (18.04, `d2f875d1`):**
- Per-turn `EOU_WAIT uuid=... turn=N eou_wait_ms=M text_len=K` в journalctl.
- Phantom EOU rate ~54 % (Yandex protocol artefact — duplicate eou_update per real one, харamless но noise).

**Auto-hangup после Sofia farewell (18.04, `b78fe04c`):**
- Hybrid detection: farewell keyword в last 80 chars response OR `state.dialog_finished` (set by `[END]` marker в pipeline.py).
- Keywords: «хорошего дня», «всего доброго», «удачного дня», «удачной дороги», «до свидания», «не буду занимать».
- Timing: 1500 ms polite pause после TTS → AS_TYPE_HANGUP 0x00 frame → Asterisk terminates PJSIP leg.
- Barge-in interlock: 15 × 100ms чанков sleep, cancel если `_is_responding=True` (user заговорил) или `_closed=True`.
- Gate: `VOICE_PROMPT_MODE=rizalta` (Atlantis НЕ затронут).
- Env: `AUTO_HANGUP_ENABLED=true` (default). Rollback: `false` + restart.
- Observability 3 лога: `AUTO_HANGUP detect|exec|cancel uuid=... reason=...`.

**[END] handler fix (18.04, `19102904`):**
- Pre-existing bug: `if "[END]" in answer_text` substring match в `core/pipeline.py:1061` ДО anti-hallucination filter — LLM emit `[END]` в hallucinated tail → `state.dialog_finished=True` flipped → false auto-hangup (впервые проявился call `f184c7be`).
- Fix: swap order (hallucination filter FIRST) + anchor `answer_text.rstrip().endswith("[END]")`.
- ⚠ **Тот же баг лежит в text-path `core/pipeline.py:319-326` для PROD** (Telegram/Radist/web) — P1 backlog.

**MixMonitor recording (18.04, `19a49fa6`):**
- Запись всех звонков в оба dialplan-контекстах (`[from-telphin]` + `[outbound-audiosocket]`).
- Path: `/var/lib/asterisk/recordings/YYYY-MM-DD/<UUID>.wav` (mono mix обеих сторон, raw PCM 8 kHz, no beep).
- TZ: VPS `Etc/UTC` → `STRFTIME` даёт UTC дату (MSK hour − 3 = UTC hour для навигации).
- Cron `/etc/cron.d/sofia-voice-recordings`: 03:00 WAV→Opus 32 kbps (>72 h), 03:30 удалить Opus >30 дней.
- Script: `/opt/sofia-voice/bin/rotate_recordings.sh` (idempotent, atomic WAV→Opus).
- Log: `/var/log/sofia-voice/recordings_rotate.log`.
- Disk projection: ~230 MB WAV/day → ~23 MB Opus → ~700 MB retention 30 дней (<20 GB free).

**dial.py realtime streaming (18.04, `4ce5881b`):**
- Во время звонка в терминал dial.py стримятся USER/SOFIA/AUTO_HANGUP события из journalctl с префиксом `[HH:MM:SS]`.
- Gate: env `STREAM_TRANSCRIPT=true` default.
- Start on channel state→Up, stop on Ended (orphan-safe через finally).
- Post-call SQLite transcript (offset timestamps `[MM:SS]`) выводится как прежде — визуально не путается с realtime block (wall-clock).

**Yandex TTS Alena (текущий провайдер с 16.04):**
- Голос: `alena`, формат `lpcm` 8kHz 16-bit mono (готовый для AudioSocket, без ffmpeg)
- Модель: Yandex SpeechKit v1 REST, endpoint `tts.api.cloud.yandex.net/speech/v1/tts:synthesize`
- TTFB ~150-185ms медиана (single REST POST, весь PCM одним ответом)
- Настройки: emotion=neutral, speed=1.1
- SSML: `<break time="300ms"/>` (Yandex требует integer ms, не дробные секунды как 0.3s)
- Cached greetings (0ms TTFB): `greeting_rizalta.pcm` (198318 bytes, 12.4s аудио, регенерирован 16.04 под RIZALTA v3), `greeting_atlantis.pcm`
- Регенерация cached PCM: inline Python через `synthesize_tts_yandex()` → запись файла
- Ударения: ~99% на русском (лучше ElevenLabs), voice cloning отсутствует
- `add_ssml_breaks()` — функция в voice_asterisk.py, автоматически вставляет breaks между предложениями
- Env VPS: `YC_API_KEY`, `YC_FOLDER_ID`, `YANDEX_TTS_VOICE=alena`, `YANDEX_TTS_EMOTION=neutral`, `YANDEX_TTS_SPEED=1.1`, `VOICE_TTS_PROVIDER=yandex`

**ElevenLabs legacy (dead branch, rollback-only):**
- Переключается через `VOICE_TTS_PROVIDER=elevenlabs` в .env
- Nastya PVC, voice_id=YjESejviApN7SHrbfnA2, модель `eleven_v3`, через proxy 72.56.64.91:8095 → ffmpeg MP3→PCM
- Код сохранён для экстренного rollback

