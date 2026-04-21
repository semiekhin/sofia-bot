# Pilot Workstation Runbook

Для сессий пилота холодного обзвона RIZALTA. Три терминала, конкретные команды, известные тонкости. Восстановить контекст рабочей станции без чтения всей истории.

## Рабочая станция (3 терминала)

### T1 — Live audio на Mac (вторая вкладка, весь день пилота)

```bash
while true; do
  ssh sofia-voice '/opt/sofia-voice/bin/listen_live.sh' 2>/dev/null | \
      ffplay -nodisp -autoexit -f s16le -ar 8000 -ch_layout mono -
done
```

- `ffplay` из `brew install ffmpeg`. Проверка: `which ffplay` → `/opt/homebrew/bin/ffplay`
- SSH alias `sofia-voice` должен быть по ключу (`ssh-copy-id sofia-voice` один раз). Без ключа pw-prompt рвёт while-loop
- Скрипт exit'ит после 20с idle файла → ffplay EOF → while перезапускает сам
- Задержка end-to-end 2–5с, subjectively слышно оба голоса (Sofia + клиент)
- `2>/dev/null` глушит stderr-статусы (`[listen_live] Waiting...`). Убрать если нужна диагностика

### T2 — Исходящий звонок (main-server через `ssh sofia-dev`)

```bash
ssh sofia-voice 'python3 /opt/sofia-voice/dial.py +7XXXXXXXXXX'
```

Realtime вывод:
- `[HH:MM:SS] Originating/Answered/Ended` — state transitions (wall clock UTC)
- `[MM:SS] USER/SOFIA` — реплики (offset от originate)
- `[MM:SS] METRICS: eou=Nms llm=Nms tts=Nms` — per-turn метрики после каждой SOFIA-реплики

Post-call:
- `Status: ANSWERED`, `Duration: Ns (billsec: Ns)`
- `Recording: /var/lib/asterisk/recordings/YYYY-MM-DD/<CALL_UUID>.wav`
- `Download (run from your Mac): scp sofia-voice:/path/to/file ~/Desktop/`
- Transcript inline в stdout

### T3 — Скачать запись (Mac, по необходимости)

Копипаст `scp`-команды из `Download:` строки T2. Выполняется с Mac (не из T2-сессии):

```bash
scp sofia-voice:/var/lib/asterisk/recordings/YYYY-MM-DD/<CALL_UUID>.wav ~/Desktop/
```

### Мониторинг (ad-hoc)

```bash
# Сколько активных каналов — перед любым restart, перед следующим звонком
ssh sofia-voice 'asterisk -rx "core show channels count"'

# Если dial.py завис — убить конкретный
ssh sofia-voice 'pkill -f "dial.py <phone>"'

# Лог исходящих сегодня (jsonl)
ssh sofia-voice "tail -f /var/log/sofia-voice/outbound_$(date -u +%Y-%m-%d).jsonl"

# Метрики voice-сервиса
ssh sofia-voice 'journalctl -u sofia-voice -f -o cat'
```

## Состояние 21.04.2026

### Задеплоено сегодня (7 коммитов DEV, не запушено)

| SHA | Что |
|---|---|
| `8ac8233f` | feat(dial): per-turn metrics + turn timers + recording path |
| `f28cd748` | fix(dial): use CALL_UUID from CDR.lastdata for recording path |
| `f501d719` | feat(voice): live audio listen wrapper |
| `37e099a5` | feat(voice): ExecStop hangup AudioSocket orphans on restart |
| `2304b075` | docs: CLAUDE.md three-terminal workflow |
| `38c42abf` | fix(dial): early exit when originate produces no channel (v1, flawed, superseded) |
| `75082b73` | fix(dial): require 3 consecutive Up/Ringing before cancelling giveup |

### Состояние инфры

- 5 реальных звонков пилота холодной базы проведены (3 ANSWERED, 1 hang-up-after-hello, 1 hang-bug → починен)
- `dial.py` больше не висит на invalid/unanswered номерах — exit за ~35с вместо 600с
- `sofia-voice.service` active, `ExecStop=bin/hangup_audiosocket.sh` активен
- Telphin Registered, UFW whitelist `46.229.221.93` + `213.170.84.105`
- `/opt/sofia-voice/bin/`: `listen_live.sh`, `hangup_audiosocket.sh`, `rotate_recordings.sh`

### Carry-over / открыто

- **Telphin autodial discovery** — Сергей написал менеджеру: поддерживает ли «Голосовой робот» AMD + passthrough живого ответа на наш SIP endpoint? Если да → свой `dial.py` может устареть (их dialer 1790₽/мес, до 100 одновременных). Если нет → продолжаем свой стек.
- **Greeting PCM artefacts** (P1 с 20.04) — шероховатости на cached greeting, на live TTS чисто. `speed=1.2` зафиксирован. Бесплатная диагностика: live-синтез greeting в 1 звонок + MixMonitor diff vs cached-звонка.
- **Watchdog cron** (P1 с 20.04) — safety net против CPU-storm. После ExecStop-фикса менее критично, откладывали до реальных метрик load от пилота.
- **Misleading `FAILED (no CDR after 600s)` message** — новый P1 косметика. При channel_giveup-exit (35с) выводится «600s» т.к. main() пишет один текст для обеих веток no-CDR. Пробросить reason up из `wait_for_cdr`.

## Известные особенности и тонкости

### Orphan AudioSocket при рестарте sofia-voice (выучено 20.04)

`systemctl restart sofia-voice` во время активного звонка → Python умирает → Asterisk PJSIP канал остаётся с `AudioSocket()` app на dead TCP socket (port 9090) → tight retry loop → 193% CPU / load 27 (инцидент 20.04).

**Защита с 21.04:** `ExecStop=/opt/sofia-voice/bin/hangup_audiosocket.sh` делает targeted hangup каналов с `application=AudioSocket` ДО SIGTERM. Другие PJSIP (echo/voicemail/peer-to-peer) не трогаются.

**Дисциплина:** всё ещё не рестартить зря в середине живого разговора — клиент услышит обрыв.

### Briefly-existing channels для invalid dial (выучено 21.04)

При silent originate failure (Telphin SBC вернул 4xx/5xx) Asterisk на 1–2с создаёт PJSIP канал в state `Ring`/`Other` пока SIP INVITE летит, затем teardown. `dial.py` escape требует **3 consecutive Up/Ringing polls** (~3с sustained) — иначе ложно сработает `channel_ever_seen = True` и escape никогда не зафаерит.

**Не переделывать на `is not None`** — это была первая попытка фикса (`38c42abf`), не сработала. Рабочая версия — `75082b73`.

### Два разных UUID у Asterisk (выучено 21.04)

- **CDR uniqueid** — epoch.counter, например `1776758372.14`. Записывается в CDR, трекается dial.py для find_cdr_by_uniqueid.
- **CALL_UUID** — RFC-4122 UUID, например `c83688c7-6362-48dd-9c8e-a167b875e473`. Генерируется в dialplan `[outbound-audiosocket]` через `${SHELL(cat /proc/sys/kernel/random/uuid)}`, идёт в AudioSocket и как **имя файла** MixMonitor.

`dial.py` `_print_recording_info` берёт CALL_UUID из `CDR.lastdata` (`"UUID,host:port"`), НЕ из `uniqueid`. Если поменять местами — `Recording: not found`.

### SSH ключ обязателен для listen_live

Без ключа каждая итерация `while true` в T1 попросит пароль — рвёт loop. Настроено 21.04 через `ssh-copy-id sofia-voice` с Mac Сергея.

### No restart sofia-voice во время активных звонков (дисциплинарное)

Техническая защита теперь есть (ExecStop), но клиент всё равно услышит обрыв. Проверка перед любым restart:

```bash
ssh sofia-voice 'asterisk -rx "core show channels count"'  # должно быть 0
```

### Конкуретные outbound из разных сессий — V1 assumption

`dial.py` рассчитан на один outbound в момент времени. `find_new_telphin_uniqueid`, fallback CDR matcher, `listen_live.sh` все полагаются на V1. Параллельные запуски могут путать UUID/CDR между dial.py-процессами (наблюдаемо в jsonl `uuid=1776758372.14` для двух concurrent calls 07:57/07:59 — разные phone'ы, одна CDR).
